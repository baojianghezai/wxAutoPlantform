# -*- coding: utf-8 -*-
"""校验模板中 INJECT 标记区域是否平衡：删除 [START, END) 后 section 标签深度应回到一致。"""
import io
import re
import sys


def section_depths(html):
    """扫描所有 section 标签，返回每个字符处的深度轨迹（近似）。"""
    depth = 0
    out = []
    for m in re.finditer(r"<section\b[^>]*>|</section>", html):
        out.append((m.start(), depth, m.group(0)))
        depth += -1 if m.group(0).startswith("</") else 1
    return out


def main():
    fp = sys.argv[1]
    html = io.open(fp, encoding="utf-8").read()
    a = html.find("<!-- INJECT_START -->")
    b = html.find("<!-- INJECT_END -->")
    if a < 0 or b < 0:
        print("无标记")
        return

    # 记录标记处紧邻的前后 section 深度
    dep = 0
    ev = []
    for m in re.finditer(r"<section\b[^>]*>|</section>", html):
        pos = m.start()
        if pos < a:
            ev.append((pos, "before", dep, m.group(0)[:40]))
        elif a <= pos < b:
            ev.append((pos, "IN-REGION", dep, m.group(0)[:40]))
        else:
            ev.append((pos, "after", dep, m.group(0)[:40]))
        dep += -1 if m.group(0).startswith("</") else 1

    before_events = [e for e in ev if e[1] == "before"]
    region_events = [e for e in ev if e[1] == "IN-REGION"]
    after_events = [e for e in ev if e[1] == "after"]

    d_before_end = before_events[-1][2] if before_events else 0  # 最后一个 before 事件时的深度
    d_after_start = after_events[0][2] if after_events else 0    # 第一个 after 事件时的深度

    print(f"START 位于 {a}，END 位于 {b}")
    print(f"before 末尾最后一个 section 事件时深度 = {d_before_end}")
    print(f"after  开头第一个 section 事件时深度 = {d_after_start}")
    print(f"before 区里 open/close 净增减 = {sum(1 for e in region_events if e[3].startswith('<section') and not e[3].startswith('</')) - sum(1 for e in region_events if e[3].startswith('</'))}")

    # 关键：区域内部是否自平衡（open数 == close数）
    opens = sum(1 for e in region_events if e[3].startswith("<section") and not e[3].startswith("</"))
    closes = sum(1 for e in region_events if e[3].startswith("</section>"))
    print(f"区域内部: open={opens} close={closes} -> {'自平衡' if opens == closes else '不平衡!'}")

    # 删除区域后整体平衡
    removed = html[:a] + html[b + len("<!-- INJECT_END -->"):]
    depth = 0
    bad = False
    for m in re.finditer(r"<section\b[^>]*>|</section>", removed):
        depth += -1 if m.group(0).startswith("</") else 1
        if depth < 0:
            bad = True
            break
    print(f"删除区域后整体 section 深度回 0: {depth == 0}，中途无负深度: {not bad}")


if __name__ == "__main__":
    main()
