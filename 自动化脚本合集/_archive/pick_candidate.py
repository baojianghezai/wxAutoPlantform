# -*- coding: utf-8 -*-
"""选稿助手：把要发的文章链接写进 selected_links.txt（Task2 会读取）。

用法：
  python pick_candidate.py <微信文章链接> [备注]
  python pick_candidate.py A05 [备注]      # 若参数为 Axx，则从 candidates/ 解析出对应链接再写入

说明：每行一个链接，Task2 处理完后会自动删除该行。也可直接手动编辑 selected_links.txt。
"""
import sys, os, json

BASE = os.path.dirname(os.path.abspath(__file__))
LINKS_FILE = os.path.join(BASE, "selected_links.txt")


def resolve_url(arg):
    # 若为 Axx 形式，从 candidates 缓存解析链接
    if re.match(r'^A\d+$', arg):
        meta = os.path.join(BASE, "candidates", f"{arg}.meta.json")
        if os.path.exists(meta):
            try:
                m = json.load(open(meta, encoding="utf-8"))
                return m.get("link")
            except Exception:
                pass
    return arg


def append_link(url, note=""):
    line = url if not note else f"{url}  # {note}"
    with open(LINKS_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")
    print(f"已写入链接到 selected_links.txt：{line}")


if __name__ == "__main__":
    import re
    if len(sys.argv) < 2:
        print("用法: python pick_candidate.py <链接或Axx id> [备注]")
        sys.exit(1)
    arg = sys.argv[1].strip()
    note = sys.argv[2] if len(sys.argv) > 2 else ""
    url = resolve_url(arg)
    if not url or not url.startswith("http"):
        print(f"无法识别为链接或有效候选id：{arg}")
        sys.exit(1)
    append_link(url, note)
