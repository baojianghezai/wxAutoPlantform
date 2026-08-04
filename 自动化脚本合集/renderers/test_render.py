# -*- coding: utf-8 -*-
"""渲染器自测：三种 content_type 的 mock data 各渲染一次，结果写入 _test_output/。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from renderers import render_article

OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_test_output")

MOCKS = [
    ("job_list", {
        "content_type": "job_list",
        "title": "青岛本周热招岗位",
        "digest": "精选 3 个急招岗位",
        "sections": [
            {"type": "hero", "title": "本周热招", "subtitle": "优质岗位 · 职等你来"},
            {"type": "cards", "items": [
                {"title": "软件工程师",
                 "fields": {"薪资": "8-12K", "地点": "青岛"},
                 "tags": ["急招", "五险一金"],
                 "description": "负责后端服务开发与维护，熟悉 Python 优先。"},
                {"title": "煤矿安全员",
                 "fields": {"薪资": "6-9K", "地点": "榆林"},
                 "tags": ["包住"],
                 "description": "负责井下安全巡检，需持安全员证。"},
            ]},
            {"type": "key_points", "title": "投递须知",
             "points": ["简历命名：姓名+岗位", "一周内反馈面试结果"]},
        ],
    }),
    ("solar_term", {
        "content_type": "solar_term",
        "title": "大暑",
        "digest": "腐草为萤，土润溽暑",
        "sections": [
            {"type": "hero", "title": "大暑", "subtitle": "二十四节气 · 第十二"},
            {"type": "paragraph", "heading": "节气物语",
             "text": "大暑，一年中最热的时节。绿树荫浓，蝉声阵阵。"},
            {"type": "key_points", "title": "大暑三候",
             "points": ["一候腐草为萤", "二候土润溽暑", "三候大雨时行"]},
            {"type": "image", "url": "https://example.com/dashu.jpg",
             "caption": "荷风送香气"},
        ],
    }),
    ("unknown_type", {
        "content_type": "weibo_hot",
        "title": "今日热榜",
        "sections": [
            {"type": "hero", "title": "今日热榜", "subtitle": "一分钟看完"},
            {"type": "paragraph", "text": "以下是今天的热点摘要。"},
            {"type": "key_points", "title": "TOP3",
             "points": ["热点一", "热点二", "热点三"]},
            {"type": "cards", "items": [{"title": "不应出现"}]},  # generic 不渲染 cards
        ],
    }),
]


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    for name, data in MOCKS:
        html_out = render_article(data)
        path = os.path.join(OUT_DIR, f"{name}.html")
        with open(path, "w", encoding="utf-8") as f:
            f.write(html_out)
        print(f"[{name}] bytes={len(html_out.encode('utf-8'))} -> {path}")


if __name__ == "__main__":
    main()
