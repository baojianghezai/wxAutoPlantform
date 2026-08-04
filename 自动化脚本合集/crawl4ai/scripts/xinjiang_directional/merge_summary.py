#!/usr/bin/env python3
"""综合汇总页生成器：合并所有分方向的 JSON 结果，生成带导航的总汇总页 + 统一契约 JSON。

输出 JSON 与单方向 crawler.py 的输出保持同一契约（见《爬虫接口文档.md》）：
- 顶层 articles 为扁平数组，前端始终遍历 articles 即可
- scope="all" 时额外提供 directions 汇总与 stats.direction_total
"""
import os
import re
import json
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "..", "xinjiang_output")

DIRECTIONS = [
    {"id": 1, "name": "劳动法规解读", "file": "子方向1_劳动法规解读.json", "category": "政策法规"},
    {"id": 2, "name": "社保税务新政", "file": "子方向2_社保税务新政.json", "category": "政策法规"},
    {"id": 3, "name": "地方人才政策", "file": "子方向3_地方人才政策.json", "category": "政策法规"},
    {"id": 4, "name": "就业促进政策", "file": "子方向4_就业促进政策.json", "category": "政策法规"},
    {"id": 5, "name": "AI+HR应用", "file": "子方向5_AI_HR应用.json", "category": "科技动态"},
    {"id": 6, "name": "人才测评技术", "file": "子方向6_人才测评技术.json", "category": "科技动态"},
    {"id": 7, "name": "HR SaaS产品迭代", "file": "子方向7_HR_SaaS产品迭代.json", "category": "科技动态"},
    {"id": 8, "name": "数字化转型", "file": "子方向8_数字化转型.json", "category": "科技动态"},
    {"id": 9, "name": "大厂组织变革", "file": "子方向9_大厂组织变革.json", "category": "行业动态"},
    {"id": 10, "name": "薪酬福利创新", "file": "子方向10_薪酬福利创新.json", "category": "行业动态"},
    {"id": 11, "name": "灵活用工/蓝领HR", "file": "子方向11_灵活用工.json", "category": "行业动态"},
    {"id": 12, "name": "招聘市场趋势", "file": "子方向12_招聘市场趋势.json", "category": "行业动态"},
    {"id": 13, "name": "HR模块干货", "file": "子方向13_HR模块干货.json", "category": "原创实操"},
    {"id": 15, "name": "员工关系/合规", "file": "子方向15_员工关系合规.json", "category": "原创实操"},
    {"id": 16, "name": "企业文化/领导力", "file": "子方向16_企业文化领导力.json", "category": "原创实操"},
]


def extract_articles(payload):
    """从分方向 JSON 中提取扁平 articles（兼容新旧两种格式）。"""
    arts = []
    # 新格式：顶层 articles 已是扁平数组
    if payload.get("articles"):
        return payload["articles"]
    # 旧格式：sources[].articles 嵌套
    for src in payload.get("sources", []):
        for art in src.get("articles", []):
            arts.append({
                "id": "web_" + str(abs(hash(art.get("url", ""))) & 0xffffffff)[:8],
                "title": art.get("title", "无标题"),
                "source": src.get("name", ""),
                "source_type": "web",
                "direction": payload.get("direction", "") if isinstance(payload.get("direction"), str) else "",
                "category": src.get("category", ""),
                "published_at": (re.search(r'(\d{4}-\d{2}-\d{2})', art.get("date", "")).group(1)
                                 if re.search(r'(\d{4}-\d{2}-\d{2})', art.get("date", "")) else ""),
                "url": art.get("url", "#"),
                "summary": "",
                "thumbnail": "",
            })
    return arts


