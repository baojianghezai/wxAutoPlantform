# -*- coding: utf-8 -*-
"""96微信编辑器 扫码登录（crawl4ai 持久化浏览器）。

用法：
    python login_96weixin.py

流程：打开真实浏览器窗口 → 用户扫码登录 → 登录态自动保存到 .browser_profile，
后续 crawl_templates.py 复用该登录态（无需再扫码）。
"""
import asyncio
import os
import time

from crawl4ai import AsyncWebCrawler, BrowserConfig

BASE = os.path.dirname(os.path.abspath(__file__))
PROFILE = os.path.join(BASE, ".browser_profile")


async def _page_of(crawler):
    """拿到持久化浏览器里的 playwright page（crawl4ai 底层同一实例）。"""
    bm = crawler.crawler_strategy.browser_manager
    ctx = bm.default_context or bm.browser.contexts[0]
    return ctx.pages[0] if ctx.pages else await ctx.new_page()


async def main():
    browser_cfg = BrowserConfig(
        headless=False,
        use_persistent_context=True,
        user_data_dir=PROFILE,
        viewport={"width": 1280, "height": 900},
        java_script_enabled=True,
        verbose=False,
    )
    crawler = AsyncWebCrawler(config=browser_cfg)
    await crawler.start()
    try:
        page = await _page_of(crawler)
        await page.goto("https://bj.96weixin.com/", wait_until="domcontentloaded", timeout=60000)
        print("浏览器已打开，请在弹出的窗口扫码登录（登录成功后脚本自动继续）...")

        deadline = time.time() + 300
        last_reload = time.time()
        while time.time() < deadline:
            logged = await page.evaluate(
                "window._96Config && window._96Config.AlreadyLogin === true")
            if logged:
                break
            if time.time() - last_reload > 60:
                last_reload = time.time()
                await page.reload(wait_until="domcontentloaded")
                print("· 刷新页面，等待登录态生效...")
            await asyncio.sleep(2)
        else:
            print("等待登录超时（5分钟），请重试。")
            return

        print("登录成功！登录态已保存到:", PROFILE)

        # 验证能访问收藏：请求收藏列表第一页
        data = await page.evaluate("""async () => {
            const body = new URLSearchParams({
                jieri: '0', hangye: '0', sort: 'addtime', p: '1', q: '',
                color: '0', fav: '1', bought: '0', vip_level: '0',
                is_design: '0', new: '0', tplrecent_ids: ''
            });
            const r = await fetch('/material/tpl?v=3&t=1', {
                method: 'POST',
                headers: {'Content-Type': 'application/x-www-form-urlencoded'},
                body: body.toString()
            });
            return {ok: r.ok, status: r.status, text: await r.text()};
        }""")
        html = data.get("text", "")
        ids = re.findall(r'class="style-item"[^>]*data-id="(\d+)"', html)
        print(f"收藏模板列表可访问，第1页发现 {len(ids)} 个模板（如为0，请检查账号收藏或登录态）。")
    finally:
        await crawler.close()


if __name__ == "__main__":
    import re
    asyncio.run(main())
