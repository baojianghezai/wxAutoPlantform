#!/usr/bin/env python3
"""爬取 court.gov.cn 的司法解释和典型案例，转为 Markdown。"""
import asyncio
import re
import os
from datetime import datetime
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig

BASE = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE, "court_output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

browser_config = BrowserConfig(headless=True)
crawler_config = CrawlerRunConfig(cache_mode="BYPASS", wait_for_images=True)


async def crawl_list(url_pattern, list_url):
    """爬取列表页，提取详情链接。"""
    async with AsyncWebCrawler(config=browser_config) as crawler:
        result = await crawler.arun(list_url, config=crawler_config)
        if not result.success:
            print(f"  ✘ 列表页失败: {result.error_message}")
            return []
        links = list(dict.fromkeys(re.findall(url_pattern, result.markdown)))
        print(f"  ✔ 列表页找到 {len(links)} 条链接")
        return links


async def crawl_detail(url):
    """爬取详情页，返回 markdown 内容。"""
    async with AsyncWebCrawler(config=browser_config) as crawler:
        result = await crawler.arun(url, config=crawler_config)
        if not result.success:
            print(f"    ✘ 详情页失败: {url} - {result.error_message}")
            return None
        return result.markdown


async def main():
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # 1. 司法解释
    print("【司法解释】")
    sifa_links = await crawl_list(
        r'https://www\.court\.gov\.cn/fabu/xiangqing/\d+\.html',
        'https://www.court.gov.cn/fabu/gengduo/16.html'
    )
    sifa_md = []
    for i, link in enumerate(sifa_links, 1):
        print(f"  爬取 ({i}/{len(sifa_links)}): {link}")
        md = await crawl_detail(link)
        if md:
            sifa_md.append(md)
    
    # 保存司法解释
    if sifa_md:
        path = os.path.join(OUTPUT_DIR, f"司法解释_{timestamp}.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"# 司法解释（共 {len(sifa_md)} 条）\n\n")
            f.write(f"> 爬取时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n")
            f.write("---\n\n".join(sifa_md))
        print(f"  ✔ 已保存: {path}")
    
    # 2. 典型案例
    print("\n【典型案例】")
    anli_links = await crawl_list(
        r'https://www\.court\.gov\.cn/zixun/xiangqing/\d+\.html',
        'https://www.court.gov.cn/zixun/gengduo/104.html'
    )
    anli_md = []
    for i, link in enumerate(anli_links, 1):
        print(f"  爬取 ({i}/{len(anli_links)}): {link}")
        md = await crawl_detail(link)
        if md:
            anli_md.append(md)
    
    # 保存典型案例
    if anli_md:
        path = os.path.join(OUTPUT_DIR, f"典型案例_{timestamp}.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"# 典型案例（共 {len(anli_md)} 条）\n\n")
            f.write(f"> 爬取时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n")
            f.write("---\n\n".join(anli_md))
        print(f"  ✔ 已保存: {path}")
    
    print(f"\n完成！共爬取 司法解释 {len(sifa_md)} 条，典型案例 {len(anli_md)} 条")
    print(f"输出目录: {OUTPUT_DIR}")


if __name__ == "__main__":
    asyncio.run(main())
