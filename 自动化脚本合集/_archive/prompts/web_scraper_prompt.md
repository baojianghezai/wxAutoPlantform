# 网页抓取脚本生成 prompt

## 背景
用户需要从指定网址抓取信息，并生成一个可独立运行的 Python 脚本。
脚本要求：
- 仅使用 Python 标准库 + 已安装的可执行工具
- 输出结构化 JSON 索引 + HTML 浏览页
- 原始页面缓存到本地
- 适合人工审核或后续 AI 处理

## 已验证可行的技术方案

### 1. 静态页面直接抓取
适用场景：目标页面为静态 HTML，数据直接写在源码中。
技术栈：`urllib.request` + 正则/HTML 解析。
关键点：
- 设置 `User-Agent` 绕过基础反爬
- 使用 `cache_path(url)` 基于 URL 哈希存储原始 HTML
- 页面标题提取优先用 `<meta name="ArticleTitle">`，回退到 `<title>`
- 正文清洗：去除 `<script>/<style>`，去掉 HTML 标签，`html.unescape`，压缩空白

### 2. 动态页面使用 web2md 渲染
适用场景：目标页面为 JS 动态加载，静态抓取拿不到数据。
工具：`web2md.exe`（已安装在 `C:\Users\18089\.workbuddy\binaries\python\versions\3.13.12\Scripts\web2md.exe`）
调用方式：
```python
import subprocess
cmd = [WEB2MD_CMD, url, save_dir, "--depth", "1", "--count", "10"]
res = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
```
web2md 输出为 Markdown 文件，路径规则：
`{save_dir}/{域名_路径}.md`，例如 `listflfg.html.md`

### 3. 浏览器自动化（Playwright）
适用场景：需要点击、登录、滚动触发数据加载。
注意：当前环境 Playwright 安装后浏览器二进制删除失败，**优先使用 web2md**，必要时再用 Playwright。
如必须使用：
```python
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto(url, timeout=30000)
    page.wait_for_timeout(3000)
    # 操作页面...
    browser.close()
```

## 脚本结构模板