def load_all_articles():
    """加载所有分方向 JSON，返回 (articles_flat, directions_meta)。"""
    all_articles = []
    directions_meta = []
    for d in DIRECTIONS:
        json_path = os.path.join(OUTPUT_DIR, d["file"])
        if not os.path.exists(json_path):
            continue
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                payload = json.load(f)
        except Exception as e:
            print(f"Warning: failed to load {d['file']}: {e}")
            continue
        arts = extract_articles(payload)
        for a in arts:
            a.setdefault("direction", d["name"])
            a.setdefault("category", d["category"])
            a.setdefault("source_type", "web")
        all_articles.extend(arts)
        dir_obj = payload.get("direction", {})
        if isinstance(dir_obj, dict):
            code = dir_obj.get("code", f"{d['id']:02d}")
            name = dir_obj.get("name", d["name"])
        else:
            code = f"{d['id']:02d}"
            name = d["name"]
        directions_meta.append({
            "code": code,
            "name": name,
            "category": d["category"],
            "article_count": len(arts),
        })
    return all_articles, directions_meta


def sort_articles(articles):
    def key(a):
        m = re.search(r'(\d{4}-\d{2}-\d{2})', a.get("published_at", ""))
        return m.group(1) if m else "0000-00-00"
    articles.sort(key=key, reverse=True)
    return articles


