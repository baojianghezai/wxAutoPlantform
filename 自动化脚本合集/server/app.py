# -*- coding: utf-8 -*-
"""Flask 桥接服务：n8n ↔ 本地脚本。

端点：
  POST /api/waitUrl   登记 n8n wait 节点回调 URL（存 server/state.json）
  GET|POST /api/run   触发 pipeline（后台线程，防重入），结束后回调 waitUrl
  GET  /api/articles  返回 unified_articles.json 原文
  GET  /api/templates 展开 templates/selector_config.json 为扁平模板列表
  POST /api/submit    {article_id, template_id} 抓原文 HTML → POST 到 waitUrl
  POST /api/publish   n8n 回调：渲染契约 JSON → render_article → push_to_draft
  GET  /api/img?url=  图片代理：带 UA/Referer 抓取外链图，绕过防盗链
  GET  /api/tpl-preview/<name>  返回模板本地预览图（assets/template-previews/）

运行：python server/app.py（依赖见 server/requirements.txt），端口 5001
（5000 已被目标机 Docker 上的 RSS 服务占用）。
若 wxcheck/dist 存在，前端产物也由本服务托管（http://localhost:5001/）。
"""
import json
import os
import re
import threading
from datetime import datetime

import requests
from flask import Flask, jsonify, request, send_file, send_from_directory
from flask_cors import CORS

BASE = os.path.dirname(os.path.abspath(__file__))          # server/
PROJECT_ROOT = os.path.dirname(BASE)                        # 自动化脚本合集/

import sys
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

try:
    from server import pipeline, fetch_html  # 作为包从项目根导入
except ImportError:  # 直接以脚本方式运行（python server/app.py）
    import pipeline  # noqa: E402
    import fetch_html  # noqa: E402

STATE_FILE = os.path.join(BASE, "state.json")
UNIFIED_JSON = os.path.join(PROJECT_ROOT, "crawl4ai", "scripts",
                            "xinjiang_output", "unified_articles.json")
TEMPLATES_DIR = os.path.join(PROJECT_ROOT, "templates")
SELECTOR_CONFIG = os.path.join(TEMPLATES_DIR, "selector_config.json")
# 模板本地预览图目录（由 assets/gen_template_previews.py 生成）
TEMPLATE_PREVIEWS_DIR = os.path.join(PROJECT_ROOT, "assets", "template-previews")
# 前端产物（wxcheck/dist，与 自动化脚本合集 同级）；存在则由本服务直接托管
FRONTEND_DIST = os.path.join(os.path.dirname(PROJECT_ROOT), "wxcheck", "dist")

# 图片代理默认请求头（绕过 mmbiz / 96weixin 等防盗链）
_IMG_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"),
    "Referer": "https://mp.weixin.qq.com/",
}
_IMG_WHITELIST_HOSTS = ("mmbiz.qpic.cn", "newcdn.96weixin.com", "mmbiz.qlogo.cn",
                        "mp.weixin.qq.com", "wx.qlogo.cn", "mmbiz.qpic.cn")

app = Flask(__name__)
CORS(app)

_pipeline_lock = threading.Lock()


# ---------------------------------------------------------------- state

def _load_state():
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------- helpers

def _err(msg, status=200, code=1):
    return jsonify({"code": code, "msg": str(msg)}), status


@app.errorhandler(Exception)
def handle_exception(e):
    # 统一 JSON 错误响应，不裸抛 HTML 500
    from werkzeug.exceptions import HTTPException
    if isinstance(e, HTTPException):
        return jsonify({"code": 1, "msg": e.description}), e.code
    app.logger.exception("unhandled error")
    return jsonify({"code": 1, "msg": f"internal error: {e}"}), 500


# ---------------------------------------------------------------- /api/waitUrl

