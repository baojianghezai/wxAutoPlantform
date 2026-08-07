#!/usr/bin/env python3
"""信源定向爬虫：根据配置文件爬取特定方向的文章，生成分方向汇总页。"""
import os
import re
import json
import asyncio
import sys
import argparse
import hashlib
from datetime import datetime
from urllib.parse import urljoin, urlparse

try:
    from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig
except ImportError:
    print("请先安装 crawl4ai：pip install crawl4ai")
    exit(1)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_BASE = os.path.join(SCRIPT_DIR, "xinjiang_output")
os.makedirs(OUTPUT_BASE, exist_ok=True)

browser_config = BrowserConfig(headless=True)
crawler_config = CrawlerRunConfig(cache_mode="BYPASS", wait_for_images=True, page_timeout=30000)

# 反爬关键词过滤
ANTI_CRAWL_KEYWORDS = ["验证", "滑动", "人机", "captcha", "verify", "Cloudflare", "Access Denied"]

# ---------- 前端契约工具函数 ----------
def make_id(url, source_type="web"):
    """根据原文 URL 生成稳定唯一 ID（同一链接多次爬取 ID 不变，便于前端去重与选定回传）。"""
    digest = hashlib.md5((url or "").encode("utf-8")).hexdigest()[:8]
    return f"{source_type}_{digest}"


def normalize_date(raw):
    """将各种日期写法归一化为 YYYY-MM-DD；无法解析返回空字符串。"""
    if not raw:
        return ""
    m = re.search(r"(20\d{2})[-/年.](\d{1,2})[-/月.](\d{1,2})", raw)
    if m:
        y, mo, d = m.groups()
        try:
            return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"
        except ValueError:
            return ""
    return ""


def parse_direction(direction_name):
    """从 '子方向1：劳动法规解读' 解析出 (code, 简短名称)。"""
    code = ""
    short = direction_name
    m = re.search(r"子方向\s*(\d+)", direction_name)
    if m:
        code = m.group(1).zfill(2)
    if "：" in direction_name:
        short = direction_name.split("：", 1)[1].strip()
    elif ":" in direction_name:
        short = direction_name.split(":", 1)[1].strip()
    return code, short


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
    pattern = source.get("pattern", r'https?://[^)"\'<>\s]+')
    links = list(dict.fromkeys(re.findall(pattern, md)))
    cleaned = []
    for link in links:
        url = clean_link(link, source["url"])
        if url:
            cleaned.append(url)
    return cleaned


async def crawl_article_detail(url, semaphore):
    """爬取文章详情，提取标题和日期。"""
    async with semaphore:
        try:
            async with AsyncWebCrawler(config=browser_config) as crawler:
                result = await crawler.arun(url, config=crawler_config)
                if result.success:
                    title = result.metadata.get("title", "")
                    # 过滤反爬验证页面
                    if any(kw in title for kw in ANTI_CRAWL_KEYWORDS):
                        return None
                    md = result.markdown
                    # 尝试从markdown中提取日期
                    date = ""
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


async def crawl_source(source, semaphore):
    """爬取单个信源的文章列表和详情。"""
    articles = []
    try:
        async with AsyncWebCrawler(config=browser_config) as crawler:
            # 1. 爬取首页
            result = await crawler.arun(source["url"], config=crawler_config)
            if not result.success:
                print(f"  ✘ {source['name']}: {result.error_message}")
                return source["name"], source.get("type", ""), source.get("category", ""), articles

            # 2. 提取文章链接
            raw_links = extract_articles_from_markdown(result.markdown, source)
            print(f"  {source['name']}: 首页找到 {len(raw_links)} 个候选链接")

            # 3. 去重并限制数量
            unique_links = list(dict.fromkeys(raw_links))[:10]

            # 4. 爬取详情
            tasks = []
            for link in unique_links:
                tasks.append(crawl_article_detail(link, semaphore))
            details = await asyncio.gather(*tasks, return_exceptions=True)

            for detail in details:
                if isinstance(detail, dict) and detail.get("title"):
                    articles.append(detail)
    except Exception as e:
        print(f"  ✘ {source['name']}: {e}")

    return source["name"], source.get("type", ""), source.get("category", ""), articles


