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


def auto_marker(fp):
    """自动给模板插入 INJECT 标记，保留头部装饰与尾部（二维码/版权）装饰。

    策略 A（兄弟块平铺）：头部块[0] 与尾部块[-1] 之间的内容区替换。
    策略 B（页脚驱动，A 不适用时）：头部=深度2第一块终点起；尾部=包含 data-qr
    二维码的最深块起点起。render_inject 自带不平衡补偿，保证渲染后 section 平衡。

    返回状态字符串（OK / 各类失败原因）。
    """
    html = io.open(fp, encoding="utf-8").read()
    if "INJECT_START" in html:
        return "SKIP 已有标记"
    html = html.replace("<!-- INJECT_START -->", "").replace("<!-- INJECT_END -->", "")

    ranges = editor_ranges(html)
    bd = _block_depth(ranges)

    # ---- 策略 A：兄弟块平铺 ----
    if bd is not None:
        blocks = sorted(r for r in ranges if r[2] == bd)
        if len(blocks) >= 3:
            s_start = blocks[1][0]
            e_start = blocks[-1][0]
            if e_start > s_start and section_balance(html[:s_start] + html[e_start:]):
                parts = [html[:s_start], "<!-- INJECT_START -->",
                         html[s_start:e_start], "<!-- INJECT_END -->", html[e_start:]]
                io.open(fp, "w", encoding="utf-8").write("".join(parts))
                return (f"OK-A bd={bd} keep[{len(blocks)}块->头{blocks[0][1]-blocks[0][0]}字"
                        f"/尾{blocks[-1][1]-blocks[-1][0]}字] region={e_start - s_start}字")

    # ---- 策略 B：页脚驱动 ----
    qr = html.rfind("data-qr")
    at2 = sorted(r for r in ranges if r[2] == 2)
    if qr < 0:
        return "FAIL 无 data-qr 页脚且策略 A 不适用"
    if not at2:
        return "FAIL 无深度2头部块"
    s_start = at2[0][1]
    cands = sorted([r for r in ranges if r[0] <= qr < r[1]], key=lambda r: r[2])
    if not cands:
        return "FAIL 找不到包含二维码的块"
    e_start = cands[-1][0]
    if e_start <= s_start:
        return f"FAIL 二维码块@{e_start} 在头部@{s_start} 之前"

    parts = [html[:s_start], "<!-- INJECT_START -->",
             html[s_start:e_start], "<!-- INJECT_END -->", html[e_start:]]
    io.open(fp, "w", encoding="utf-8").write("".join(parts))
    return (f"OK-B 头部{at2[0][1]-at2[0][0]}字 尾部{len(html)-e_start}字"
            f" region={e_start - s_start}字")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--start", required=False, help="--auto 时忽略")
    ap.add_argument("--end", required=False, help="--auto 时忽略")
    ap.add_argument("--auto", action="store_true",
                    help="自动定位：保留第一个内容块（头部）和最后一个内容块（尾部），中间全部替换")
    args = ap.parse_args()

    html = io.open(args.file, encoding="utf-8").read()
    if args.auto:
        print(auto_marker(args.file))
        return
    html = html.replace("<!-- INJECT_START -->", "").replace("<!-- INJECT_END -->", "")

    ranges = editor_ranges(html)
    bd = _block_depth(ranges)
    if bd is None:
        print("未找到内容块深度")
        return

    blocks = sorted(r for r in ranges if r[2] == bd)
    if len(blocks) < 3:
        print(f"内容块只有 {len(blocks)} 个，无法自动定位（需要 ≥3：头部+内容+尾部）")
        return

    if args.auto:
        s_start = blocks[1][0]
        e_start = blocks[-1][0]
    else:
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
    print(f"块深度={bd}；保留块[0]({blocks[0][1]-blocks[0][0]}字符)+块[-1]({blocks[-1][1]-blocks[-1][0]}字符)"
          f"；INJECT_START 在 {s_start}，INJECT_END 在 {e_start}（区域 {e_start - s_start} 字符）")
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
