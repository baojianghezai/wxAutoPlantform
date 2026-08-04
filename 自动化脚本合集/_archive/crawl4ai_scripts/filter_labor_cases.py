#!/usr/bin/env python3
"""从已爬取的典型案例中筛选劳动争议相关内容。"""
import re
import os

INPUT = os.path.join(os.path.dirname(__file__), "court_output", "典型案例_20260730_085049.md")
OUTPUT = os.path.join(os.path.dirname(__file__), "court_output", "劳动争议典型案例_20260730_085049.md")

KEYWORDS = [
    "劳动", "劳资", "用工", "工资", "工伤", "辞退", "解除劳动合同",
    "劳动争议", "劳动仲裁", "劳动合同", "工伤赔偿", "经济补偿",
    "劳动者", "用人单位", "劳动合同法", "劳动人事", "船员劳动",
    "拖欠工资", "违法解除", "服务期", "竞业限制", "加班费",
    "农民工工资", "劳动权益"
]

with open(INPUT, "r", encoding="utf-8") as f:
    content = f.read()

# 按 --- 分隔每条案例
cases = re.split(r'\n---\n', content)
header = cases[0]  # 开头的标题部分
cases = cases[1:]

matched = []
for case in cases:
    # 检查是否包含关键词
    if any(kw in case for kw in KEYWORDS):
        matched.append(case)

print(f"总案例数: {len(cases)}")
print(f"劳动争议相关案例: {len(matched)}")

# 保存筛选结果
with open(OUTPUT, "w", encoding="utf-8") as f:
    f.write(f"{header}\n\n")
    f.write(f"> 筛选条件：包含劳动争议相关关键词（劳动、工资、工伤、辞退、解除劳动合同等）\n\n")
    f.write("---\n\n".join(matched))

print(f"已保存: {OUTPUT}")

# 打印匹配的案例标题
for i, case in enumerate(matched, 1):
    title_match = re.search(r'\*\*(.+?)\*\*', case)
    if title_match:
        print(f"  {i}. {title_match.group(1)}")