def generate_html(articles, directions_meta):
    """生成综合汇总页（人工浏览用）。"""
    # 分类统计
    category_stats = {}
    for a in articles:
        cat = a.get("category", "")
        category_stats[cat] = category_stats.get(cat, 0) + 1

    # 方向导航
    nav_by_category = {}
    for dm in directions_meta:
        nav_by_category.setdefault(dm["category"], []).append(
            f'<a href="子方向{dm["code"]}_{dm["name"]}.html" '
            f'style="display:inline-block;margin:4px;padding:6px 12px;background:#e8f0fe;'
            f'color:#1F4E78;text-decoration:none;border-radius:4px;font-size:13px;">'
            f'{dm["name"]} ({dm["article_count"]}篇)</a>'
        )
    nav_html = "".join(
        f'<div style="margin:8px 0;"><strong>{cat}：</strong>{"".join(links)}</div>'
        for cat, links in nav_by_category.items()
    )

    # 主表格行（字段与契约一致）
    rows = []
    for a in articles:
        rows.append(f"""
            <tr>
                <td>{a.get('direction', '')}</td>
                <td>{a.get('source', '')}</td>
                <td>{a.get('category', '')}</td>
                <td>{a.get('published_at', '')}</td>
                <td><a href="{a.get('url', '#')}" target="_blank" rel="noopener">{a.get('title', '')}</a></td>
            </tr>""")

    cat_stats_rows = "".join(
        f"<tr><td>{k}</td><td>{v}</td></tr>" for k, v in sorted(category_stats.items())
    )

    success_names = [dm["name"] for dm in directions_meta if dm["article_count"] > 0]
    failed_names = [d["name"] for d in DIRECTIONS
                    if d["name"] not in {dm["name"] for dm in directions_meta}]

    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>信源文章汇总页 - 综合</title>
    <style>
        body {{ font-family: -apple-system, "Microsoft YaHei", sans-serif; max-width: 1500px; margin: 0 auto; padding: 20px; }}
        h1 {{ color: #1F4E78; border-bottom: 3px solid #1F4E78; padding-bottom: 12px; }}
        .nav-section {{ margin: 20px 0; padding: 20px; background: #f7f9fb; border-radius: 8px; border-left: 4px solid #1F4E78; }}
        .nav-section h3 {{ margin-top: 0; color: #1F4E78; }}
        .stats {{ margin: 20px 0; padding: 15px; background: #e8f5e9; border-radius: 8px; }}
        .stats-table {{ width: auto; border-collapse: collapse; margin: 5px 0; }}
        .stats-table th, .stats-table td {{ border: 1px solid #ddd; padding: 6px 14px; }}
        .stats-table th {{ background: #f0f0f0; color: #333; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
        th, td {{ border: 1px solid #ddd; padding: 10px; text-align: left; }}
        th {{ background: #1F4E78; color: white; }}
        tr:nth-child(even) {{ background: #f5f8fc; }}
        a {{ color: #2E6DA4; text-decoration: none; }}
        a:hover {{ text-decoration: underline; }}
        .filters {{ margin: 20px 0; padding: 15px; background: #fff; border: 1px solid #ddd; border-radius: 8px; }}
        .filters input {{ padding: 8px; width: 350px; margin-right: 10px; }}
        .filters button {{ padding: 8px 16px; background: #1F4E78; color: white; border: none; border-radius: 4px; cursor: pointer; }}
        .status {{ margin: 10px 0; padding: 12px; border-radius: 4px; }}
        .status.success {{ background: #d4edda; color: #155724; }}
        .status.warning {{ background: #fff3cd; color: #856404; }}
    </style>
</head>
<body>
    <h1>📊 信源文章汇总页 · 综合版</h1>

    <div class="stats">
        <strong>生成时间：</strong>{now}<br>
        <strong>内容方向：</strong>{len(directions_meta)} 个<br>
        <strong>文章总数：</strong>{len(articles)} 条<br>
        <strong>排序方式：</strong>按日期降序（最新在前）
    </div>

    <div class="status {'success' if not failed_names else 'warning'}">
        <strong>方向爬取状态：</strong>
        {' | '.join([f'✓ {n}' for n in success_names])}
        {' | '.join([f'✗ {n}' for n in failed_names])}
    </div>

    <div class="nav-section">
        <h3>📑 按方向浏览</h3>
        {nav_html}
    </div>

    <div style="margin: 20px 0; padding: 15px; background: #fff; border: 1px solid #ddd; border-radius: 8px;">
        <strong>分类统计：</strong>
        <table class="stats-table">
            <tr><th>内容板块</th><th>文章数</th></tr>
            {cat_stats_rows}
        </table>
    </div>

    <div class="filters">
        <input type="text" id="searchInput" placeholder="搜索标题（支持全局搜索）..." onkeyup="filterTable()">
        <button onclick="filterTable()">搜索</button>
        <span style="color:#999;margin-left:10px;">共 {len(articles)} 条结果</span>
    </div>

    <table id="articlesTable">
        <thead>
            <tr>
                <th>内容方向</th>
                <th>信源名称</th>
                <th>内容板块</th>
                <th>发布日期</th>
                <th>文章标题</th>
            </tr>
        </thead>
        <tbody>
            {''.join(rows) if rows else '<tr><td colspan="5" style="text-align:center;color:#999;">暂无文章数据</td></tr>'}
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
                var show = false;
                for (var j = 0; j < 5; j++) {{
                    td = tr[i].getElementsByTagName("td")[j];
                    if (td) {{
                        txtValue = td.textContent || td.innerText;
                        if (txtValue.toUpperCase().indexOf(filter) > -1) {{
                            show = true; break;
                        }}
                    }}
                }}
                tr[i].style.display = show ? "" : "none";
            }}
        }}
    </script>
</body>
</html>"""
    return html


def generate_payload(articles, directions_meta):
    """生成统一契约综合 JSON（与单方向输出同构，scope=all）。"""
    return {
        "schema_version": "1.0",
        "source_system": "web_crawler",
        "scope": "all",
        "generated_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S+08:00"),
        "directions": directions_meta,
        "stats": {
            "direction_total": len(directions_meta),
            "article_total": len(articles),
        },
        "articles": articles,
    }


def main():
    articles, directions_meta = load_all_articles()
    articles = sort_articles(articles)

    print(f"\n{'='*60}")
    print(f"综合汇总页生成")
    print(f"{'='*60}")
    for dm in directions_meta:
        print(f"  [{dm['code']}] {dm['name']}: {dm['article_count']}篇")

    html = generate_html(articles, directions_meta)
    html_path = os.path.join(OUTPUT_DIR, "信源文章汇总页_综合.html")
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(html)

    payload = generate_payload(articles, directions_meta)
    json_path = os.path.join(OUTPUT_DIR, "信源文章汇总页_综合.json")
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"\n✓ 综合汇总页已生成: {html_path}")
    print(f"✓ 综合契约 JSON 已生成: {json_path}")
    print(f"  共 {len(directions_meta)} 个方向，{len(articles)} 篇文章")


if __name__ == "__main__":
    main()
