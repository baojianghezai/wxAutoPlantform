#!/usr/bin/env python3
"""信源爬虫配置与汇总页生成器。"""
import os
import re
import json
import asyncio
from datetime import datetime
from urllib.parse import urljoin

try:
    from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig
except ImportError:
    print("请先安装 crawl4ai：pip install crawl4ai")
    exit(1)

BASE = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE, "xinjiang_output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

browser_config = BrowserConfig(headless=True)
crawler_config = CrawlerRunConfig(cache_mode="BYPASS", wait_for_images=True)

SOURCES = [
    # 政策法规信源
    {"name": "中华人民共和国中央人民政府（国务院）", "url": "https://www.gov.cn", "type": "政策法规", "selector": "a[href*='zhengce']", "pattern": r"/zhengce/[^\"'>\s]+"},
    {"name": "人力资源和社会保障部", "url": "https://www.mohrss.gov.cn", "type": "政策法规", "selector": "a[href*='2026']", "pattern": r"\.gov\.cn/[^\"'>\s]+"},
    {"name": "国家税务总局", "url": "https://www.chinatax.gov.cn", "type": "政策法规", "selector": "a[href*='2026']", "pattern": r"\.gov\.cn/[^\"'>\s]+"},
    {"name": "司法部", "url": "https://www.moj.gov.cn", "type": "政策法规", "selector": "a[href*='2026']", "pattern": r"\.gov\.cn/[^\"'>\s]+"},
    {"name": "国家医疗保障局", "url": "https://www.nhsa.gov.cn", "type": "政策法规", "selector": "a[href*='2026']", "pattern": r"\.gov\.cn/[^\"'>\s]+"},
    {"name": "国家统计局", "url": "https://www.stats.gov.cn", "type": "政策法规", "selector": "a[href*='2026']", "pattern": r"\.gov\.cn/[^\"'>\s]+"},
    {"name": "最高人民法院", "url": "https://www.court.gov.cn", "type": "政策法规", "selector": "a[href*='xiangqing']", "pattern": r"/zixun/xiangqing/\d+\.html"},
    {"name": "国务院国有资产监督管理委员会", "url": "https://www.sasac.gov.cn", "type": "政策法规", "selector": "a[href*='2026']", "pattern": r"\.gov\.cn/[^\"'>\s]+"},
    {"name": "教育部", "url": "https://www.moe.gov.cn", "type": "政策法规", "selector": "a[href*='2026']", "pattern": r"\.gov\.cn/[^\"'>\s]+"},
    {"name": "全国工商联", "url": "https://www.acfic.org.cn", "type": "政策法规", "selector": "a[href*='2026']", "pattern": r"\.org\.cn/[^\"'>\s]+"},
    {"name": "中国公共招聘网", "url": "https://job.mohrss.gov.cn", "type": "政策法规", "selector": "a[href*='2026']", "pattern": r"\.gov\.cn/[^\"'>\s]+"},
    {"name": "就业在线", "url": "https://www.jobonline.cn", "type": "政策法规", "selector": "a[href*='2026']", "pattern": r"\.cn/[^\"'>\s]+"},
    {"name": "国家发展��革��", "url": "https://www.ndrc.gov.cn", "type": "政策法规", "selector": "a[href*='2026']", "pattern": r"\.gov\.cn/[^\"'>\s]+"},
    {"name": "国家市场监督管理总局", "url": "https://www.samr.gov.cn", "type": "政策法规", "selector": "a[href*='2026']", "pattern": r"\.gov\.cn/[^\"'>\s]+"},
    {"name": "中国人大网", "url": "https://www.npc.gov.cn", "type": "政策法规", "selector": "a[href*='2026']", "pattern": r"\.gov\.cn/[^\"'>\s]+"},
    {"name": "青岛市人力资源和社会保障局", "url": "https://hrss.qingdao.gov.cn", "type": "政策法规", "selector": "a[href*='2026']", "pattern": r"\.gov\.cn/[^\"'>\s]+"},
    {"name": "中国法律服务网", "url": "https://www.12348.gov.cn", "type": "政策法规", "selector": "a[href*='2026']", "pattern": r"\.gov\.cn/[^\"'>\s]+"},
    {"name": "中国裁判文书网", "url": "https://wenshu.court.gov.cn", "type": "政策法规", "selector": "a[href*='2026']", "pattern": r"\.gov\.cn/[^\"'>\s]+"},
    # 科技学术信源
    {"name": "中国科学院", "url": "https://www.cas.cn", "type": "科技学术", "selector": "a[href*='2026']", "pattern": r"\.cas\.cn/[^\"'>\s]+"},
    {"name": "清华大学经济管理学院", "url": "https://www.sem.tsinghua.edu.cn", "type": "科技学术", "selector": "a[href*='2026']", "pattern": r"\.edu\.cn/[^\"'>\s]+"},
    {"name": "北京大学光华管理学院", "url": "https://www.gsm.pku.edu.cn", "type": "科技学术", "selector": "a[href*='2026']", "pattern": r"\.edu\.cn/[^\"'>\s]+"},
    {"name": "中国人民大学劳动人事学院", "url": "https://slhr.ruc.edu.cn", "type": "科技学术", "selector": "a[href*='2026']", "pattern": r"\.edu\.cn/[^\"'>\s]+"},
    {"name": "《管理世界》", "url": "https://www.mwm.net.cn", "type": "科技学术", "selector": "a[href*='2026']", "pattern": r"\.net\.cn/[^\"'>\s]+"},
    {"name": "《南开管理评论》", "url": "https://nbr.nankai.edu.cn", "type": "科技学术", "selector": "a[href*='2026']", "pattern": r"\.edu\.cn/[^\"'>\s]+"},
    {"name": "《中国人力资源开发》", "url": "https://www.chrdm.com", "type": "科技学术", "selector": "a[href*='2026']", "pattern": r"\.com/[^\"'>\s]+"},
    {"name": "《哈佛商业评论》中文版", "url": "https://www.hbr-caijing.com", "type": "科技学术", "selector": "a[href*='2026']", "pattern": r"\.com/[^\"'>\s]+"},
    {"name": "MIT Sloan Management Review", "url": "https://sloanreview.mit.edu", "type": "科技学术", "selector": "a[href*='2026']", "pattern": r"\.edu/[^\"'>\s]+"},
    {"name": "国家自然科学基金委员会", "url": "https://www.nsfc.gov.cn", "type": "科技学术", "selector": "a[href*='2026']", "pattern": r"\.gov\.cn/[^\"'>\s]+"},
    # 企业行业信源
    {"name": "华为", "url": "https://www.huawei.com", "type": "企业行业", "selector": "a[href*='2026']", "pattern": r"\.com/[^\"'>\s]+"},
    {"name": "腾讯", "url": "https://www.tencent.com", "type": "企业行业", "selector": "a[href*='2026']", "pattern": r"\.com/[^\"'>\s]+"},
    {"name": "阿里巴巴集团", "url": "https://www.alibabagroup.com", "type": "企业行业", "selector": "a[href*='2026']", "pattern": r"\.com/[^\"'>\s]+"},
    {"name": "字节跳动", "url": "https://www.bytedance.com", "type": "企业行业", "selector": "a[href*='2026']", "pattern": r"\.com/[^\"'>\s]+"},
    {"name": "德勤中国", "url": "https://www.deloitte.com/cn", "type": "企业行业", "selector": "a[href*='2026']", "pattern": r"\.com/[^\"'>\s]+"},
    {"name": "麦肯锡（McKinsey）", "url": "https://www.mckinsey.com.cn", "type": "企业行业", "selector": "a[href*='2026']", "pattern": r"\.com\.cn/[^\"'>\s]+"},
    {"name": "光辉国际（Korn Ferry）", "url": "https://www.kornferry.com", "type": "企业行业", "selector": "a[href*='2026']", "pattern": r"\.com/[^\"'>\s]+"},
    {"name": "美世（Mercer）", "url": "https://www.mercer.com.cn", "type": "企业行业", "selector": "a[href*='2026']", "pattern": r"\.com\.cn/[^\"'>\s]+"},
    {"name": "36氪", "url": "https://www.36kr.com", "type": "企业行业", "selector": "a[href*='/p/']", "pattern": r"/p/\d+"},
    {"name": "虎嗅", "url": "https://www.huxiu.com", "type": "企业行业", "selector": "a[href*='/article/']", "pattern": r"/article/\d+"},
    {"name": "猎聘", "url": "https://www.liepin.com", "type": "企业行业", "selector": "a[href*='/news/']", "pattern": r"/news/\d+"},
    {"name": "智联招聘", "url": "https://www.zhaopin.com", "type": "企业行业", "selector": "a[href*='2026']", "pattern": r"\.com/[^\"'>\s]+"},
    {"name": "BOSS直聘研究院", "url": "https://www.zhipin.com", "type": "企业行业", "selector": "a[href*='2026']", "pattern": r"\.com/[^\"'>\s]+"},
    {"name": "Gartner", "url": "https://www.gartner.com", "type": "企业行业", "selector": "a[href*='2026']", "pattern": r"\.com/[^\"'>\s]+"},
    {"name": "IDC中国", "url": "https://www.idc.com.cn", "type": "企业行业", "selector": "a[href*='2026']", "pattern": r"\.com\.cn/[^\"'>\s]+"},
    # 自媒体社群信源（部分有官网的）
    {"name": "三茅人力资源网", "url": "https://www.hrloo.com", "type": "自媒体社群", "selector": "a[href*='/article/']", "pattern": r"/article/\d+"},
    {"name": "人力资源智享会（HREC）", "url": "https://www.hrec.com.cn", "type": "自媒体社群", "selector": "a[href*='2026']", "pattern": r"\.com\.cn/[^\"'>\s]+"},
    {"name": "任向晖（明道云）", "url": "https://www.runbing.com", "type": "自媒体社群", "selector": "a[href*='/post/']", "pattern": r"/post/\d+"},
    {"name": "KnowYourself", "url": "https://www.knowyourself.cc", "type": "自媒体社群", "selector": "a[href*='/article/']", "pattern": r"/article/\d+"},
]


