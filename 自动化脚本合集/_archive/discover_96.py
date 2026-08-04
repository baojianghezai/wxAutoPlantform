# -*- coding: utf-8 -*-
"""探测 bj.96weixin.com 模板库：验证登录态 + 解析真实模板 id。"""
import os, re, sys, json, urllib.request, urllib.parse

BASE = os.path.dirname(os.path.abspath(__file__))
HOST = "https://bj.96weixin.com"

COOKIE = os.environ.get("WB96_COOKIE", "")
if not COOKIE:
    ck = os.path.join(BASE, "cookies.txt")
    if os.path.exists(ck):
        COOKIE = open(ck, encoding="utf-8").read().strip()

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
HDR = {
    "User-Agent": UA,
    "Cookie": COOKIE,
    "Referer": f"{HOST}/",
    "Accept": "text/html,application/xhtml+xml,application/json,*/*",
}

def get(url):
    req = urllib.request.Request(url, headers=HDR)
    return urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "ignore")

def post(url, data):
    body = urllib.parse.urlencode(data).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST", headers={
        **HDR,
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": f"{HOST}/material/tpl",
    })
    return urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "ignore")

def main():
    print("=== 1) 测试登录态：直接 POST tplinfo id=1001 ===")
    try:
        raw = post(f"{HOST}/indexajax/tplinfo", {"id": 1001})
        print("原始返回(前300):", raw[:300])
    except Exception as e:
        print("tplinfo 请求异常:", e)

    print("\n=== 2) 抓取模板画廊页，解析 id ===")
    found = set()
    # 候选画廊页路径
    pages = [
        "/material/tpl",
        "/material/tpl?type=2",
        "/material/tpl?style=0",
    ]
    for p in pages:
        try:
            html = get(f"{HOST}{p}")
            print(f"  · {p} 状态OK 长度={len(html)}")
            # 96 卡片常带 data-id / data-tplid / id= 数字
            for m in re.finditer(r'data-(?:tplid|id|tid)=["\']?(\d+)', html, re.I):
                found.add(int(m.group(1)))
            # 内联 JSON 里的 "id":数字
            for m in re.finditer(r'"id"\s*:\s*(\d+)', html):
                found.add(int(m.group(1)))
            # onclick 里 tplinfo(数字)
            for m in re.finditer(r'tplinfo\s*\(\s*(\d+)', html, re.I):
                found.add(int(m.group(1)))
        except Exception as e:
            print(f"  · {p} 失败: {e}")

    print(f"\n解析到候选 id 数量: {len(found)}")
    if found:
        top = sorted(found)[:50]
        print("样例 id:", top)

if __name__ == "__main__":
    main()
