# -*- coding: utf-8 -*-
"""为模板 HTML 生成本地预览截图（Playwright，带 Referer 以绕过 96weixin 防盗链）。

用法：python gen_template_previews.py
输出：../assets/template-previews/<template_id>.png
"""
import asyncio
import json
import os
import sys

import requests
from playwright.async_api import async_playwright

BASE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE)
TEMPLATES_DIR = os.path.join(PROJECT_ROOT, "templates")
OUT_DIR = os.path.join(PROJECT_ROOT, "assets", "template-previews")

CONFIG = {
    "zhaopin1": "选出来/招聘1.html",
    "zhaopin2": "选出来/招聘2.html",
    "xiaoshu": "选出来/节气-大暑.html",
}


def _load_templates():
    """从 selector_config.json 读取模板文件路径（优先用配置，保证 id 对齐）。"""
    cfg_path = os.path.join(TEMPLATES_DIR, "selector_config.json")
    if not os.path.exists(cfg_path):
        return CONFIG
    with open(cfg_path, encoding="utf-8") as f:
        cfg = json.load(f)
    out = {}
    for block in (cfg.get("content_types") or {}).values():
        for tpl in block.get("templates", []):
            out[tpl["id"]] = tpl["file"]
    return out or CONFIG


async def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    tasks = _load_templates()
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        ctx = await browser.new_context(
            viewport={"width": 390, "height": 700},
            extra_http_headers={"Referer": "https://bj.96weixin.com/"},
        )
        page = await ctx.new_page()
        for tpl_id, rel in tasks.items():
            html_path = os.path.join(TEMPLATES_DIR, rel)
            if not os.path.exists(html_path):
                print(f"[skip] {tpl_id}: {rel} 不存在")
                continue
            url = "file:///" + html_path.replace("\\", "/")
            try:
                await page.goto(url, wait_until="networkidle", timeout=30000)
            except Exception as e:
                print(f"[warn] {tpl_id} networkidle: {e}")
                await page.goto(url, wait_until="load", timeout=30000)
            await page.wait_for_timeout(1500)
            # 截取正文容器（不含顶部说明条 .bar）
            el = page.locator(".wrap").first
            clip = None
            if await el.count() > 0:
                box = await el.bounding_box()
                if box:
                    clip = {
                        "x": box["x"], "y": box["y"],
                        "width": min(box["width"], 390), "height": min(box["height"], 1400),
                    }
            out_path = os.path.join(OUT_DIR, f"{tpl_id}.png")
            if clip:
                await page.screenshot(path=out_path, clip=clip)
            else:
                await page.screenshot(path=out_path)
            print(f"[ok] {tpl_id} -> {out_path} ({os.path.getsize(out_path)} bytes)")
        await browser.close()
    print("done")


if __name__ == "__main__":
    asyncio.run(main())
