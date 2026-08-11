# -*- coding: utf-8 -*-
"""Pipeline：依次跑 task1_index → 16 个方向爬虫 → merge_summary → adapter_task1 → combine。

对外接口：
    run_all(log_fn=None) -> dict
        返回 {"code": 0|1, "msg": str,
              "stats": {"web_total", "wechat_total", "total", "failed_directions"}}

说明：
- 爬虫脚本依赖 crawl4ai，需用能 import crawl4ai 的解释器运行（本机为系统 python 3.11）。
  _find_crawl_python() 会按候选顺序探测。
- 单方向爬虫失败不中断，记入 failed_directions。
- 日志写 server/pipeline.log，同时转发给 log_fn（若有）。
"""
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime

BASE = os.path.dirname(os.path.abspath(__file__))          # server/
PROJECT_ROOT = os.path.dirname(BASE)                        # 自动化脚本合集/
CRAWL_SCRIPTS = os.path.join(PROJECT_ROOT, "crawl4ai", "scripts")
SHANDONG_DIR = os.path.join(CRAWL_SCRIPTS, "shandong_official")
OUTPUT_DIR = os.path.join(SHANDONG_DIR, "shandong_output")
UNIFIED_JSON = os.path.join(OUTPUT_DIR, "unified_articles.json")
LOG_FILE = os.path.join(BASE, "pipeline.log")

# 单方向爬虫子进程超时（秒）
CRAWL_TIMEOUT = 1800


def _make_logger(log_fn):
    def log(msg):
        line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
        try:
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            pass
        if log_fn:
            try:
                log_fn(msg)
            except Exception:
                pass
    return log


def _find_crawl_python(log):
    """探测能 import crawl4ai 的解释器。返回命令前缀列表，如 ['python'] 或 ['py', '-3.13']。"""
    candidates = [
        ["python"],
        ["py", "-3.13"],
        ["py", "-3"],
        [sys.executable],
    ]
    for cand in candidates:
        try:
            r = subprocess.run(
                cand + ["-c", "import crawl4ai"],
                capture_output=True, timeout=60,
            )
            if r.returncode == 0:
                log(f"爬虫解释器探测成功: {' '.join(cand)}")
                return cand
        except Exception:
            continue
    return None


def _run(cmd, cwd, log, timeout=None):
    """跑子进程，输出逐行进日志。返回 returncode。"""
    log(f"$ {' '.join(cmd)}  (cwd={cwd})")
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    try:
        proc = subprocess.Popen(
            cmd, cwd=cwd, env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace",
        )
    except Exception as e:
        log(f"!! 子进程启动失败: {e}")
        return -1
    try:
        out, _ = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.communicate()
        log(f"!! 子进程超时（{timeout}s）被终止")
        return -2
    if out:
        for line in out.splitlines():
            log(f"  | {line}")
    return proc.returncode


def run_all(log_fn=None):
    log = _make_logger(log_fn)
    log("=" * 60)
    log("pipeline 开始")

    crawl_py = _find_crawl_python(log)
    if not crawl_py:
        msg = "找不到能 import crawl4ai 的 Python 解释器"
        log(msg)
        return {"code": 1, "msg": msg, "stats": {}}

    # 1) 公众号信源 task1_index.py（项目根，仅标准库，沿用爬虫解释器即可）
    # 防护：RSS 聚合器不可达时 task1_index 会以 0 条覆盖 review/index.json，
    # 这里先备份，若新索引为空且备份非空则还原，避免公众号信源被清空。
    review_index = os.path.join(PROJECT_ROOT, "review", "index.json")
    review_backup = os.path.join(PROJECT_ROOT, "review", "index.backup.json")
    if os.path.exists(review_index):
        shutil.copy2(review_index, review_backup)
    log("---- step 1/4: task1_index.py ----")
    rc = _run(crawl_py + [os.path.join(PROJECT_ROOT, "task1_index.py")],
              cwd=PROJECT_ROOT, log=log, timeout=300)
    if rc != 0:
        log(f"!! task1_index.py 退出码 {rc}（继续后续步骤）")
    try:
        with open(review_index, encoding="utf-8") as f:
            new_items = len(json.load(f).get("items", []))
        old_items = 0
        if os.path.exists(review_backup):
            with open(review_backup, encoding="utf-8") as f:
                old_items = len(json.load(f).get("items", []))
        if new_items == 0 and old_items > 0:
            shutil.copy2(review_backup, review_index)
            log(f"!! task1_index 产出 0 条（疑似 RSS 不可达），已还原备份（{old_items} 条）")
    except Exception as e:
        log(f"!! review/index.json 备份检查异常：{e}")

    # 2) 山东官方招聘爬虫（单站失败不中断）
    log("---- step 2/4: 山东官方招聘爬虫 ----")
    failed = []
    rc = _run(
        crawl_py + [os.path.join(SHANDONG_DIR, "shandong_official_crawler.py"),
                    "--config", os.path.join(SHANDONG_DIR, "sources_config.json")],
        cwd=SHANDONG_DIR, log=log, timeout=CRAWL_TIMEOUT,
    )
    if rc != 0:
        log(f"!! 山东官方招聘爬虫失败（退出码 {rc}）")
        failed.append("shandong_official")

    # 3) adapter_task1 / 4) combine（均为 stdlib 脚本，路径自解析）
    for i, script in enumerate(["adapter_task1.py", "combine.py"], start=3):
        log(f"---- step {i}/4: {script} ----")
        rc = _run(crawl_py + [script], cwd=SHANDONG_DIR, log=log, timeout=300)
        if rc != 0:
            msg = f"{script} 失败（退出码 {rc}）"
            log("!! " + msg)
            return {"code": 1, "msg": msg,
                    "stats": {"failed_directions": failed}}

    # 汇总统计
    stats = {"web_total": 0, "wechat_total": 0, "total": 0, "failed_directions": failed}
    try:
        with open(UNIFIED_JSON, encoding="utf-8") as f:
            s = json.load(f).get("stats", {})
        stats.update({k: s.get(k, 0) for k in ("web_total", "wechat_total", "total")})
    except Exception as e:
        msg = f"pipeline 执行完毕但读取 unified_articles.json 失败: {e}"
        log("!! " + msg)
        return {"code": 1, "msg": msg, "stats": stats}

    code = 0 if not failed else 1
    msg = ("pipeline 完成" if not failed
           else f"pipeline 完成，{len(failed)} 个方向失败: {', '.join(failed)}")
    log(msg + f"  stats={stats}")
    return {"code": code, "msg": msg, "stats": stats}
