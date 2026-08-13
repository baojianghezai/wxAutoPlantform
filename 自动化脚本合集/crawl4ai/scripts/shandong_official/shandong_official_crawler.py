#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""山东官方招聘网站爬虫（crawl4ai 驱动）。

数据源：官方招聘网站.docx 整理出的 68 个网址（省级人社/人事考试/卫健委 + 16地市的人社/教育/卫健委/文旅局招聘搜索页）。
这些搜索页大多用 JS 动态加载结果，因此用 crawl4ai 的真实浏览器渲染后提取链接。

产出（shandong_output/ 目录）：
  - 山东官方招聘_综合.json   前端契约格式（与 xinjiang web 侧一致，可被 combine 合并）
  - 山东官方招聘_综合.html   人工浏览汇总页

用法：
  python shandong_official_crawler.py [--config sources_config.json] [--limit 10]
  --limit N   每个信源最多取 N 条（默认 0 = 不限制，但最多抓取站内全部）
后续新增网址：直接往 sources_config.json 的 sources 数组加一条 {name,url,group,...} 即可，无需改代码。

链接提取策略（每站自动判定，也可在 source 里手动指定 extractor）：
  - markdown     : 解析 crawl4ai 输出的 markdown 链接 [标题](URL)（默认，大多数站）
  - visit_do     : 链接是 visit/link.do?url=xxx 包装，需还原 url 参数（淄博/东营/济宁/泰安/威海等）
  - javascript   : 链接是 javascript:;，标题和真实链接藏在 <a> 标签（青岛 unionsearch）
