#!/usr/bin/env python3
"""适配器：把 task1_index.py 产出的 review/index.json（公众号招聘来源）转换为统一 articles 契约。

设计原则（非侵入式）：
- 不修改 task1_index.py 本身，它仍按原结构为 task2_publish.py 供数
- 仅读取 review/index.json，本脚本单独产出统一格式，避免破坏下游
- 字段映射与 crawl4ai 爬虫输出保持完全一致（前端无感区分 web / wechat）
"""
import os
import re
import json
import html
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# crawl4ai/scripts/xinjiang_directional -> 自动化脚本合集
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "..", ".."))
REVIEW_INDEX = os.path.join(PROJECT_ROOT, "review", "index.json")
OUTPUT_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, "shandong_output"))
# 公众号名称 -> 分类 映射表（与 server 模板配置共用）
SELECTOR_CONFIG = os.path.join(PROJECT_ROOT, "templates", "selector_config.json")


def load_source_categories():
    """读取 selector_config.json 的 source_categories（公众号 -> 分类）。"""
    try:
        with open(SELECTOR_CONFIG, encoding="utf-8") as f:
            return json.load(f).get("source_categories", {})
    except Exception:
        return {}


def parse_pubdate(raw):
    """把 RFC 2822 的 pubDate（如 'Tue, 28 Jul 2026 01:33:25 +0000'）转成 YYYY-MM-DD。"""
    if not raw:
        return ""
    for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S %Z"):
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except Exception:
            continue
    m = re.search(r"(20\d{2})[-/](\d{1,2})[-/](\d{1,2})", raw)
    if m:
        return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    return ""


def convert_task1_index(index_path=None):
    """读取 review/index.json，返回 (articles_list, meta_dict)。

    每条 article 契约字段与 web 爬虫一致：
    id / title / source / source_type / direction / category / published_at / url / summary / thumbnail / extra
    """
    path = index_path or REVIEW_INDEX
    if not os.path.exists(path):
        return [], {"found": False, "path": path}
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    items = data.get("items", [])
    src_cats = load_source_categories()
    articles = []
    for it in items:
        link = it.get("link", "")
        img = html.unescape(it.get("first_image", "") or "")  # 还原 &amp; -> &
        accounts = it.get("accounts", []) or []
        # 公众号分类：按 accounts 命中最优先的映射分类；未命中归入 other
        account_cats = [src_cats.get(a) for a in accounts if src_cats.get(a)]
        source_category = account_cats[0] if account_cats else "other"
        articles.append({
            "id": it.get("id", ""),                      # 保留 A01 编号，下游 Task2 可据此回查
            "title": it.get("title", "无标题"),
            "source": " / ".join(accounts) if accounts else "公众号",
            "source_type": "wechat",
            "direction": "",                             # task1 无方向分类
            "category": "公众号招聘",
            "source_category": source_category,
            "published_at": parse_pubdate(it.get("pubDate", "")),
            "url": link,
            "summary": it.get("summary", ""),
            "thumbnail": img,
            "extra": {
                "accounts": accounts,
                "deadline": it.get("deadline", ""),
                "companies": it.get("companies", []),
                "attachments": it.get("attachments", []),
                "image_count": it.get("image_count", 0),
                "is_media": it.get("is_media", False),
                "note": it.get("note", ""),
            },
        })

    meta = {
        "found": True,
        "source_path": path,
        "generated_at": data.get("generated_at", ""),
        "window": data.get("window", []),
        "candidate_count": data.get("candidate_count", len(items)),
        "expired_filtered": data.get("expired_filtered", 0),
    }
    return articles, meta


if __name__ == "__main__":
    articles, meta = convert_task1_index()
    out = os.path.join(OUTPUT_DIR, "unified_wechat.json")
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    payload = {
        "schema_version": "1.0",
        "source_system": "task1_index",
        "scope": "wechat",
        "generated_at": meta.get("generated_at", datetime.now().strftime("%Y-%m-%dT%H:%M:%S+08:00")),
        "stats": {"article_total": len(articles)},
        "articles": articles,
    }
    with open(out, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"公众号适配器：转换 {len(articles)} 篇 → {out}")
    if not meta.get("found"):
        print(f"  ⚠ 未找到 review/index.json：{meta.get('path')}")
