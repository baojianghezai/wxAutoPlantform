# -*- coding: utf-8 -*-
"""用发现的候选 id 逐一探测 tplinfo，报告有效/无效，并落盘有效模板。"""
import os, sys, json, urllib.request, urllib.parse, re

BASE = os.path.dirname(os.path.abspath(__file__))
HOST = "https://bj.96weixin.com"
OUT = os.path.join(BASE, "templates", "96", "real")
os.makedirs(OUT, exist_ok=True)

COOKIE = os.environ.get("WB96_COOKIE", "")
if not COOKIE:
    ck = os.path.join(BASE, "cookies.txt")
    if os.path.exists(ck):
        COOKIE = open(ck, encoding="utf-8").read().strip()

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"

def post(endpoint, tid):
    body = f"id={tid}".encode("utf-8")
    req = urllib.request.Request(f"{HOST}{endpoint}", data=body, method="POST", headers={
        "User-Agent": UA,
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": f"{HOST}/material/tpl",
        "Cookie": COOKIE,
    })
    raw = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "ignore")
    return json.loads(raw)

def guess_accent(html):
    m = re.search(r'(?:color|background|border[a-z-]*):\s*(#[0-9A-Fa-f]{6})', html, re.I)
    return m.group(1).upper() if m else "#1F4E78"

if __name__ == "__main__":
    ids = list(range(24960, 24992))  # 24960~24991
    ok, fail = [], []
    for tid in ids:
        try:
            obj = post("/indexajax/tplinfo", tid)
            if obj.get("status") == 1 and obj.get("info"):
                info = obj["info"]
                # info 可能是 html 字符串，也可能是含 html 字段的对象
                html = info if isinstance(info, str) else info.get("html", "") or json.dumps(info, ensure_ascii=False)
                if html and len(html) > 50:
                    accent = guess_accent(html)
                    content = (html if html.lstrip().startswith("<!--") else f"<!-- ACCENT:{accent} -->\n{html}\n")
                    p = os.path.join(OUT, f"tpl_{tid}.html")
                    open(p, "w", encoding="utf-8").write(content)
                    ok.append(tid)
                    print(f"  ✔ id={tid} len={len(html)} accent={accent} → {p}")
                    continue
            fail.append((tid, f"status={obj.get('status')} info_len={len(str(obj.get('info')))}"))
            print(f"  ✘ id={tid} 无效: status={obj.get('status')}")
        except Exception as e:
            fail.append((tid, str(e)))
            print(f"  ✘ id={tid} 异常: {e}")
    print(f"\n有效模板数: {len(ok)} -> {ok}")
    print(f"无效/失败数: {len(fail)}")
    with open(os.path.join(BASE, "templates", "96", "real", "_probe_report.json"), "w", encoding="utf-8") as f:
        json.dump({"ok": ok, "fail": [list(x) for x in fail]}, f, ensure_ascii=False, indent=2)
