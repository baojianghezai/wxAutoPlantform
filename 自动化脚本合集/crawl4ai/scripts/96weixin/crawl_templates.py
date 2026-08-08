# -*- coding: utf-8 -*-
"""抓取 96微信编辑器 个人账号收藏的模板（复用 login_96weixin.py 的登录态）。

用法：
    python crawl_templates.py [--out 输出目录] [--max 最多数量] [--sleep 每页间隔秒]

流程：
    1) POST /material/tpl?v=3&t=1（fav=1，我的收藏）分页取模板列表（id/标题/VIP等级）
    2) 逐条 POST /indexajax/tplinfo 取模板 HTML
    3) 按 选出来/*.html 的格式包裹（顶部信息条 + .wrap），保存到输出目录
    4) 生成 manifest.json 记录抓取结果

输出目录默认：自动化脚本合集/templates/96_import/
"""
import argparse
import asyncio
import json
import os
import re
import time
import urllib.parse

from crawl4ai import AsyncWebCrawler, BrowserConfig

BASE = os.path.dirname(os.path.abspath(__file__))
PROFILE = os.path.join(BASE, ".browser_profile")
DEFAULT_OUTPUT = os.path.normpath(os.path.join(BASE, "..", "..", "..", "templates", "96_import"))

LIST_URL = "/material/tpl?v=3&t=1"
INFO_URL = "/indexajax/tplinfo"

