#!/usr/bin/env python3
"""信源文章爬虫：从Excel规划表提取信源，定向爬取文章标题、日期、链接，生成汇总页。"""
import os
import re
import json
import asyncio
from datetime import datetime
from urllib.parse import urljoin, urlparse

try:
    from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig
except ImportError:
    print("请先安装 crawl4ai：pip install crawl4ai")
    exit(1)

BASE = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE, "xinjiang_output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

browser_config = BrowserConfig(headless=True)
crawler_config = CrawlerRunConfig(cache_mode="BYPASS", wait_for_images=True, page_timeout=30000)

# 信源配置：基于名硕人力公众号_内容信源规划表.xlsx
# 只保留能稳定爬取的站点，��爬站点已标注
SOURCES = [
    # ===== 政策法规信源 =====
    {"name": "国务院", "url": "https://www.gov.cn", "type": "政策法规", "category": "政策法规",
     "pattern": r"/zhengce/(?:content|jiedu)/\d{6}/[^)"'"'"'<>\s]+\.htm",
     "date_in_url": True},
    {"name": "最高人民法院", "url": "https://www.court.gov.cn", "type": "政策法规", "category": "政策法规",
     "pattern": r"/(?:zixun|fabu)/xiangqing/\d+\.html",
     "date_in_md": r'(\d{4}-\d{2}-\d{2})'},
    {"name": "国家税务总局", "url": "https://www.chinatax.gov.cn", "type": "政策法规", "category": "政策法规",
     "pattern": r"\.gov\.cn/[^)"'"'"'<>\s]+\.html",
     "date_in_md": r'(\d{4}-\d{2}-\d{2})'},
    {"name": "司法部", "url": "https://www.moj.gov.cn", "type": "政策法规", "category": "政策法规",
     "pattern": r"\.gov\.cn/[^)"'"'"'<>\s]+\.html",
     "date_in_md": r'(\d{4}-\d{2}-\d{2})'},
    {"name": "国家医疗保障局", "url": "https://www.nhsa.gov.cn", "type": "政策法规", "category": "政策法规",
     "pattern": r"\.gov\.cn/[^)"'"'"'<>\s]+\.html",
     "date_in_md": r'(\d{4}-\d{2}-\d{2})'},
    {"name": "国家统计局", "url": "https://www.stats.gov.cn", "type": "政策法规", "category": "政策法规",
     "pattern": r"\.gov\.cn/[^)"'"'"'<>\s]+\.html",
     "date_in_md": r'(\d{4}-\d{2}-\d{2})'},
    {"name": "教育部", "url": "https://www.moe.gov.cn", "type": "政策法规", "category": "政策法规",
     "pattern": r"\.gov\.cn/[^)"'"'"'<>\s]+\.html",
     "date_in_md": r'(\d{4}-\d{2}-\d{2})'},
    {"name": "全国工商联", "url": "https://www.acfic.org.cn", "type": "政策法规", "category": "政策法规",
     "pattern": r"\.org\.cn/[^)"'"'"'<>\s]+\.html",
     "date_in_md": r'(\d{4}-\d{2}-\d{2})'},
    {"name": "青岛市人社局", "url": "https://hrss.qingdao.gov.cn", "type": "政策法规", "category": "政策法��",
     "pattern": r"\.gov\.cn/[^)"'"'"'<>\s]+\.html",
     "date_in_md": r'(\d{4}-\d{2}-\d{2})'},
    {"name": "中国法律服务网", "url": "https://www.12348.gov.cn", "type": "政策法规", "category": "政策法规",
     "pattern": r"\.gov\.cn/[^)"'"'"'<>\s]+\.html",
     "date_in_md": r'(\d{4}-\d{2}-\d{2})'},
    {"name": "中国裁判文书网", "url": "https://wenshu.court.gov.cn", "type": "政策法规", "category": "政策法规",
     "pattern": r"\.gov\.cn/[^)"'"'"'<>\s]+\.html",
     "date_in_md": r'(\d{4}-\d{2}-\d{2})'},
    # ===== 科技学术信源 =====
    {"name": "中国科学院", "url": "https://www.cas.cn", "type": "科技学术", "category": "科技动态",
     "pattern": r"\.cas\.cn/[^)"'"'"'<>\s]+\.html",
     "date_in_md": r'(\d{4}-\d{2}-\d{2})'},
    {"name": "清华大学经管学院", "url": "https://www.sem.tsinghua.edu.cn", "type": "科技学术", "category": "科技动态",
     "pattern": r"\.edu\.cn/[^)"'"'"'<>\s]+\.html",
     "date_in_md": r'(\d{4}-\d{2}-\d{2})'},
    {"name": "北京大学光华管理学院", "url": "https://www.gsm.pku.edu.cn", "type": "科技学术", "category": "科技动态",
     "pattern": r"\.edu\.cn/[^)"'"'"'<>\s]+\.html",
     "date_in_md": r'(\d{4}-\d{2}-\d{2})'},
    {"name": "中国人民大学劳人院", "url": "https://slhr.ruc.edu.cn", "type": "科技学术", "category": "科技动态",
     "pattern": r"\.edu\.cn/[^)"'"'"'<>\s]+\.html",
     "date_in_md": r'(\d{4}-\d{2}-\d{2})'},
    {"name": "国家自然科学基金委", "url": "https://www.nsfc.gov.cn", "type": "科技学术", "category": "科技动态",
     "pattern": r"\.gov\.cn/[^)"'"'"'<>\s]+\.html",
     "date_in_md": r'(\d{4}-\d{2}-\d{2})'},
    {"name": "《管理世界》", "url": "https://www.mwm.net.cn", "type": "科技学术", "category": "科技动态",
     "pattern": r"\.net\.cn/[^)"'"'"'<>\s]+\.html",
     "date_in_md": r'(\d{4}-\d{2}-\d{2})'},
    {"name": "《南开管理评论》", "url": "https://nbr.nankai.edu.cn", "type": "科技学术", "category": "科技动态",
     "pattern": r"\.edu\.cn/[^)"'"'"'<>\s]+\.html",
     "date_in_md": r'(\d{4}-\d{2}-\d{2})'},
    {"name": "《中国人力资源开发》", "url": "https://www.chrdm.com", "type": "科技学术", "category": "科技动态",
     "pattern": r"\.com/[^)"'"'"'<>\s]+\.html",
     "date_in_md": r'(\d{4}-\d{2}-\d{2})'},
    {"name": "《哈佛商业评论》中文版", "url": "https://www.hbr-caijing.com", "type": "科技学术", "category": "科技动态",
     "pattern": r"\.com/[^)"'"'"'<>\s]+\.html",
     "date_in_md": r'(\d{4}-\d{2}-\d{2})'},
    # ===== 企业行业信源 =====
    {"name": "华为", "url": "https://www.huawei.com", "type": "企业行业", "category": "行业动态",
     "pattern": r"\.com/[^)"'"'"'<>\s]+\.html",
     "date_in_md": r'(\d{4}-\d{2}-\d{2})'},
    {"name": "腾讯", "url": "https://www.tencent.com", "type": "企业行业", "category": "行业动态",
     "pattern": r"\.com/[^)"'"'"'<>\s]+\.html",
     "date_in_md": r'(\d{4}-\d{2}-\d{2})'},
    {"name": "阿里巴巴", "url": "https://www.alibabagroup.com", "type": "企业行业", "category": "行业动态",
     "pattern": r"\.com/[^)"'"'"'<>\s]+\.html",
     "date_in_md": r'(\d{4}-\d{2}-\d{2})'},
    {"name": "字节跳动", "url": "https://www.bytedance.com", "type": "企业行业", "category": "行业动态",
     "pattern": r"\.com/[^)"'"'"'<>\s]+\.html",
     "date_in_md": r'(\d{4}-\d{2}-\d{2})'},
    {"name": "德勤中国", "url": "https://www.deloitte.com/cn", "type": "企业行业", "category": "行业动态",
     "pattern": r"\.com/[^)"'"'"'<>\s]+\.html",
     "date_in_md": r'(\d{4}-\d{2}-\d{2})'},
    {"name": "麦肯锡", "url": "https://www.mckinsey.com.cn", "type": "企业行业", "category": "行业动态",
     "pattern": r"\.com\.cn/[^)"'"'"'<>\s]+\.html",
     "date_in_md": r'(\d{4}-\d{2}-\d{2})'},
    {"name": "光辉国际", "url": "https://www.kornferry.com", "type": "企业行业", "category": "行业动态",
     "pattern": r"\.com/[^)"'"'"'<>\s]+\.html",
     "date_in_md": r'(\d{4}-\d{2}-\d{2})'},
    {"name": "美世", "url": "https://www.mercer.com.cn", "type": "企业行业", "category": "行业动态",
     "pattern": r"\.com\.cn/[^)"'"'"'<>\s]+\.html",
     "date_in_md": r'(\d{4}-\d{2}-\d{2})'},
    {"name": "虎嗅", "url": "https://www.huxiu.com", "type": "企业行业", "category": "行业动态",
     "pattern": r"/article/\d+",
     "date_in_md": r'(\d{4}-\d{2}-\d{2})',
     "note": "详情页需人机验证，仅提取链接"},
    {"name": "智联招聘", "url": "https://www.zhaopin.com", "type": "企业行业", "category": "行业动态",
     "pattern": r"\.com/[^)"'"'"'<>\s]+\.html",
     "date_in_md": r'(\d{4}-\d{2}-\d{2})'},
    {"name": "BOSS直聘", "url": "https://www.zhipin.com", "type": "企业行业", "category": "行业动态",
     "pattern": r"\.com/[^)"'"'"'<>\s]+\.html",
     "date_in_md": r'(\d{4}-\d{2}-\d{2})'},
    # ===== 自媒体社群信源 =====
    {"name": "三茅人力资源网", "url": "https://www.hrloo.com", "type": "自媒体社群", "category": "原创实操",
     "pattern": r"/article/\d+",
     "date_in_md": r'(\d{4}-\d{2}-\d{2})'},
    {"name": "KnowYourself", "url": "https://www.knowyourself.cc", "type": "自媒体社群", "category": "原创实操",
     "pattern": r"/article/\d+",
     "date_in_md": r'(\d{4}-\d{2}-\d{2})'},
]