@app.route("/api/waitUrl", methods=["POST"])
def wait_url():
    data = request.get_json(silent=True) or {}
    url = (data.get("url") or "").strip()
    if not url:
        return _err("missing url", status=400)
    state = _load_state()
    state["waitUrl"] = url
    state["saved_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    _save_state(state)
    return jsonify({"code": 0})


# ---------------------------------------------------------------- /api/run

def _pipeline_worker():
    try:
        result = pipeline.run_all(log_fn=lambda m: app.logger.info(m))
    except Exception as e:
        app.logger.exception("pipeline crashed")
        result = {"code": 1, "msg": f"pipeline exception: {e}", "stats": {}}
    finally:
        _pipeline_lock.release()

    wait = _load_state().get("waitUrl")
    payload = {"code": result.get("code", 1),
               "msg": result.get("msg", ""),
               "stats": result.get("stats", {})}
    if wait:
        try:
            requests.post(wait, json=payload, timeout=30)
            app.logger.info("已回调 waitUrl: %s", wait)
        except Exception as e:
            app.logger.error("回调 waitUrl 失败 %s: %s", wait, e)
    else:
        app.logger.info("无 waitUrl，pipeline 结果仅记日志: %s", payload)


@app.route("/api/run", methods=["GET", "POST"])
def run_pipeline():
    if not _pipeline_lock.acquire(blocking=False):
        return jsonify({"code": 1, "msg": "pipeline already running"})
    t = threading.Thread(target=_pipeline_worker, daemon=True)
    t.start()
    return jsonify({"code": 0, "msg": "pipeline started"}), 202


# ---------------------------------------------------------------- /api/articles

def _fallback_source_category(articles):
    """兜底补齐 source_category（web -> recruitment、wechat -> other）。"""
    for a in articles:
        if not a.get("source_category"):
            a["source_category"] = "recruitment" if a.get("source_type") == "web" else "other"
    return articles


def _template_category_code(template_id):
    """根据 template_id 查模板归属分类，返回 {code, id, label}。

    code 定义见 selector_config.json 的 categories（1=招聘类、2=农业类、0=其他）；
    模板未命中时返回 {"code": 0, "id": "other", "label": "其他"}。
    """
    try:
        with open(SELECTOR_CONFIG, encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception:
        return {"code": 0, "id": "other", "label": "其他"}

    categories = cfg.get("categories") or {}
    block_cat = ""
    for block in (cfg.get("content_types") or {}).values():
        for t in block.get("templates", []):
            if t.get("id") == template_id:
                block_cat = t.get("category") or block.get("category", "")
                break
        if block_cat:
            break

    if not block_cat:
        block_cat = "other"
    cdef = categories.get(block_cat, {})
    return {
        "code": cdef.get("code", 0),
        "id": block_cat,
        "label": cdef.get("label", block_cat),
    }


def _load_wechat_accounts():
    """读取 config.json 的 wechat.accounts（含 appid/secret，仅供内部使用）。

    返回 [{id, name, appid, secret}]；无 accounts 时用旧式单账号合成 default。
    """
    try:
        with open(os.path.join(PROJECT_ROOT, "config.json"), encoding="utf-8") as f:
            wc = json.load(f).get("wechat", {})
    except Exception:
        return []
    accounts = wc.get("accounts") or []
    if accounts:
        return accounts
    appid, secret = wc.get("appid", ""), wc.get("secret", "")
    if appid:
        return [{"id": "default", "name": "默认公众号", "appid": appid, "secret": secret}]
    return []


@app.route("/api/articles", methods=["GET"])
def articles():
    if not os.path.exists(UNIFIED_JSON):
        return _err(f"unified_articles.json ������: {UNIFIED_JSON}", status=404)
    try:
        with open(UNIFIED_JSON, encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        return _err(f"��ȡ unified_articles.json ʧ��: {e}", status=500)
    data["articles"] = _fallback_source_category(data.get("articles", []))
    return jsonify(data)


# ---------------------------------------------------------------- /api/templates

@app.route("/api/templates", methods=["GET"])
def templates():
    try:
        with open(SELECTOR_CONFIG, encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception as e:
        return _err(f"读取 selector_config.json 失败: {e}", status=500)

    out = []
    categories = (cfg.get("categories") or {})
    for ctype, block in (cfg.get("content_types") or {}).items():
        label = block.get("label", ctype)
        block_cat = block.get("category", "")
        block_cat_label = categories.get(block_cat, {}).get("label", "")
        for tpl in block.get("templates", []):
            tpl_id = tpl.get("id", "")
            tpl_cat = tpl.get("category") or block_cat
            tpl_cat_label = categories.get(tpl_cat, {}).get("label", "")
            preview = ""
            tpl_path = os.path.join(TEMPLATES_DIR, tpl.get("file", ""))
            try:
                with open(tpl_path, encoding="utf-8") as f:
                    html_text = f.read()
                m = re.search(r"<body[^>]*>(.*)</body>", html_text, re.S | re.I)
                preview = (m.group(1) if m else html_text).strip()[:2000]
            except Exception as e:
                preview = f"<!-- preview unavailable: {e} -->"
            # 本地预览图 /api/tpl-preview/<id>.png（assets/gen_template_previews.py 生成）
            preview_img = f"/api/tpl-preview/{tpl_id}.png"
            if not os.path.isfile(os.path.join(TEMPLATE_PREVIEWS_DIR, f"{tpl_id}.png")):
                preview_img = ""
            out.append({
                "id": tpl_id,
                "name": tpl.get("name", ""),
                "content_type": ctype,
                "content_type_label": label,
                "category": tpl_cat,
                "category_label": tpl_cat_label,
                "category_code": categories.get(tpl_cat, {}).get("code", 0),
                "style": tpl.get("style", ""),
                "description": tpl.get("description", ""),
                "previewHtml": preview,
                "previewImage": preview_img,
            })
    return jsonify({
        "code": 0,
        "categories": [
            {"id": cid, "label": cdef.get("label", cid),
             "code": cdef.get("code", 0)}
            for cid, cdef in categories.items()
        ],
        "templates": out,
    })


# ---------------------------------------------------------------- /api/accounts（公众号账号列表，供前端选择目标）

@app.route("/api/accounts", methods=["GET"])
def accounts():
    """返回可推送的公众号账号列表（不含 appid/secret）。

    [{id, name, appid_masked}]；appid_masked 形如 wxd6****1136，便于前端识别账号。
    """
    out = []
    for acc in _load_wechat_accounts():
        appid = acc.get("appid", "")
        masked = (appid[:3] + "****" + appid[-4:]) if len(appid) >= 7 else ("****" if appid else "")
        out.append({"id": acc.get("id", ""), "name": acc.get("name", ""),
                    "appid_masked": masked, "configured": bool(appid)})
    return jsonify({"code": 0, "accounts": out})


# ---------------------------------------------------------------- /api/img（图片代理，绕过防盗链）

@app.route("/api/img", methods=["GET"])
def img_proxy():
    url = (request.args.get("url") or "").strip()
    if not url or not url.startswith(("http://", "https://")):
        return _err("missing or invalid url", status=400)
    try:
        resp = requests.get(url, headers=_IMG_HEADERS, timeout=20, stream=True)
        if resp.status_code != 200:
            return _err(f"fetch failed: HTTP {resp.status_code}", status=502)
        ctype = resp.headers.get("Content-Type", "application/octet-stream")
        if not ctype.startswith("image/"):
            ctype = "image/jpeg"
        data = resp.raw.read(8 * 1024 * 1024)  # 上限 8MB
        return send_file(__import__("io").BytesIO(data), mimetype=ctype,
                         max_age=86400)
    except Exception as e:
        return _err(f"proxy error: {e}", status=502)


# ---------------------------------------------------------------- /api/tpl-preview（模板本地预览图）

@app.route("/api/tpl-preview/<name>", methods=["GET"])
def tpl_preview(name):
    safe = os.path.basename(name)
    path = os.path.join(TEMPLATE_PREVIEWS_DIR, safe)
    if not os.path.isfile(path):
        return _err("preview not found", status=404)
    return send_from_directory(TEMPLATE_PREVIEWS_DIR, safe, max_age=86400)


# ---------------------------------------------------------------- /api/submit

@app.route("/api/submit", methods=["POST"])
def submit():
    data = request.get_json(silent=True) or {}
    article_id = data.get("article_id")
    template_id = data.get("template_id")
    account_id = data.get("account_id") or ""
    if not article_id or not template_id:
        return _err("missing article_id or template_id", status=400)

    wait = _load_state().get("waitUrl")
    if not wait:
        return _err("no waitUrl registered")

    try:
        with open(UNIFIED_JSON, encoding="utf-8") as f:
            arts = json.load(f).get("articles", [])
    except Exception as e:
        return _err(f"读取 unified_articles.json 失败: {e}", status=500)

    art = next((a for a in arts if a.get("id") == article_id), None)
    if not art:
        return _err(f"article not found: {article_id}", status=404)

    try:
        html = fetch_html.fetch(art.get("url", ""))
    except Exception as e:
        return _err(str(e), status=502)

    cat = _template_category_code(template_id)
    # 目标公众号：前端可选传 account_id；未传时取第一个已配置账号
    target_acc = next((a for a in _load_wechat_accounts() if a.get("id") == account_id), None)
    if account_id and not target_acc:
        return _err(f"account not found: {account_id}", status=404)
    if not target_acc:
        target_acc = next((a for a in _load_wechat_accounts() if a.get("appid")), None)
    target_name = target_acc.get("name", "") if target_acc else ""

    # 记录本次选定的公众号，/api/publish 缺省 target_account 时兜底使用
    state = _load_state()
    state["publish_account"] = (target_acc or {}).get("id", "")
    state["publish_template_id"] = template_id
    state["saved_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    _save_state(state)

    payload = {
        "article_id": article_id,
        "title": art.get("title", ""),
        "url": art.get("url", ""),
        "html": html,
        "template_id": template_id,
        "template_category": cat.get("id", "other"),
        "template_category_label": cat.get("label", "其他"),
        "template_category_code": cat.get("code", 0),
        "target_account": (target_acc or {}).get("id", ""),
        "target_account_name": target_name,
    }
    try:
        requests.post(wait, json=payload, timeout=30)
    except Exception as e:
        return _err(f"POST waitUrl 失败: {e}", status=502)
    return jsonify({"code": 0, "msg": f"submitted {article_id} to waitUrl"})


# ---------------------------------------------------------------- /api/publish

@app.route("/api/publish", methods=["POST"])
def publish():
    data = request.get_json(silent=True)
    if not data:
        return _err("missing or invalid JSON body", status=400)
    try:
        from renderers import render_article
        from publish import push_to_draft
        # 前端 /api/submit 选定的模板兜底：n8n 大模型若丢了 template_id 也能套上
        if not data.get("template_id"):
            data["template_id"] = _load_state().get("publish_template_id")
        html = render_article(data)
        account_id = data.get("target_account") or _load_state().get("publish_account") or None
        media_id = push_to_draft(data.get("title", ""), html,
                                 digest=data.get("digest", ""),
                                 account_id=account_id)
    except Exception as e:
        app.logger.exception("publish failed")
        return _err(str(e), status=500)
    return jsonify({"code": 0, "media_id": media_id})


# ---------------------------------------------------------------- 前端静态托管

@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def frontend(path):
    """托管 wxcheck/dist 产物（存在时）；/api/* 由上方具体路由优先匹配。"""
    from flask import send_from_directory
    if not os.path.isdir(FRONTEND_DIST):
        return _err(f"前端产物不存在: {FRONTEND_DIST}（请先在 wxcheck 执行 npm run build，或使用 vite dev）",
                    status=404)
    if path and os.path.isfile(os.path.join(FRONTEND_DIST, path)):
        return send_from_directory(FRONTEND_DIST, path)
    return send_from_directory(FRONTEND_DIST, "index.html")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, threaded=True)