WRAP_HEAD = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}（ID {tpl_id}）</title>
<style>
  body{{font-family:-apple-system,BlinkMacSystemFont,'Microsoft YaHei',sans-serif;background:#f2f2f2;margin:0;padding:16px;}}
  .bar{{max-width:677px;margin:0 auto 12px;font-size:13px;color:#888;line-height:1.6;}}
  .bar b{{color:#07c160;}}
  .wrap{{max-width:677px;margin:0 auto;background:#fff;padding:16px;box-shadow:0 1px 4px rgba(0,0,0,.08);overflow:hidden;}}
</style>
</head>
<body>
<div class="bar">模板ID: <b>{tpl_id}</b> · 标题: {title} · VIP等级: {vip} · 来源: 96微信编辑器 bj.96weixin.com</div>
<div class="wrap">
{body}
</div>
</body>
</html>
"""


def sanitize_filename(name):
    name = re.sub(r'[\\/:*?"<>|\r\n\t]+', "_", name)
    name = re.sub(r"\s+", " ", name).strip(" .")
    return name[:80] or "untitled"


def wrap_template(tpl_id, title, vip, info):
    """复刻首页 JS 的处理：取 info 外层 _editor/_editor_bg，无则包一层，再打上 data-tpl-id。"""
    body = (info or "").strip()
    if not body:
        return ""
    if not re.match(r"^\s*<section[^>]*class=\"[^\"]*_editor", body):
        body = '<section class="_editor">' + body + "</section>"
    body = re.sub(
        r'(class="[^"]*_editor(_bg)?[^"]*")',
        lambda m: m.group(1) + f' data-tpl-id="{tpl_id}"',
        body, count=1)
    title_esc = (title or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return WRAP_HEAD.format(title=title_esc, tpl_id=tpl_id, vip=vip or "", body=body)


async def _page_of(crawler):
    bm = crawler.crawler_strategy.browser_manager
    ctx = bm.default_context or bm.browser.contexts[0]
    return ctx.pages[0] if ctx.pages else await ctx.new_page()


async def fetch_tpl_page(page, p, params=None):
    """POST /material/tpl?v=3&t=1 取一页收藏模板列表 HTML。"""
    base = {
        "jieri": "0", "hangye": "0", "sort": "addtime", "p": str(p), "q": "",
        "color": "0", "fav": "1", "bought": "0", "vip_level": "0",
        "is_design": "0", "new": "0", "tplrecent_ids": "",
    }
    if params:
        base.update(params)
    body = urllib.parse.urlencode(base)
    return await page.evaluate("""async ({url, body}) => {
        const r = await fetch(url, {
            method: 'POST',
            headers: {'Content-Type': 'application/x-www-form-urlencoded'},
            body: body
        });
        return {ok: r.ok, status: r.status, text: await r.text()};
    }""", {"url": LIST_URL, "body": body})


def parse_tpl_list(html):
    """从列表 HTML 提取 [{'id','title','vip','thumb'}]。

    接口返回结构：<li data-id data-vip data-title data-time ...><img src>...</li>
    """
    items = []
    for m in re.finditer(r'<li\b[^>]*>', html):
        tag = m.group(0)
        if 'data-id="' not in tag:
            continue
        idm = re.search(r'data-id="(\d+)"', tag)
        vipm = re.search(r'data-vip="(\d+)"', tag)
        tm = re.search(r'data-title="([^"]*)"', tag)
        if not idm:
            continue
        items.append({
            "id": idm.group(1),
            "vip": vipm.group(1) if vipm else "",
            "title": (tm.group(1) if tm else "").strip(),
        })
    return items


async def fetch_tpl_info(page, tpl_id):
    """POST /indexajax/tplinfo 取模板 HTML，返回 dict(status/info/tplinfo)。"""
    return await page.evaluate("""async ({url, id}) => {
        const r = await fetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded',
                'X-Requested-With': 'XMLHttpRequest'
            },
            body: 'id=' + encodeURIComponent(id)
        });
        return await r.json();
    }""", {"url": INFO_URL, "id": tpl_id})


async def main():
    parser = argparse.ArgumentParser(description="抓取 96微信 收藏模板")
    parser.add_argument("--out", default=DEFAULT_OUTPUT, help="输出目录")
    parser.add_argument("--max", type=int, default=0, help="最多抓取数量（0=全部）")
    parser.add_argument("--sleep", type=float, default=0.5, help="每页请求间隔秒")
    args = parser.parse_args()

    os.makedirs(args.out, exist_ok=True)

    browser_cfg = BrowserConfig(
        headless=True,
        use_persistent_context=True,
        user_data_dir=PROFILE,
        viewport={"width": 1280, "height": 900},
        java_script_enabled=True,
        verbose=False,
    )
    crawler = AsyncWebCrawler(config=browser_cfg)
    await crawler.start()
    manifest = {"fetched_at": time.strftime("%Y-%m-%d %H:%M:%S"), "items": [], "errors": []}
    try:
        page = await _page_of(crawler)
        await page.goto("https://bj.96weixin.com/", wait_until="domcontentloaded", timeout=60000)
        logged = await page.evaluate("window._96Config && window._96Config.AlreadyLogin === true")
        if not logged:
            print("未检测到登录态，请先运行 python login_96weixin.py 扫码登录。")
            return

        seen_ids = set()
        p = 1
        while True:
            res = await fetch_tpl_page(page, p)
            if not res.get("ok"):
                print(f"  [x] 第{p}页请求失败 HTTP {res.get('status')}")
                break
            items = parse_tpl_list(res.get("text", ""))
            new_items = [it for it in items if it["id"] not in seen_ids]
            print(f"  第{p}页：解析到 {len(items)} 条，新增 {len(new_items)} 条")
            if not new_items:
                break
            for it in new_items:
                seen_ids.add(it["id"])
                manifest["items"].append(it)
            if args.max and len(manifest["items"]) >= args.max:
                break
            p += 1
            await asyncio.sleep(args.sleep)

        total = len(manifest["items"])
        print(f"\n共 {total} 个收藏模板，开始逐个抓取 HTML ...")
        for i, it in enumerate(manifest["items"], 1):
            try:
                info = await fetch_tpl_info(page, it["id"])
                if info.get("status") != 1:
                    msg = f"{it['id']} 获取失败: {str(info.get('info', info))[:120]}"
                    print(f"  [x] [{i}/{total}] {msg}")
                    manifest["errors"].append({"id": it["id"], "title": it["title"], "msg": msg})
                    continue
                html = wrap_template(it["id"], it["title"], it["vip"], info.get("info", ""))
                if not html:
                    manifest["errors"].append({"id": it["id"], "title": it["title"], "msg": "空HTML"})
                    continue
                fname = f"{it['id']}_{sanitize_filename(it['title'])}.html"
                with open(os.path.join(args.out, fname), "w", encoding="utf-8") as f:
                    f.write(html)
                it["file"] = fname
                print(f"  [ok] [{i}/{total}] {it['title']} -> {fname}")
            except Exception as e:
                print(f"  [x] [{i}/{total}] {it['id']} 异常: {e}")
                manifest["errors"].append({"id": it["id"], "title": it["title"], "msg": str(e)})
            await asyncio.sleep(args.sleep)

        with open(os.path.join(args.out, "manifest.json"), "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)
        print(f"\n完成：成功 {total - len(manifest['errors'])}，失败 {len(manifest['errors'])}")
        print(f"输出目录：{os.path.abspath(args.out)}")
    finally:
        await crawler.close()


if __name__ == "__main__":
    asyncio.run(main())
