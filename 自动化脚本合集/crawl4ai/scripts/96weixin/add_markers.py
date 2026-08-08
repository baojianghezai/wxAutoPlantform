# -*- coding: utf-8 -*-
"""给 96 模板插入 INJECT 占位符（按 section 嵌套深度定位兄弟块边界）。

用法：
    python add_markers.py <html文件> --start <关键词> --end <关键词>

流程：
1. 解析所有 <section class="_editor*"> 元素的 [start,end,depth]。
2. 找出"内容块深度"：该深度下兄弟块平铺覆盖整个内容区（无大缝隙）。
3. INJECT_START 插到含 --start 关键词的块之前；INJECT_END 插到含 --end 关键词的块之前。
4. 删除 [START, END) 区域后整体 section 深度应回 0（平衡校验）。
"""
import argparse
import io
import re
from collections import Counter


def editor_ranges(html):
    """返回所有 <section class="_editor*"> 的 (start, end, depth)。"""
    stack = []
    ranges = []
    for m in re.finditer(r"<section\b[^>]*>|</section>", html):
        tag = m.group(0)
        if tag.startswith("</"):
            if stack:
                o = stack.pop()
                if o["is_editor"]:
                    ranges.append((o["start"], m.start(), o["depth"]))
        else:
            is_editor = bool(re.search(r'class="[^"]*_editor', tag))
            stack.append({"depth": len(stack), "is_editor": is_editor, "start": m.start()})
    ranges.sort(key=lambda r: r[0])
    return ranges


def _block_depth(ranges):
    """内容块深度 = 该深度下兄弟块平铺覆盖最广。"""
    best = None
    for d in sorted({r[2] for r in ranges}):
        at = sorted(r for r in ranges if r[2] == d)
        if len(at) < 2:
            continue
        # 缝隙大小（下一块起点 - 上一块终点）
        gaps = [at[i + 1][0] - at[i][1] for i in range(len(at) - 1)]
        if all(g >= 0 for g in gaps):
            coverage = at[-1][1] - at[0][0]
            total_gap = sum(max(0, g - 20) for g in gaps)  # 容忍 20 字符内的小空隙
            score = coverage - total_gap
            if best is None or score > best[0]:
                best = (score, d)
    return best[1] if best else None


def _block_containing(ranges, html, keyword, block_depth):
    pos = html.find(keyword)
    if pos < 0:
        return None
    for r in ranges:
        if r[2] == block_depth and r[0] <= pos < r[1]:
            return r
    return None


def section_balance(html):
    depth = 0
    for m in re.finditer(r"<section\b[^>]*>|</section>", html):
        depth += -1 if m.group(0).startswith("</") else 1
        if depth < 0:
            return False
    return depth == 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    args = ap.parse_args()

    html = io.open(args.file, encoding="utf-8").read()
    html = html.replace("<!-- INJECT_START -->", "").replace("<!-- INJECT_END -->", "")

    ranges = editor_ranges(html)
    bd = _block_depth(ranges)
    if bd is None:
        print("未找到内容块深度")
        return
    bs = _block_containing(ranges, html, args.start, bd)
    be = _block_containing(ranges, html, args.end, bd)
    if not bs:
        print(f"start 关键词（{args.start}）不在块深度 {bd} 的块中")
        return
    if not be:
        print(f"end 关键词（{args.end}）不在块深度 {bd} 的块中")
        return
    s_start, e_start = bs[0], be[0]
    if e_start <= s_start:
        print("END 块必须位于 START 块之后")
        return

    removed = html[:s_start] + html[e_start:]
    ok = section_balance(removed)
    print(f"块深度={bd}；INJECT_START 在 {s_start}，INJECT_END 在 {e_start}（区域 {e_start - s_start} 字符）")
    print(f"删除区域后 section 平衡: {ok}")
    if not ok:
        print("平衡校验失败，未写入")
        return

    parts = [html[:s_start], "<!-- INJECT_START -->",
             html[s_start:e_start], "<!-- INJECT_END -->", html[e_start:]]
    io.open(args.file, "w", encoding="utf-8").write("".join(parts))
    print("已写入。")


if __name__ == "__main__":
    main()