# 并发控制
MAX_CONCURRENT = 5
semaphore = asyncio.Semaphore(MAX_CONCURRENT)


def clean_link(link, base_url):
    """清理链接，移除尾部垃圾字符，转为完整URL。"""
    if not link:
        return None
    link = link.strip().rstrip(')"').rstrip(")'").rstrip(')"')
    if link.startswith('/'):
        parsed = urlparse(base_url)
        link = f"{parsed.scheme}://{parsed.netloc}{link}"
    elif link.startswith('./'):
        link = urljoin(base_url, link)
    if not link.startswith('http'):
        return None
    return link


def extract_articles_from_markdown(md, source):
    """从markdown中提取文章链接列表。"""
    pattern = source.get("pattern", r'https?://[^)"'"'"'<>\s]+')
    links = list(dict.fromkeys(re.findall(pattern, md)))
    cleaned = []
    for link in links:
        url = clean_link(link, source["url"])
        if url:
            cleaned.append(url)
    return cleaned


async def crawl_article_detail(url):
    """爬取文章详情，提取标题和日期。"""
    async with semaphore:
        try:
            async with AsyncWebCrawler(config=browser_config) as crawler:
                result = await crawler.arun(url, config=crawler_config)
                if result.success:
                    title = result.metadata.get("title", "")
                    # 过滤反爬验证页面
                    if any(kw in title for kw in ["验证", "滑动", "人机", "captcha", "verify"]):
                        return None
                    # 尝试从markdown中提取日期
                    date = ""
                    md = result.markdown
                    date_patterns = [
                        r'(\d{4}-\d{2}-\d{2})',
                        r'(\d{4}/\d{2}/\d{2})',
                        r'(\d{4}年\d{1,2}月\d{1,2}日)',
                        r'发布时间[：:]\s*(\d{4}-\d{2}-\d{2})',
                        r'发布日期[：:]\s*(\d{4}-\d{2}-\d{2})',
                    ]
                    for pat in date_patterns:
                        m = re.search(pat, md)
                        if m:
                            date = m.group(1)
                            break
                    return {"title": title, "date": date, "url": url}
        except Exception as e:
            print(f"    ✘ 详情失败: {e}")
        return None