"""
import argparse
import asyncio
import hashlib
import json
import os
import re
from datetime import datetime, timedelta
from urllib.parse import unquote, urljoin

try:
    from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig
except ImportError:
    print("请先安装 crawl4ai：pip install crawl4ai")
    exit(1)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "shandong_output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

browser_config = BrowserConfig(headless=True)
run_config = CrawlerRunConfig(
    cache_mode="BYPASS",
    wait_for_images=False,
    page_timeout=25000,
    wait_until="networkidle",
    js_code="await new Promise(r=>setTimeout(r,6000))",
    verbose=False,
)

# 反爬 / 无意义页面关键词
ANTI_KEYWORDS = ["Access Denied", "安全验证", "访问过于频繁", "请输入验证码", "请完成验证",
                 "滑块验证", "人机验证", "验证码错误"]

# 标题命中关键词（招聘相关）
TITLE_KEYWORDS = ["招聘", "招录", "遴选", "选调", "招募", "引进", "聘用", "聘任",
                  "拟聘", "录用", "公示", "公告", "简章", "岗位", "报名", "补充公告"]

# 标题排除关键词（导航/栏目等噪声）
TITLE_EXCLUDE = ["首页", "上页", "下页", "尾页", "无障碍", "设为首页", "加入收藏",
                 "网站地图", "关于我们", "联系我们", "政府信息公开指南"]

# 日期在标题末尾：形如 "xxx公告2026-08-05" / "xxx 2026年8月5日"
DATE_IN_TITLE = r"(20\d{2})[-/年.](\d{1,2})[-/月.](\d{1,2})"


def make_id(url, source_type="web"):
    digest = hashlib.md5((url or "").encode("utf-8")).hexdigest()[:8]
    return f"{source_type}_{digest}"


def normalize_date(raw):
    """从文本提取日期 -> YYYY-MM-DD。"""
    if not raw:
        return ""
    m = re.search(DATE_IN_TITLE, raw)
    if m:
        y, mo, d = m.groups()
        try:
            return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}"
        except ValueError:
            return ""
    return ""


def clean_title(t):
    """清洗标题：去掉首尾空白、去除末尾日期、去除拆字空格、压缩多余空格。"""
    if not t:
        return ""
    t = re.sub(DATE_IN_TITLE + r"\s*$", "", t.strip())
    t = re.sub(r"[\u4e00-\u9fff]\s+(?=[\u4e00-\u9fff])", "", t)  # 中文间空格（拆字）
    t = re.sub(r"\s+", " ", t).strip()
    t = t.strip()
    return t


def is_recruitment_title(title):
    """判断标题是否招聘相关且非导航噪声。"""
    if not title or len(title) < 4:
        return False
    if any(k in title for k in TITLE_EXCLUDE):
        return False
    return any(k in title for k in TITLE_KEYWORDS)


def is_index_page(url):
    """过滤栏目索引页/导航页：URL 以 index.html 结尾，或指向栏目根（无文章 ID 特征）。"""
    if not url:
        return True
    if re.search(r"/index(?:_\d+)?\.html?$", url):
        return True
    # 指向栏目列表根（末级路径即栏目），如 wsdw/index_7179.html、gsgg/index_7179.html
    if re.search(r"/[a-z0-9_]+/index(?:_\d+)?\.html?$", url):
        return True
    return False


def extract_visit_do(url):
    """还原 visit/link.do?url=<urlencode(真实地址)>。"""
    m = re.search(r"[?&]url=([^&]+)", url)
    if m:
        return unquote(m.group(1))
    return url


def normalize_link(url, base):
    """转成绝对 URL。"""
    if not url:
        return None
    url = url.strip()
    # 去掉 markdown 链接尾部的 "title" 部分：URL "文章标题" 或 URL 中文标题
    m = re.match(r"(https?://\S+?)\s+['\"]?(?:[^'\"]*)['\"]?$", url)
    if m and re.search(r"[\u4e00-\u9fff'\"]", url):
        url = m.group(1)
    if url.startswith("javascript"):
        return None
    if url.startswith("//"):
        url = "https:" + url
    elif url.startswith("/"):
        from urllib.parse import urlparse
        p = urlparse(base)
        url = f"{p.scheme}://{p.netloc}{url}"
    elif not url.startswith("http"):
        url = urljoin(base, url)
    if not url.startswith("http"):
        return None
    return url


def pick_extractor(source, html, md):
    """自动判定链接提取器：优先 source.extractor 手动指定，否则按特征判断。"""
    ex = source.get("extractor", "")
    if ex:
        return ex
    if "visit/link.do" in html and re.search(r'jsearchfront', html):
        return "visit_do"
    js_count = len(re.findall(r'href="javascript:;"', html))
    http_count = len(re.findall(r'href="https?://', html))
    # 青岛 unionsearch / 纯 javascript 链接站：js 占多数
    if js_count > 0 and js_count >= http_count:
        return "javascript"
    return "markdown"


# ---------------------------------------------------------------- 提取器

def extract_markdown(md, base, limit):
    """标准 markdown 链接提取：[(标题, URL)]。"""
    out = []
    for m in re.finditer(r'\[([^\]]{2,80})\]\(([^)]+)\)', md):
        title = m.group(1).strip()
        url = m.group(2).strip()
        url = normalize_link(url, base)
        title = clean_title(title)
        if not url or not is_recruitment_title(title):
            continue
        date = normalize_date(m.group(0)) or normalize_date(title)
        out.append({"title": title, "url": url, "date": date})
        if limit and len(out) >= limit:
            break
    return out


def extract_visit_do_md(md, base, limit):
    """visit/link.do 包装链接提取。"""
    out = []
    for m in re.finditer(r'\[([^\]]{2,80})\]\(([^)]+)\)', md):
        title = m.group(1).strip()
        raw_url = m.group(2).strip()
        if "visit/link.do" in raw_url or "link.do" in raw_url:
            url = extract_visit_do(raw_url)
        else:
            url = raw_url
        url = normalize_link(url, base)
        title = clean_title(title)
        if not url or not is_recruitment_title(title):
            continue
        date = normalize_date(title)
        out.append({"title": title, "url": url, "date": date})
        if limit and len(out) >= limit:
            break
    return out


def extract_javascript(html, base, limit):
    """青岛 unionsearch：链接 href=javascript:;，真实链接在 data-link，标题在 title 属性。"""
    out = []
    for m in re.finditer(
        r'<a[^>]+(?:data-link="(https?://[^"]+)"|title="([^"]+)"|href="javascript:;")[^>]*>',
        html):
        tag = m.group(0)
        url = re.search(r'data-link="(https?://[^"]+)"', tag)
        title = re.search(r'title="([^"]+)"', tag)
        if not url or not title:
            continue
        u = url.group(1)
        t = clean_title(title.group(1))
        if not u or not is_recruitment_title(t):
            continue
        u = normalize_link(u, base)
        if not u:
            continue
        date = normalize_date(t)
        out.append({"title": t, "url": u, "date": date})
        if limit and len(out) >= limit:
            break
    return out


EXTRACTORS = {
    "markdown": extract_markdown,
    "visit_do": extract_visit_do_md,
    "javascript": extract_javascript,
}


async def crawl_source(crawler, source, limit):
    """爬取单个信源：加载页面 -> 提取招聘文章链接列表。"""
    name = source["name"]
    url = source["url"]
    try:
        result = await crawler.arun(url, config=run_config)
        if not result.success:
            return {"name": name, "url": url, "ok": False,
                    "error": result.error_message or "加载失败", "articles": []}
        html = result.html or ""
        md = result.markdown or ""
        title = (result.metadata or {}).get("title", "") or ""

        # 反爬检测
        if any(k in (md[:1500] + title) for k in ANTI_KEYWORDS):
            return {"name": name, "url": url, "ok": False, "error": "反爬拦截", "articles": []}

        extractor = pick_extractor(source, html, md)
        fn = EXTRACTORS.get(extractor, extract_markdown)
        articles = fn(md if extractor != "javascript" else html, url, limit)
        # 过滤栏目索引页/导航页
        articles = [a for a in articles if not is_index_page(a["url"])]

        return {"name": name, "url": url, "ok": True, "extractor": extractor,
                "error": "", "articles": articles}
    except Exception as e:
        return {"name": name, "url": url, "ok": False, "error": str(e)[:120], "articles": []}


def generate_html(summary):
    """生成人工浏览汇总页。"""
    rows = []
    stats = []
    ok = [s for s in summary if s["ok"] and s["articles"]]
    fail = [s for s in summary if not (s["ok"] and s["articles"])]
    for s in summary:
        stats.append(f"<tr><td>{s['name']}</td><td>{len(s['articles'])}</td>"
                     f"<td>{s.get('extractor','')}</td>"
                     f"<td>{'✓' if s['ok'] else '✗ '+s.get('error','')}</td></tr>")
        for a in s["articles"]:
            rows.append(f"<tr><td>{s['name']}</td><td>{a['date']}</td>"
                        f"<td><a href='{a['url']}' target='_blank'>{a['title']}</a></td></tr>")
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="UTF-8"><title>山东官方招聘网站汇总</title>
<style>
body{{font-family:-apple-system,'Microsoft YaHei',sans-serif;max-width:1400px;margin:0 auto;padding:20px;}}
h1{{color:#1F4E78;border-bottom:2px solid #1F4E78;padding-bottom:10px;}}
.stats{{margin:20px 0;padding:15px;background:#f7f9fb;border-radius:8px;}}
table{{width:100%;border-collapse:collapse;margin-top:20px;}}
th,td{{border:1px solid #ddd;padding:8px;text-align:left;font-size:14px;}}
th{{background:#1F4E78;color:#fff;}}
tr:nth-child(even){{background:#f5f8fc;}}
a{{color:#2E6DA4;text-decoration:none;}}
</style></head>
<body>
<h1>山东官方招聘网站 · 汇总</h1>
<div class="stats">
<strong>生成时间：</strong>{datetime.now().strftime('%Y-%m-%d %H:%M')}<br>
<strong>信源总数：</strong>{len(summary)}　<strong>成功：</strong>{len(ok)}　<strong>失败：</strong>{len(fail)}<br>
<strong>文章总数：</strong>{len(rows)} 条
</div>
<h2>信源状态</h2>
<table><tr><th>信源</th><th>文章数</th><th>提取器</th><th>状态</th></tr>{''.join(stats)}</table>
<h2>文章列表</h2>
<table><tr><th>信源</th><th>日期</th><th>标题</th></tr>
{''.join(rows) if rows else '<tr><td colspan=3>无</td></tr>'}</table>
</body></html>"""
    return html