def generate_html(summary, direction_name, timestamp):
    """生成按日期排序的分方向汇总页。"""
    all_articles = []
    for src in summary:
        for art in src.get("articles", []):
            all_articles.append({
                "source": src["name"],
                "type": src.get("type", ""),
                "category": src.get("category", ""),
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
                <td><a href="{art['url']}" target="_blank" rel="noopener">{art['title']}</a></td>
            </tr>""")

    # 信源统计
    source_stats = {}
    for art in all_articles:
        source_stats[art["source"]] = source_stats.get(art["source"], 0) + 1

    stats_rows = "".join([f"<tr><td>{k}</td><td>{v}</td></tr>" for k, v in source_stats.items()])

    # 成功/失败统计
    success_sources = [s for s in summary if s.get("articles")]
    failed_sources = [s for s in summary if not s.get("articles")]
    total_links = sum(len(s.get("articles", [])) for s in summary)

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>{direction_name} - 信源文章汇总</title>
    <style>
        body {{ font-family: -apple-system, "Microsoft YaHei", sans-serif; max-width: 1400px; margin: 0 auto; padding: 20px; }}
        h1 {{ color: #1F4E78; border-bottom: 2px solid #1F4E78; padding-bottom: 10px; }}
        .stats {{ margin: 20px 0; padding: 15px; background: #f7f9fb; border-radius: 8px; }}
        .stats-table {{ width: auto; border-collapse: collapse; }}
        .stats-table th, .stats-table td {{ border: 1px solid #ddd; padding: 6px 12px; }}
        .stats-table th {{ background: #f0f0f0; color: #333; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
        th, td {{ border: 1px solid #ddd; padding: 10px; text-align: left; }}
        th {{ background: #1F4E78; color: white; }}
        tr:nth-child(even) {{ background: #f5f8fc; }}
        a {{ color: #2E6DA4; text-decoration: none; }}
        a:hover {{ text-decoration: underline; }}
        .filters {{ margin: 20px 0; padding: 15px; background: #fff; border: 1px solid #ddd; border-radius: 8px; }}
        .filters input {{ padding: 8px; width: 300px; margin-right: 10px; }}
        .filters button {{ padding: 8px 16px; background: #1F4E78; color: white; border: none; border-radius: 4px; cursor: pointer; }}
        .back-link {{ margin: 10px 0; }}
        .back-link a {{ color: #1F4E78; font-weight: bold; }}
        .status {{ margin: 10px 0; padding: 10px; border-radius: 4px; }}
        .status.success {{ background: #d4edda; color: #155724; }}
        .status.warning {{ background: #fff3cd; color: #856404; }}
    </style>
</head>
<body>
    <div class="back-link">
        <a href="../信源文章汇总页_综合.html">&larr; 返回综合汇总页</a>
    </div>
    <h1>📊 {direction_name}</h1>
    <div class="stats">
        <strong>生成时间：</strong>{datetime.now().strftime('%Y-%m-%d %H:%M')}<br>
        <strong>信源总数：</strong>{len(summary)} 个<br>
        <strong>成功爬取：</strong>{len(success_sources)} 个<br>
        <strong>爬取失败：</strong>{len(failed_sources)} 个<br>
        <strong>文章总数：</strong>{len(all_articles)} 条<br>
        <strong>排序方式：</strong>按日期降序（最新在前）
    </div>

    <div class="status {'success' if success_sources else 'warning'}">
        <strong>爬取状态：</strong>
        {' | '.join([f"✓ {s['name']}({len(s.get('articles', []))}篇)" for s in success_sources])}
        {' | '.join([f"✗ {s['name']}" for s in failed_sources])}
    </div>

    <div style="margin: 20px 0; padding: 15px; background: #fff; border: 1px solid #ddd; border-radius: 8px;">
        <strong>信源统计：</strong>
        <table class="stats-table">
            <tr><th>信源名称</th><th>文章数</th></tr>
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
            {''.join(rows) if rows else '<tr><td colspan="4" style="text-align:center;color:#999;">暂无文章数据</td></tr>'}
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
    return html


async def main():
    parser = argparse.ArgumentParser(description='定向信源爬虫')
    parser.add_argument('--config', required=True, help='配置文件路径')
    parser.add_argument('--output', required=True, help='输出HTML文件路径')
    parser.add_argument('--json', required=True, help='输出JSON文件路径')
    args = parser.parse_args()

    # 读取配置
    with open(args.config, 'r', encoding='utf-8') as f:
        config = json.load(f)

    direction_name = config.get("direction_name", "未知方向")
    sources = config.get("sources", [])
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    max_concurrent = config.get("max_concurrent", 5)
    semaphore = asyncio.Semaphore(max_concurrent)

    print(f"\n{'='*60}")
    print(f"方向：{direction_name}")
    print(f"信源数：{len(sources)}")
    print(f"{'='*60}\n")

    summary = []
    for i, source in enumerate(sources, 1):
        print(f"[{i}/{len(sources)}] {source['name']} ({source['url']})")
        name, stype, category, articles = await crawl_source(source, semaphore)
        summary.append({
            "name": name,
            "type": stype,
            "category": category,
            "url": source["url"],
            "articles": articles
        })
        print(f"    → 提取 {len(articles)} 篇文章")

    # ---------- 扁平化为前端契约格式 ----------
    direction_code, direction_short = parse_direction(direction_name)
    # 分类下沉：web 文章按方向配置的 source_category 归类（recruitment/agriculture），
    # 未配置时默认 recruitment（当前方向均与招聘/HR 相关）。
    source_category = config.get("source_category", "recruitment")
    flat_articles = []
    for src in summary:
        for art in src.get("articles", []):
            flat_articles.append({
                "id": make_id(art.get("url", ""), "web"),
                "title": art.get("title", "无标题"),
                "source": src["name"],
                "source_type": "web",
                "direction": direction_short,
                "category": src.get("category", ""),
                "source_category": source_category,
                "published_at": normalize_date(art.get("date", "")),
                "url": art.get("url", "#"),
                "summary": "",
                "thumbnail": "",
            })

    # 保存前端契约 JSON
    payload = {
        "schema_version": "1.0",
        "source_system": "web_crawler",
        "scope": "direction",
        "generated_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S+08:00"),
        "direction": {
            "code": direction_code,
            "name": direction_short,
            "category": summary[0].get("category", "") if summary else "",
        },
        "stats": {
            "source_total": len(summary),
            "source_ok": sum(1 for s in summary if s.get("articles")),
            "article_total": len(flat_articles),
        },
        "articles": flat_articles,
    }
    with open(args.json, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    # 生成HTML（人工浏览用，字段与 JSON 一致）
    html = generate_html(summary, direction_name, timestamp)
    with open(args.output, 'w', encoding='utf-8') as f:
        f.write(html)

    total = sum(len(s.get("articles", [])) for s in summary)
    success = sum(1 for s in summary if s.get("articles"))
    print(f"\n✓ {direction_name} 完成！成功 {success}/{len(sources)} 个信源，共 {total} 篇文章")
    print(f"  HTML: {args.output}")
    print(f"  JSON: {args.json}")


if __name__ == "__main__":
    asyncio.run(main())