async def crawl_source(source):
    """爬取单个信源的文章列表和详情。"""
    articles = []
    try:
        async with AsyncWebCrawler(config=browser_config) as crawler:
            # 1. 爬取首页
            result = await crawler.arun(source["url"], config=crawler_config)
            if not result.success:
                print(f"  ✘ {source['name']}: {result.error_message}")
                return source["name"], source["type"], source["category"], articles
            
            # 2. 提取文章链接
            raw_links = extract_articles_from_markdown(result.markdown, source)
            print(f"  {source['name']}: 首页找到 {len(raw_links)} 个候选链接")
            
            # 3. 去重并限制数量
            unique_links = list(dict.fromkeys(raw_links))[:10]
            
            # 4. 爬取详情
            tasks = []
            for link in unique_links:
                tasks.append(crawl_article_detail(link))
            details = await asyncio.gather(*tasks, return_exceptions=True)
            
            for detail in details:
                if isinstance(detail, dict) and detail.get("title"):
                    articles.append(detail)
    except Exception as e:
        print(f"  ✘ {source['name']}: {e}")
    
    return source["name"], source["type"], source["category"], articles


def generate_html(summary, path, timestamp):
    """生成按日期排序的汇总页。"""
    # 收集所有文章
    all_articles = []
    for src in summary:
        for art in src.get("articles", []):
            all_articles.append({
                "source": src["name"],
                "type": src["type"],
                "category": src["category"],
                "title": art.get("title", "无标题"),
                "date": art.get("date", ""),
                "url": art.get("url", "#"),
            })
    
    # 按日期排序
    def sort_key(item):
        d = item.get("date", "")
        m = re.search(r'(\d{4}-\d{2}-\d{2})', d)
        if m:
            return m.group(1)
        return "0000-00-00"
    
    all_articles.sort(key=sort_key, reverse=True)
    
    # 生成行
    rows = []
    for art in all_articles:
        rows.append(f"""
            <tr>
                <td>{art['source']}</td>
                <td>{art['category']}</td>
                <td>{art['date']}</td>
                <td><a href="{art['url']}" target="_blank">{art['title']}</a></td>
            </tr>""")
    
    # 分类统计
    category_stats = {}
    for art in all_articles:
        category_stats[art["category"]] = category_stats.get(art["category"], 0) + 1
    
    stats_rows = "".join([f"<tr><td>{k}</td><td>{v}</td></tr>" for k, v in category_stats.items()])
    
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>信源文章汇总页 - {timestamp}</title>
    <style>
        body {{ font-family: -apple-system, "Microsoft YaHei", sans-serif; max-width: 1400px; margin: 0 auto; padding: 20px; }}
        h1 {{ color: #1F4E78; border-bottom: 2px solid #1F4E78; padding-bottom: 10px; }}
        .stats {{ margin: 20px 0; padding: 15px; background: #f7f9fb; border-radius: 8px; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
        th, td {{ border: 1px solid #ddd; padding: 10px; text-align: left; }}
        th {{ background: #1F4E78; color: white; }}
        tr:nth-child(even) {{ background: #f5f8fc; }}
        a {{ color: #2E6DA4; text-decoration: none; }}
        a:hover {{ text-decoration: underline; }}
        .filters {{ margin: 20px 0; padding: 15px; background: #fff; border: 1px solid #ddd; border-radius: 8px; }}
        .filters input {{ padding: 8px; width: 300px; margin-right: 10px; }}
        .filters button {{ padding: 8px 16px; background: #1F4E78; color: white; border: none; border-radius: 4px; cursor: pointer; }}
        .category-stats {{ margin: 20px 0; padding: 15px; background: #fff; border: 1px solid #ddd; border-radius: 8px; }}
        table.stats-table {{ width: auto; border-collapse: collapse; }}
        table.stats-table th, table.stats-table td {{ border: 1px solid #ddd; padding: 6px 12px; }}
        table.stats-table th {{ background: #f0f0f0; color: #333; }}
    </style>
</head>
<body>
    <h1>📊 信源文章汇总页</h1>
    <div class="stats">
        <strong>生成时间：</strong>{datetime.now().strftime('%Y-%m-%d %H:%M')}<br>
        <strong>信源总数：</strong>{len(summary)} 个<br>
        <strong>文章总数：</strong>{len(all_articles)} 条<br>
        <strong>排序方式：</strong>按日期降序（最新在前）
    </div>
    
    <div class="category-stats">
        <strong>分类统计：</strong>
        <table class="stats-table">
            <tr><th>内容板块</th><th>文章数</th></tr>
            {stats_rows}
        </table>
    </div>
    
    <div class="filters">
        <input type="text" id="searchInput" placeholder="搜索标题..." onkeyup="filterTable()">
        <button onclick="filterTable()">搜索</button>
    </div>
    
    <table id="articlesTable">
        <thead>
            <tr>
                <th>信源名称</th>
                <th>内容板块</th>
                <th>发布日期</th>
                <th>文章标题</th>
            </tr>
        </thead>
        <tbody>
            {''.join(rows)}
        </tbody>
    </table>
    
    <script>
        function filterTable() {{
            var input, filter, table, tr, td, i, txtValue;
            input = document.getElementById("searchInput");
            filter = input.value.toUpperCase();
            table = document.getElementById("articlesTable");
            tr = table.getElementsByTagName("tr");
            for (i = 1; i < tr.length; i++) {{
                td = tr[i].getElementsByTagName("td")[3];
                if (td) {{
                    txtValue = td.textContent || td.innerText;
                    if (txtValue.toUpperCase().indexOf(filter) > -1) {{
                        tr[i].style.display = "";
                    }} else {{
                        tr[i].style.display = "none";
                    }}
                }}
            }}
        }}
    </script>
</body>
</html>"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)


async def main():
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    summary = []
    
    print(f"开始爬取 {len(SOURCES)} 个信源...\n")
    for i, source in enumerate(SOURCES, 1):
        print(f"[{i}/{len(SOURCES)}] {source['name']}")
        name, stype, category, articles = await crawl_source(source)
        summary.append({"name": name, "type": stype, "category": category, "url": source["url"], "articles": articles})
        print(f"    → 提取 {len(articles)} 篇文章")
    
    # 保存原始数据
    data_path = os.path.join(OUTPUT_DIR, f"信源文章汇总_{timestamp}.json")
    with open(data_path, "w", encoding="utf-8") as f:
        json.dump({"crawl_time": datetime.now().strftime("%Y-%m-%d %H:%M"), "sources": summary}, f, ensure_ascii=False, indent=2)
    print(f"\n原始数据已保存: {data_path}")
    
    # 生成汇总页
    html_path = os.path.join(OUTPUT_DIR, f"信源文章汇总页_{timestamp}.html")
    generate_html(summary, html_path, timestamp)
    print(f"汇总页已生成: {html_path}")
    
    # 打印统计
    total = sum(len(s.get("articles", [])) for s in summary)
    print(f"\n完成！共 {len(summary)} 个信源，{total} 篇文章")


if __name__ == "__main__":
    asyncio.run(main())