async def crawl_source(source):
    """爬取单个信源的链接列表。"""
    results = []
    try:
        async with AsyncWebCrawler(config=browser_config) as crawler:
            result = await crawler.arun(source["url"], config=crawler_config)
            if result.success:
                # 使用正则提取链接
                links = list(dict.fromkeys(re.findall(source.get("pattern", r'https?://[^"\'>\s]+'), result.markdown)))
                results = links[:20]  # 限制前20条
            else:
                print(f"  ✘ {source['name']}: {result.error_message}")
    except Exception as e:
        print(f"  ✘ {source['name']}: {e}")
    return source["name"], source["type"], results


async def main():
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    summary = []
    
    print(f"开始爬取 {len(SOURCES)} 个信源...")
    for i, source in enumerate(SOURCES, 1):
        print(f"[{i}/{len(SOURCES)}] {source['name']}")
        name, stype, links = await crawl_source(source)
        summary.append({"name": name, "type": stype, "url": source["url"], "links": links})
        print(f"    找到 {len(links)} 条链接")
    
    # 保存汇总数据
    data_path = os.path.join(OUTPUT_DIR, f"信源汇总_{timestamp}.json")
    with open(data_path, "w", encoding="utf-8") as f:
        json.dump({"crawl_time": datetime.now().strftime("%Y-%m-%d %H:%M"), "sources": summary}, f, ensure_ascii=False, indent=2)
    print(f"\n汇总数据已保存: {data_path}")
    
    # 生成汇总页
    html_path = os.path.join(OUTPUT_DIR, f"信源汇总页_{timestamp}.html")
    generate_html(summary, html_path, timestamp)
    print(f"汇总页已生成: {html_path}")