async def main():
    parser = argparse.ArgumentParser(description="山东官方招聘网站爬虫")
    parser.add_argument("--config", default=os.path.join(SCRIPT_DIR, "sources_config.json"))
    parser.add_argument("--limit", type=int, default=0, help="每信源最多取 N 条（0=不限制）")
    parser.add_argument("--only", default="", help="只爬指定 sub（rsj/edu/wjw/wlj/province），逗号分隔")
    parser.add_argument("--days", type=int, default=10, help="只保留近 N 天内的文章（0=不过滤）")
    args = parser.parse_args()

    with open(args.config, encoding="utf-8") as f:
        cfg = json.load(f)
    sources = [s for s in cfg.get("sources", []) if s.get("enabled", True)]
    if args.only:
        only = set(args.only.split(","))
        sources = [s for s in sources if s.get("sub") in only or s.get("category") in only]

    print(f"\n{'='*60}\n山东官方招聘网站爬虫：{len(sources)} 个信源\n{'='*60}")
    sem = asyncio.Semaphore(cfg.get("max_concurrent", 3))

    async def _wrap(crawler, src):
        async with sem:
            return await crawl_source(crawler, src, args.limit)

    async with AsyncWebCrawler(config=browser_config) as crawler:
        summary = []
        for i, src in enumerate(sources, 1):
            print(f"[{i}/{len(sources)}] {src['name']} ...")
            res = await _wrap(crawler, src)
            summary.append(res)
            print(f"    → {'✓' if res['ok'] else '✗ '+res.get('error','')} "
                  f"提取 {len(res['articles'])} 条"
                  + (f" ({res['extractor']})" if res["ok"] else ""))

    # ---------- 产出前端契约 JSON ----------
    flat = []
    for src in summary:
        for a in src.get("articles", []):
            flat.append({
                "id": make_id(a["url"], "web"),
                "title": a["title"],
                "source": src["name"],
                "source_type": "web",
                "direction": "山东官方招聘",
                "category": "",
                "source_category": cfg.get("source_category", "recruitment"),
                "published_at": a.get("date", ""),
                "url": a["url"],
                "summary": "",
                "thumbnail": "",
            })
    # 按日期降序、去重
    flat.sort(key=lambda x: x.get("published_at") or "0000-00-00", reverse=True)

    # 过期筛选：仅保留近 days 天内的文章（published_at 解析失败或为空视为未知，默认保留）
    if args.days and args.days > 0:
        cutoff = (datetime.now() - timedelta(days=args.days)).strftime("%Y-%m-%d")
        flat = [a for a in flat if not a.get("published_at") or a["published_at"] >= cutoff]

    seen = set()
    dedup = []
    for a in flat:
        if a["id"] in seen:
            continue
        seen.add(a["id"])
        dedup.append(a)

    payload = {
        "schema_version": "1.0",
        "source_system": "web_crawler",
        "scope": "shandong_official",
        "generated_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S+08:00"),
        "direction": {"code": "sd_official", "name": "山东官方招聘", "category": "recruitment"},
        "stats": {
            "source_total": len(summary),
            "source_ok": sum(1 for s in summary if s["ok"] and s["articles"]),
            "article_total": len(dedup),
        },
        "articles": dedup,
    }
    json_path = os.path.join(OUTPUT_DIR, "山东官方招聘_综合.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    html_path = os.path.join(OUTPUT_DIR, "山东官方招聘_综合.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(generate_html(summary))

    print(f"\n✓ 完成！成功 {payload['stats']['source_ok']}/{len(summary)} 个信源，共 {len(dedup)} 篇文章")
    print(f"  JSON: {json_path}")
    print(f"  HTML: {html_path}")


if __name__ == "__main__":
    asyncio.run(main())