```python
# -*- coding: utf-8 -*-
"""
抓取脚本说明
"""
import json, os, re, hashlib, html as html_mod
from datetime import datetime, timezone, timedelta
import urllib.request
import subprocess

BASE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(BASE, "output_dir")
CACHE_DIR = os.path.join(OUT_DIR, "cache")
os.makedirs(OUT_DIR, exist_ok=True)
os.makedirs(CACHE_DIR, exist_ok=True)

# ====== 配置 ======
TARGET_URLS = [
    "https://example.com/list.html",
]
WEB2MD_CMD = os.environ.get("WEB2MD_CMD", r"C:\Users\18089\.workbuddy\binaries\python\versions\3.13.12\Scripts\web2md.exe")

# ====== 工具函数 ======
def fetch(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read(), None

def cache_path(url):
    h = hashlib.md5(url.encode()).hexdigest()
    return os.path.join(CACHE_DIR, f"{h}.html")

def save_cache(url, data):
    with open(cache_path(url), "wb") as f:
        f.write(data)

def clean_text(h):
    h = re.sub(r'<(script|style)[^>]*>.*?</\\1>', ' ', h, flags=re.S | re.I)
    t = re.sub(r'<[^>]+>', ' ', h)
    t = html_mod.unescape(t)
    return re.sub(r'\\s+', ' ', t).strip()

def extract_title(html_bytes, fallback_url):
    text = html_bytes.decode("utf-8", errors="ignore")
    m = re.search(r'<meta[^>]+name=["\']ArticleTitle["\'][^>]+content=["\']([^"\']+)["\']', text, re.I)
    if m:
        return html_mod.unescape(m.group(1).strip())
    m = re.search(r'<title>(.*?)</title>', text, re.I | re.S)
    if m:
        t = re.sub(r'<[^>]+>', '', m.group(1)).strip()
        if t and t != "通用标题":
            return t
    return fallback_url

# ====== 解析函数（根据目标页面结构定制）=====
def parse_static_list(html_bytes):
    """解析静态列表页，返回 [(title, link, pub_date), ...]"""
    text = html_bytes.decode("utf-8", errors="ignore")
    items = []
    for m in re.finditer(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', text, re.S | re.I):
        href = m.group(1)
        title = re.sub(r'<[^>]+>', '', m.group(2)).strip()
        if title and len(title) > 5:
            items.append((title, href, ""))
    return items

def parse_web2md_list(md_path):
    """解析 web2md 生成的 markdown 列表页"""
    items = []
    with open(md_path, "r", encoding="utf-8") as f:
        text = f.read()
    # 根据实际 web2md 输出格式调整正则
    pattern = re.compile(r"- \\d+\\s+\\[([^\\]]+)\\]\\(([^)]+)\\)\\s+(.+?)\\s+(\\d{4}-\\d{2}-\\d{2})")
    for m in pattern.finditer(text):
        items.append({
            "title": m.group(1),
            "link": m.group(2),
            "docno": m.group(3).strip(),
            "pub_date": m.group(4),
        })
    return items

# ====== 主流程 ======
def main():
    NOW = datetime.now(timezone(timedelta(hours=8)))
    NOW_STR = NOW.strftime("%Y-%m-%d %H:%M")
    all_items = []
    seen_links = set()

    # 1. 静态抓取
    for url in TARGET_URLS:
        data, err = fetch(url)
        if data:
            save_cache(url, data)
            items = parse_static_list(data)
            for title, link, pub_date in items:
                if link in seen_links:
                    continue
                seen_links.add(link)
                detail, _ = fetch(link)
                if detail:
                    body = clean_text(detail.decode("utf-8", errors="ignore"))
                    title_final = extract_title(detail, title)
                else:
                    title_final = title
                all_items.append({
                    "title": title_final,
                    "link": link,
                    "source": "静态列表",
                    "pub_date": pub_date,
                    "tags": [],  # 可选：主题标签
                    "cached": bool(detail),
                })

    # 2. web2md 渲染抓取（如需要）
    # ...

    # 3. 去重 + 按时间排序
    uniq = []
    seen = set()
    for it in all_items:
        if it['link'] not in seen:
            seen.add(it['link'])
            uniq.append(it)
    uniq.sort(key=lambda x: x.get('pub_date', ''), reverse=True)

    # 4. 写 JSON
    index_json = {
        "generated_at": NOW_STR,
        "count": len(uniq),
        "items": uniq,
    }
    json_path = os.path.join(OUT_DIR, "index.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(index_json, f, ensure_ascii=False, indent=2)

    # 5. 写 HTML
    html_path = os.path.join(OUT_DIR, "index.html")
    gen_html(uniq, html_path)

    print(f"Done. {len(uniq)} items indexed.")

def gen_html(items, out_path):
    # 生成简化 HTML 浏览页
    now_str = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M")
    p = []
    p.append(f"""<!doctype html><html lang=zh><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>抓取结果</title>
<style>
 body{{font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;margin:0;background:#f5f6f8;color:#222}}
 header{{background:#1F4E78;color:#fff;padding:18px 24px}}
 header h1{{margin:0;font-size:20px}} header p{{margin:6px 0 0;opacity:.85;font-size:13px}}
 .wrap{{max-width:960px;margin:0 auto;padding:20px}}
 .card{{background:#fff;border-radius:10px;box-shadow:0 1px 4px rgba(0,0,0,.08);margin:14px 0;padding:16px}}
 .title{{font-size:16px;font-weight:700;margin:6px 0}}
 .meta{{color:#888;font-size:12px;margin:4px 0}}
 .links a{{color:#1F4E78;font-size:12px;margin-right:10px;text-decoration:none}}
 .empty{{text-align:center;color:#888;padding:60px}}
</style></head><body>
<header><h1>抓取结果</h1>
<p>生成时间：{now_str} ｜ 共 {len(items)} 条</p></header>
<div class=wrap>
""")
    if not items:
        p.append('<div class="empty">本次未抓取到内容。</div>')
    for it in items:
        p.append(f"""
<div class=card>
 <div class=title>{it['title']}</div>
 <div class=meta>来源：{it.get('source', '')} ｜ 发布时间：{it.get('pub_date', '未知')}</div>
 <div class=links><a href="{it['link']}" target=_blank>查看原文</a></div>
</div>""")
    p.append('</div></body></html>')
    with open(out_path, "w", encoding="utf-8") as f:
        f.write('\n'.join(p))

if __name__ == "__main__":
    main()
```

## 关键注意事项

1. **web2md 路径**：Windows 下默认安装到 `Scripts/web2md.exe`，需用绝对路径调用
2. **编码问题**：web2md URL 含中文时需 encode，否则报 `ascii codec can't encode`
3. **标题提取**：chinatax 等站点用 `<meta name="ArticleTitle">`，不要只看 `<title>`
4. **排序**：有日期的按日期降序，无日期的沉底
5. **去重**：按 link 去重，保留第一次出现的条目
6. **缓存**：原始 HTML/web2md markdown 都缓存，避免重复请求

## 输出物

- `output_dir/index.json` — 结构化数据，供 AI 读取
- `output_dir/index.html` — 人工审核页面
- `output_dir/cache/` — 原始页面缓存

## 使用方式

```bash
python script_name.py
```

## 扩展方向

- 如需分页抓取，调整 web2md 的 `--count` 或循环调用静态分页 URL
- 如需登录态，先用 Playwright 登录后导出 cookie，再注入到 `urllib` 请求头
- 如需定时运行，可配置 workbuddy automation