def generate_html(summary, path, timestamp):
    """生成汇总 HTML 页面。"""
    rows = []
    for src in summary:
        for link in src["links"]:
            rows.append(f"""
            <tr>
                <td>{src['name']}</td>
                <td>{src['type']}</td>
                <td><a href="{link}" target="_blank">{link}</a></td>
            </tr>""")
    
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>信源汇总页 - {timestamp}</title>
    <style>
        body {{ font-family: -apple-system, "Microsoft YaHei", sans-serif; max-width: 1200px; margin: 0 auto; padding: 20px; }}
        h1 {{ color: #1F4E78; border-bottom: 2px solid #1F4E78; padding-bottom: 10px; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
        th, td {{ border: 1px solid #ddd; padding: 10px; text-align: left; }}
        th {{ background: #1F4E78; color: white; }}
        tr:nth-child(even) {{ background: #f5f8fc; }}
        a {{ color: #2E6DA4; text-decoration: none; }}
        a:hover {{ text-decoration: underline; }}
        .stats {{ margin: 20px 0; padding: 15px; background: #f7f9fb; border-radius: 8px; }}
    </style>
</head>
<body>
    <h1>📊 信源内容汇总页</h1>
    <div class="stats">
        <strong>生成时间：</strong>{datetime.now().strftime('%Y-%m-%d %H:%M')}<br>
        <strong>信源总数：</strong>{len(summary)} 个<br>
        <strong>链接总数：</strong>{sum(len(s['links']) for s in summary)} 条
    </div>
    <table>
        <thead>
            <tr>
                <th>信源名称</th>
                <th>类型</th>
                <th>原文链接</th>
            </tr>
        </thead>
        <tbody>
            {''.join(rows)}
        </tbody>
    </table>
</body>
</html>"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)


if __name__ == "__main__":
    asyncio.run(main())
