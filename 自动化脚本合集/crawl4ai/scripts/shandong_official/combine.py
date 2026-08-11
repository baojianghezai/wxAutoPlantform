#!/usr/bin/env python3
"""合并脚本：将 web 爬虫（山东官方招聘 crawl4ai）与 公众号（task1_index）两套数据合并为单一 articles feed。

前端 / Flask 接入层只需读取本脚本产出的 unified_articles.json，无需关心数据来自 web 还是 wechat。
- web 侧：读 shandong_output/山东官方招聘_综合.json
- wechat 侧：通过 adapter_task1.convert_task1_index() 转换 review/index.json
- 合并后按 published_at 降序，按 id 去重（web 用 web_xxx，wechat 用 A01，天然不冲突）
"""
import os
import json
import glob
from datetime import datetime

from adapter_task1 import convert_task1_index

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, "shandong_output"))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "..", ".."))
SELECTOR_CONFIG = os.path.join(PROJECT_ROOT, "templates", "selector_config.json")


def load_web_articles():
    """加载 web 侧文章（扁平 articles）。

    权威来源为山东官方招聘爬虫产出的 山东官方招聘_综合.json。
    """
    arts = []
    combined = os.path.join(OUTPUT_DIR, "山东官方招聘_综合.json")
    if os.path.exists(combined):
        try:
            with open(combined, encoding="utf-8") as f:
                data = json.load(f)
            for a in data.get("articles", []):
                a.setdefault("source_type", "web")
                arts.append(a)
            return arts
        except Exception as e:
            print(f"  ⚠ 读取山东综合文件失败：{e}")
    return arts


def sort_key(a):
    d = a.get("published_at", "")
    return d if d else "0000-00-00"


def load_categories():
    """读取 selector_config.json 的 categories 定义（分类 id -> label）。"""
    try:
        with open(SELECTOR_CONFIG, encoding="utf-8") as f:
            return json.load(f).get("categories", {})
    except Exception:
        return {}


def fill_source_category(articles):
    """兜底补齐 source_category：缺失时 web 归 recruitment、wechat 归 other。"""
    for a in articles:
        if not a.get("source_category"):
            a["source_category"] = "recruitment" if a.get("source_type") == "web" else "other"
    return articles


def main():
    web_articles = load_web_articles()
    wechat_articles, meta = convert_task1_index()

    all_articles = fill_source_category(web_articles + wechat_articles)
    all_articles.sort(key=sort_key, reverse=True)

    # 按 id 去重（web 用 web_xxx，wechat 用 A01，天然不冲突；同名同站兜底）
    seen = set()
    deduped = []
    for a in all_articles:
        aid = a.get("id")
        if aid in seen:
            continue
        seen.add(aid)
        deduped.append(a)

    payload = {
        "schema_version": "1.0",
        "source_system": "combined",
        "scope": "all",
        "generated_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S+08:00"),
        "stats": {
            "web_total": len(web_articles),
            "wechat_total": len(wechat_articles),
            "total": len(deduped),
        },
        "categories": [
            {"id": cid, "label": cdef.get("label", cid)}
            for cid, cdef in load_categories().items()
        ],
        "articles": deduped,
    }
    out = os.path.join(OUTPUT_DIR, "unified_articles.json")
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"合并完成：web {len(web_articles)} + wechat {len(wechat_articles)} = {len(deduped)} 篇（去重后）")
    print(f"输出：{out}")


if __name__ == "__main__":
    main()
