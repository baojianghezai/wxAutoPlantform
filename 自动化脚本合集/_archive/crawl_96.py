# -*- coding: utf-8 -*-
"""96微信编辑器模板爬虫（需登录态）。

背景：96 的模板 HTML 接口 /indexajax/tplinfo（文章模板）、/indexajax/styleinfo（文本样式）
会在匿名请求时返回「内容获取失败」，必须在已登录的浏览器会话下才能拿到真实 HTML。
本脚本封装了这两个接口，供"带了登录 cookie"的爬虫调用，把真实 96 模板灌进 templates/96/real/，
之后 Task2 的轮换会自动并入这些真模板。

用法（在你这边能联网且已登录 96 的环境运行）：
  1) 从浏览器登录 bj.96weixin.com 后，复制 Cookie 请求头字符串（开发者工具→网络→任意请求→Request Headers→Cookie）。
  2) 放进环境变量或文件：
       export WB96_COOKIE="sessionid=xxx; ..."
     或写入文件 cookies.txt（一行 cookie 串）。
  3) 运行：
       python crawl_96.py --ids 1001 1002 1003          # 按模板 id 抓取文章模板
       python crawl_96.py --style-ids 7 16 41           # 抓取文本样式
       python crawl_96.py --range 1000 1100             # 批量按 id 区间尝试（跳过失败的）
       python crawl_96.py --ids 1001 --out templates/96/real   # 指定输出目录
  4) 抓到的文件形如 templates/96/real/tpl_1001.html，自动带 <!-- ACCENT:... --> 则会被 Task2 配色；
     若模板本身无配色标记，可在文件首行手动补 <!-- ACCENT:#1F4E78 -->。

依赖：仅标准库（urllib）。
"""
import os, sys, json, argparse, urllib.request, urllib.error

BASE = os.path.dirname(os.path.abspath(__file__))
HOST = "https://bj.96weixin.com"
OUT_DIR = os.path.join(BASE, "templates", "96", "real")


def get_cookie():
    if os.environ.get("WB96_COOKIE"):
        return os.environ["WB96_COOKIE"].strip()
    ck = os.path.join(BASE, "cookies.txt")
    if os.path.exists(ck):
        return open(ck, encoding="utf-8").read().strip()
    return ""


def fetch_html(endpoint, tid, cookie):
    url = f"{HOST}{endpoint}"
    data = f"id={tid}".encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST", headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": f"{HOST}/material/tpl",
        "Cookie": cookie,
    })
    try:
        raw = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "ignore")
        obj = json.loads(raw)
    except Exception as e:
        return None, f"请求/解析失败: {e}"
    if obj.get("status") == 1 and obj.get("info"):
        return obj["info"], None
    return None, f"status={obj.get('status')} info={obj.get('info')}"


def guess_accent(html):
    # 尝试从模板里找一个明显的主题色，写进 ACCENT 注释，方便 Task2 配色
    import re
    m = re.search(r'(?:color|background|border[a-z-]*):\s*(#[0-9A-Fa-f]{6})', html, re.I)
    return m.group(1).upper() if m else "#1F4E78"


def save(tid, html, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    accent = guess_accent(html)
    content = f"<!-- ACCENT:{accent} -->\n{html}\n" if not html.lstrip().startswith("<!--") else html
    path = os.path.join(out_dir, f"tpl_{tid}.html")
    open(path, "w", encoding="utf-8").write(content)
    return path


def run(endpoint, ids, cookie, out_dir, label):
    ok, fail = 0, 0
    for tid in ids:
        html, err = fetch_html(endpoint, tid, cookie)
        if html:
            p = save(tid, html, out_dir)
            print(f"  ✔ [{label}] id={tid} → {p}")
            ok += 1
        else:
            print(f"  ✘ [{label}] id={tid} 失败: {err}")
            fail += 1
    print(f"完成：成功 {ok}，失败 {fail}。输出目录：{out_dir}")


def main():
    ap = argparse.ArgumentParser(description="96微信编辑器模板爬虫（需登录cookie）")
    ap.add_argument("--ids", nargs="+", type=int, help="文章模板 id 列表")
    ap.add_argument("--style-ids", nargs="+", type=int, help="文本样式 id 列表")
    ap.add_argument("--range", nargs=2, type=int, metavar=("START", "END"), help="按 id 区间批量尝试")
    ap.add_argument("--out", default=OUT_DIR, help="输出目录（默认 templates/96/real）")
    args = ap.parse_args()

    cookie = get_cookie()
    if not cookie:
        print("未找到 cookie：请设置环境变量 WB96_COOKIE 或写入 cookies.txt（登录 bj.96weixin.com 后复制请求头 Cookie）。")
        sys.exit(1)

    if args.ids:
        run("/indexajax/tplinfo", args.ids, cookie, args.out, "tpl")
    if args.style_ids:
        run("/indexajax/styleinfo", args.style_ids, cookie, args.out, "style")
    if args.range:
        s, e = args.range
        run("/indexajax/tplinfo", range(s, e + 1), cookie, args.out, "tpl")
    if not (args.ids or args.style_ids or args.range):
        ap.print_help()


if __name__ == "__main__":
    main()
