# -*- coding: utf-8 -*-
"""Task2 — 编辑与发布（链接输入版）。

输入：selected_links.txt（每行一个微信文章链接，由人工从待审清单复制粘贴）。
流程：
  · 取首个链接 → 实时抓取原文（mp.weixin.qq.com/s/...），缓存按 link 回退；
  · 发文稿A：原文【完整正文，原封不动】+ 末尾追加 tail_images/ 下所有图片；
  · 发文稿B：读 b_photos/extracted.json（AI 视觉提取的岗位，写入前已生成）
            → 套 96 微信风格模板（templates/，可插拔）→ 渲染；
  · 处理完把该链接从 selected_links.txt 删除（仅删已消费行）；
  · 发布：有 appid/secret 且 publish_mode=auto → 推两篇到草稿箱；
          否则仅产出成品 HTML 供手动粘贴（先A后B）。
完成后写 task2_status.json。

依赖：仅 Python 标准库（urllib / base64 / json / re）。
用法：python task2_publish.py
说明：发布接口用 cgi-bin/draft/add（非 freepublish/add）；A 标题取原文、B 标题取 config.task2.articleB_title；
      尾图须插在最后一个 </section> 之前（微信会丢弃其后的兄弟节点）。详见 TASK2使用说明.md。
"""
import json, os, re, base64, shutil, urllib.request, urllib.error, uuid
from datetime import datetime, timezone, timedelta
from urllib.parse import urlencode

BASE = os.path.dirname(os.path.abspath(__file__))

DEFAULTS = {
    "selected_file": "selected.json",
    "selected_links_file": "selected_links.txt",
    "candidates_dir": "candidates",
    "task2": {
        "tail_images_dir": "tail_images",
        "b_photos_dir": "b_photos",
        "b_photos_done_dir": "b_photos/done",
        "b_extracted": "b_photos/extracted.json",
        "templates_dir": "templates",
        "templates_96_dir": "templates/96",
        "articleB_template": "96wx_cards",
        "drafts_dir": "drafts",
        "normalize_image_urls": True,
        "publish_mode": "html",
    },
    "wechat": {"appid": "", "secret": ""},
}

config = dict(DEFAULTS)
cfg_path = os.path.join(BASE, "config.json")
if os.path.exists(cfg_path):
    with open(cfg_path, encoding="utf-8") as f:
        cfg = json.load(f)
    config.update({k: v for k, v in cfg.items() if k in DEFAULTS})
    config["task2"].update(cfg.get("task2", {}))
    config["wechat"].update(cfg.get("wechat", {}))

T2 = config["task2"]
NOW = datetime.now(timezone(timedelta(hours=8)))
NOW_STR = NOW.strftime("%Y-%m-%d %H:%M")
TODAY = NOW.strftime("%Y-%m-%d")


# ---------- 链接输入 ----------
def read_links():
    p = os.path.join(BASE, config["selected_links_file"])
    if not os.path.exists(p):
        return []
    lines = [ln.strip() for ln in open(p, encoding="utf-8").read().splitlines()]
    return [ln for ln in lines if ln and not ln.startswith("#")]


def consume_first_link(url):
    """从 selected_links.txt 删除已消费的首个链接，保留其余行。"""
    p = os.path.join(BASE, config["selected_links_file"])
    lines = open(p, encoding="utf-8").read().splitlines()
    kept = [ln for ln in lines if ln.strip() != url]
    open(p, "w", encoding="utf-8").write("\n".join(kept).rstrip() + ("\n" if kept else ""))


# ---------- 抓取原文 ----------
IMG_PROXY_RE = re.compile(r'src="(http://localhost:5000/api/image\?url=([^"]+))"')


def _normalize(html):
    def repl(m):
        from urllib.parse import unquote
        return f'src="{unquote(m.group(2))}"'
    return IMG_PROXY_RE.sub(repl, html)


def fetch_live(url):
    """实时抓取微信文章，返回 {title, body, digest} 或 None。"""
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})
        data = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "ignore")
    except Exception as e:
        print(f"  · 实时抓取失败: {e}")
        return None
    m_title = re.search(r'<meta property="og:title" content="([^"]*)"', data)
    m_desc = re.search(r'<meta property="og:description" content="([^"]*)"', data)
    m_body = re.search(r'id="js_content"[^>]*>(.*?)<script', data, re.S)
    if not m_body:
        return None
    body = m_body.group(1)
    return {
        "title": m_title.group(1) if m_title else "未命名文章",
        "body": body,
        "digest": (m_desc.group(1)[:120] if m_desc else "") or (re.sub(r'<[^>]+>', '', body)[:120]),
    }


def fetch_from_cache(url):
    """按 link 在 candidates/ 缓存里回退匹配。"""
    cdir = os.path.join(BASE, config["candidates_dir"])
    if not os.path.isdir(cdir):
        return None
    for fn in os.listdir(cdir):
        if not fn.endswith(".meta.json"):
            continue
        try:
            m = json.load(open(os.path.join(cdir, fn), encoding="utf-8"))
        except Exception:
            continue
        if m.get("link") == url:
            aid = fn[:-len(".meta.json")]
            html_path = os.path.join(cdir, f"{aid}.html")
            if os.path.exists(html_path):
                body = open(html_path, encoding="utf-8").read()
                if T2.get("normalize_image_urls"):
                    body = _normalize(body)
                return {"title": m.get("title", "未命名文章"),
                        "body": body, "digest": m.get("summary", "")[:120]}
    return None


def get_article(url):
    art = fetch_live(url)
    if art:
        print("  ✔ 实时抓取原文成功")
        return art
    art = fetch_from_cache(url)
    if art:
        print("  ✔ 使用 candidates/ 缓存原文（实时抓取不可用）")
        return art
    return None


# ---------- 发文稿A：原文 + 末尾追加图片 ----------
def embed_img_file(path):
    if not os.path.exists(path):
        return ""
    ext = os.path.splitext(path)[1].lower().lstrip(".") or "png"
    mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
            "gif": "image/gif", "webp": "image/webp"}.get(ext, "image/png")
    # 去掉 base64 中的换行/空白，避免正则漏匹配
    b64 = base64.b64encode(open(path, "rb").read()).decode("ascii").replace("\n", "").replace("\r", "")
    # base64 便于 HTML 预览；自动发布时会改成上传后的 mmbiz 地址
    return (f'<section style="box-sizing:border-box;">'
            f'<img src="data:{mime};base64,{b64}" '
            f'style="display:block;max-width:100%;margin:24px auto 0;" '
            f'alt="{os.path.basename(path)}">'
            f'<!-- TAILIMG:{os.path.basename(path)} --></section>')


def build_articleA(article):
    tail_dir = os.path.join(BASE, T2["tail_images_dir"])
    tail_html = ""
    tail_files = []
    if os.path.isdir(tail_dir):
        for fn in sorted(os.listdir(tail_dir)):
            fp = os.path.join(tail_dir, fn)
            if os.path.isfile(fp) and fn.lower().rsplit(".", 1)[-1] in ("png", "jpg", "jpeg", "gif", "webp"):
                tail_html += embed_img_file(fp)
                tail_files.append(fn)
    if not tail_html:
        tail_html = '<!-- 未提供尾图：请将图片放入 tail_images/ -->'
    body = article.get("body", "")
    # ① 去掉微信特有「哨兵/自定义」标签（仅剥标签、保留内部内容），
    #    避免编辑器导入时整段被丢弃。
    body = re.sub(r'</?(?:mp-style-type|mp-common-videosnap|mpvoice|mpvideo)\b[^>]*>', '', body)
    # ② 整段正文包进【单个顶层 <section>】——这正是微信原生图文结构。
    #    否则 body 是一长串平铺的顶层 <section> 兄弟节点，编辑器导入时只认首个顶层块，
    #    导致「点开正常、一编辑就只剩标题+一张图（头图）」。包成单个 section 后编辑器整段保留。
    doc = (f'<!doctype html><html lang=zh><head><meta charset=utf-8>'
           f'<meta name=viewport content="width=device-width,initial-scale=1"></head><body>'
           f'<section style="box-sizing:border-box;">{body}\n{tail_html}</section></body></html>')
    return doc, tail_files


# ---------- 发文稿A（新流程：线索→企业官网→模板整理） ----------
# 数据契约 a_source.json（由自动化在运行脚本前，据公众号线索去企业官网查证后写入）：
# {
#   "company": "企业名称",
#   "official_website": "https://...",          // 企业官网
#   "recruit_page": "https://...",              // 招聘频道/公告页（可选）
#   "article_title": "可选，作为发文稿A标题",
#   "intro": "公司简介",
#   "positions": [ {"title","count","salary","location","requirement","jd":[...]} ],
#   "apply_method": "应聘方式说明（可含换行/URL）",
#   "deadline": "报名截止",
#   "contact": "联系方式",
#   "source_article": {"title": "...", "link": "..."},   // 线索来源公众号文章
#   "source_account": "线索来源公众号"
# }
# 说明：文章A【不再照搬】公众号原文，而是把公众号文章当作"线索"，
#       去对应企业官网查证招聘信息后，用模板重新组织成一篇文章。

def _wrap_urls(text):
    if not text:
        return ""
    return re.sub(r'(https?://[^\s，。；<]+)',
                  r'<a href="\1" style="color:#2E6DA4;text-decoration:none;">\1</a>', text)


def render_a_positions(positions):
    cards = []
    for p in (positions or []):
        title = p.get("title") or p.get("岗位") or "（未命名岗位）"
        meta_parts = [p.get("count") or p.get("人数"),
                      p.get("salary") or p.get("薪资"),
                      p.get("location") or p.get("地点")]
        meta = " ｜ ".join(x for x in meta_parts if x)
        req = p.get("requirement") or p.get("要求") or ""
        jd = p.get("jd") or p.get("JD") or []
        if isinstance(jd, list):
            jd_html = "".join(f"<div style='margin:2px 0;'>· {x}</div>" for x in jd if x)
        else:
            jd_html = f"<div>{jd}</div>" if jd else ""
        card = (
            f'<section style="border:1px solid #e3e8ef;border-left:4px solid #2E6DA4;'
            f'border-radius:10px;padding:15px 16px;margin:12px 0;background:#fff;box-sizing:border-box;">'
            f'<div style="font-size:16px;font-weight:700;color:#1F4E78;">{title}</div>'
            + (f'<div style="font-size:13px;color:#5a6b7b;margin:6px 0;">{meta}</div>' if meta else '')
            + (f'<div style="font-size:13px;color:#33424f;margin:4px 0;"><b>任职要求：</b>{req}</div>' if req else '')
            + (f'<div style="font-size:13px;color:#33424f;margin:4px 0;"><b>岗位职责：</b>{jd_html}</div>' if jd_html else '')
            + '</section>')
        cards.append(card)
    if not cards:
        return '<div style="font-size:14px;color:#8895a3;margin:8px 0 14px;">（官网暂未公布具体岗位，详见企业官方招募页面）</div>'
    return "\n".join(cards)


def _pick_articleA_template():
    """从 templates/articleA/ 按轮换顺序选下一个模板，返回路径。无则 None。"""
    d = os.path.join(BASE, T2.get("articleA_templates_dir", "templates/articleA"))
    if not os.path.isdir(d):
        return None
    files = sorted(os.path.join(d, f) for f in os.listdir(d) if f.endswith(".html"))
    if not files:
        return None
    manifest = os.path.join(d, "MANIFEST.json")
    last = -1
    if os.path.exists(manifest):
        try:
            last = int(json.load(open(manifest, encoding="utf-8")).get("last", -1))
        except Exception:
            last = -1
    nxt = (last + 1) % len(files)
    try:
        json.dump({"last": nxt, "count": len(files)},
                  open(manifest, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    except Exception:
        pass
    return files[nxt]


DEFAULT_A_TEMPLATE = (
    '<!doctype html><html lang=zh><head><meta charset=utf-8></head><body>'
    '<section style="max-width:680px;margin:0 auto;font-family:sans-serif;color:#1f2d3d;line-height:1.75;">'
    '<div style="background:#1F4E78;color:#fff;padding:22px;font-size:20px;font-weight:800;">{{COMPANY}}</div>'
    '<div style="padding:16px 20px;"><div style="font-weight:700;color:#1F4E78;margin:10px 0;">公司简介</div>{{INTRO}}'
    '<div style="font-weight:700;color:#1F4E78;margin:14px 0 8px;">在招岗位</div>{{POSITIONS}}'
    '<div style="font-weight:700;color:#1F4E78;margin:14px 0 8px;">应聘方式</div>'
    '<div style="background:#f5f8fc;border-radius:10px;padding:14px;">{{APPLY}}</div>'
    '{{DEADLINE_BLOCK}}{{CONTACT_BLOCK}}'
    '<div style="font-size:12px;color:#8895a3;background:#f7f9fb;border-radius:8px;padding:12px;margin-top:14px;">{{SOURCE_NOTE}}</div>'
    '<div style="text-align:center;font-size:12px;color:#9aa6b2;margin-top:12px;">{{FOOTER}}</div></div></section></body></html>')


def build_articleA_from_source(source):
    """把企业官网结构化招聘数据渲染成发文稿A（模板版，不照搬公众号原文）。返回 (doc, company)。"""
    tpl_path = _pick_articleA_template()
    tpl = open(tpl_path, encoding="utf-8").read() if tpl_path else DEFAULT_A_TEMPLATE

    company = (source.get("company") or "招聘企业").strip()
    intro = source.get("intro") or ""
    positions = source.get("positions") or []
    apply = source.get("apply_method") or source.get("apply") or "详见企业官方招募页面。"
    deadline = source.get("deadline") or ""
    contact = source.get("contact") or ""
    sa = source.get("source_article") or {}
    sacct = source.get("source_account") or ""
    website = source.get("official_website") or source.get("recruit_page") or ""
    suffix = source.get("article_title") or "招聘信息（官网整理）"

    intro_block = (f'<div style="font-size:14px;color:#33424f;line-height:1.8;">{intro}</div>'
                   if intro else
                   '<div style="font-size:14px;color:#8895a3;">（暂无公司简介，详见企业官网）</div>')
    pos_html = render_a_positions(positions)
    apply_html = _wrap_urls(apply).replace("\n", "<br>")
    deadline_block = (f'<div style="font-size:14px;color:#33424f;margin:10px 0 0;">'
                      f'<b style="color:#1F4E78;">报名截止：</b>{deadline}</div>') if deadline else ""
    contact_block = (f'<div style="font-size:14px;color:#33424f;margin:10px 0 0;">'
                     f'<b style="color:#1F4E78;">联系方式：</b>{_wrap_urls(contact)}</div>') if contact else ""
    src_title = sa.get("title") or ""
    if sacct or src_title:
        src_note = (f'本文根据「{sacct}」发布的《{src_title}》招聘线索整理，信息来源于'
                    f'{company}官方网站（{website or "见企业官网"}）。招聘详情以企业官方发布为准。')
    else:
        src_note = f'本文整理自{company}官方网站（{website}）。招聘详情以企业官方发布为准。'
    footer = f"本页由招聘助手于 {TODAY} 自动整理，仅供参考。"

    doc = (tpl.replace("{{COMPANY}}", company)
              .replace("{{A_TITLE_SUFFIX}}", suffix)
              .replace("{{INTRO}}", intro_block)
              .replace("{{POSITIONS}}", pos_html)
              .replace("{{APPLY}}", apply_html)
              .replace("{{DEADLINE_BLOCK}}", deadline_block)
              .replace("{{CONTACT_BLOCK}}", contact_block)
              .replace("{{SOURCE_NOTE}}", src_note)
              .replace("{{FOOTER}}", footer))
    # 追加尾图（发布时由 _attach_tail_images 上传为 mmbiz；_place_tail_blocks 移入最后 </section>）
    tail_html = _tail_img_html()
    if tail_html:
        doc = doc.replace("</body>", tail_html + "</body>")
    return doc, company


# ---------- 发文稿B：96 微信风格模板 ----------
def _jd_html(jd):
    if isinstance(jd, list):
        items = "".join(f'<div style="margin:3px 0;">• {x}</div>' for x in jd if x)
        return items or "<div>（无JD描述）</div>"
    return jd or "<div>（无JD描述）</div>"


def render_job_cards(jobs, accent="#2E6DA4"):
    cards = []
    for j in jobs:
        title = j.get("title") or j.get("岗位名称") or "（未命名岗位）"
        meta_parts = [j.get("company") or j.get("公司"), j.get("salary") or j.get("薪资"),
                      j.get("location") or j.get("地点"), j.get("requirement") or j.get("要求")]
        meta = " ｜ ".join(p for p in meta_parts if p) or "（信息待补充）"
        cards.append(f"""
<div style="border:1px solid #e3e8ef;border-left:4px solid {accent};border-radius:10px;padding:16px;margin:14px 0;background:#fff;">
  <div style="font-size:17px;font-weight:700;color:{accent};">{title}</div>
  <div style="font-size:13px;color:#555;margin:6px 0;">{meta}</div>
  <div style="font-size:14px;color:#333;">{_jd_html(j.get("jd") or j.get("JD"))}</div>
</div>""")
    return "".join(cards)


def render_job_cards_refstyle(jobs):
    """仿照「企业招聘，就等你来」(irD868Xs1WNoobY1WS4SCQ) 的岗位卡片风格：
       蓝边框 + 黄色偏移阴影 + 黄圆点 + 蓝色标题 + 岗位职责列表。"""
    BLUE = "rgb(96, 158, 253)"
    YELLOW = "rgb(254, 229, 85)"
    WHITE = "rgb(254, 254, 254)"
    cards = []
    for j in jobs:
        title = j.get("title") or j.get("岗位名称") or "（未命名岗位）"
        meta_parts = [j.get("company") or j.get("公司", ""),
                      j.get("salary") or j.get("薪资", ""),
                      j.get("location") or j.get("地点", ""),
                      j.get("requirement") or j.get("要求", "")]
        meta_str = [p for p in meta_parts if p]
        jd_raw = j.get("jd") or j.get("JD", [])
        if isinstance(jd_raw, list):
            jd_html = "".join(f'<p>{x}</p>' for x in jd_raw if x)
        else:
            jd_html = f'<p>{jd_raw}</p>' if jd_raw else ""
        note = j.get("note", "")
        tags = j.get("tags", [])
        tag_html = ""
        if tags:
            tag_html = '<section style="margin-top:8px;font-size:12px;color:#888;">' \
                       + "  ".join(f'<span style="background:rgb(230,240,255);padding:2px 8px;border-radius:10px;margin-right:4px;">{t}</span>' for t in tags) \
                       + '</section>'
        note_html = (f'<p style="margin-top:8px;color:{YELLOW};">{note}</p>' if note else "")
        card = (
            f'<section style="border:1px solid {BLUE};'
            f'background-color:{WHITE};padding:20px 15px 15px;'
            f'box-shadow:{YELLOW} 7px 7px 1px;'
            f'margin:15px 0;box-sizing:border-box;">'
            # 标题行：黄圆点 + 蓝色大字
            f'<section style="margin-bottom:unset;">'
            f'<section style="width:30px;height:30px;background-color:{YELLOW};'
            f'border-radius:50%;margin-left:-5px;box-sizing:border-box;'
            f'margin-bottom:unset;overflow:hidden;line-height:0;"></section>'
            f'<section style="font-size:16px;letter-spacing:2px;line-height:1.75;'
            f'color:{BLUE};margin-top:-23px;margin-left:6px;margin-bottom:unset;">'
            f'<p><span style="font-family:宋体;font-size:20px;">{title}</span></p>'
            f'</section></section>'
            # 元信息行
            f'<section style="font-size:13px;color:#666;margin:10px 0 8px;">'
            f'<p>{" ｜ ".join(meta_str) if meta_str else ""}</p>'
            f'</section>'
            # 岗位职责
            f'<section style="font-size:14px;letter-spacing:1px;margin:12px 0;">'
            f'<p><span style="color:{BLUE};">岗位职责</span>：</p>{jd_html}'
            f'{note_html}'
            f'</section>{tag_html}'
            f'</section>')
        cards.append(card)
    return "\n".join(cards)


# ---------- 发文稿B 模板轮换 ----------
ACCENT_RE = re.compile(r"<!--\s*ACCENT:\s*(#[0-9A-Fa-f]{6})\s*-->", re.I)


def _list_96_templates():
    """返回所有可用于发文稿B的96模板（顶层 *.html + real/ 子目录），按路径排序。"""
    tpl96 = os.path.join(BASE, T2.get("templates_96_dir", "templates/96"))
    out = []
    if not os.path.isdir(tpl96):
        return out
    for fn in os.listdir(tpl96):
        fp = os.path.join(tpl96, fn)
        if fn.endswith(".html") and os.path.isfile(fp):
            out.append(fp)
    real = os.path.join(tpl96, "real")
    if os.path.isdir(real):
        for fn in os.listdir(real):
            fp = os.path.join(real, fn)
            if fn.endswith(".html") and os.path.isfile(fp):
                out.append(fp)
    return sorted(out)


def _extract_theme(path):
    """从真实96模板抽取主题色/背景色/头图，用于给发文稿B配色。"""
    try:
        html = open(path, encoding="utf-8").read()
    except Exception:
        return "#2E6DA4", "", ""
    accent = "#2E6DA4"
    m = ACCENT_RE.search(html)
    if m:
        accent = m.group(1)
    bg = ""
    mb = re.search(r'background-color:\s*(#[0-9A-Fa-f]{3,6})', html, re.I)
    if mb:
        bg = mb.group(1)
    hero = ""
    mi = re.search(r'background-image:\s*url\((?:&#39;|["\']?)(https?://[^)\"\']+)', html, re.I)
    if mi:
        hero = mi.group(1)
    return accent, bg, hero


def _pick_template():
    """从 templates/96/（含 real/）按轮换顺序选下一个，返回 (path, accent)。"""
    tpl96 = os.path.join(BASE, T2.get("templates_96_dir", "templates/96"))
    manifest = os.path.join(tpl96, "MANIFEST.json")
    files = _list_96_templates()
    if not files:
        # 回退：单模板 + 内置兜底
        single = os.path.join(BASE, T2["templates_dir"], f"{T2.get('articleB_template','96wx_cards')}.html")
        if os.path.exists(single):
            return single, "#2E6DA4"
        return None, "#2E6DA4"
    last = -1
    if os.path.exists(manifest):
        try:
            last = int(json.load(open(manifest, encoding="utf-8")).get("last", -1))
        except Exception:
            last = -1
    nxt = (last + 1) % len(files)
    chosen = files[nxt]
    try:
        json.dump({"last": nxt,
                   "note": "轮换发文稿B模板：每次 Task2 运行取 (last+1) % N 的下一个模板。N = templates/96 顶层 + real/ 内全部 *.html。",
                   "real_dir": "real", "count": len(files)},
                  open(manifest, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    except Exception:
        pass
    accent, _, _ = _extract_theme(chosen)
    return chosen, accent


def _tail_img_html():
    """收集 tail_images/ 下所有图片，作为 data: 内联图（发布时由 _sanitize_for_publish 上传为 mmbiz）。
    供发文稿A、B 文末统一追加。"""
    tail_html = ""
    tail_dir = os.path.join(BASE, T2["tail_images_dir"])
    if os.path.isdir(tail_dir):
        for fn in sorted(os.listdir(tail_dir)):
            fp = os.path.join(tail_dir, fn)
            if os.path.isfile(fp) and fn.lower().rsplit(".", 1)[-1] in ("png", "jpg", "jpeg", "gif", "webp"):
                tail_html += embed_img_file(fp)
    return tail_html


def build_articleB():
    # 确保当天日期夹存在，方便人工/AI 直接往里丢识别图
    src_dir = os.path.join(BASE, T2["b_photos_dir"], TODAY)
    os.makedirs(src_dir, exist_ok=True)
    ext_path = os.path.join(BASE, T2["b_extracted"])
    if not os.path.exists(ext_path):
        return None, "无 b_photos/extracted.json（未做视觉提取或当日无识别图片）"
    try:
        jobs = json.load(open(ext_path, encoding="utf-8"))
    except Exception as e:
        return None, f"extracted.json 解析失败: {e}"
    if not isinstance(jobs, list) or not jobs:
        return None, "extracted.json 为空，未生成发文稿B"

    tail_html = _tail_img_html()
    # 固定样式模式（仿照指定文章版式，不轮换）
    fixed_tpl_name = T2.get("articleB_style_fixed", "")
    page_title = T2.get("articleB_title", "本期精选岗位")
    if fixed_tpl_name:
        fixed_path = os.path.join(BASE, T2["templates_96_dir"], fixed_tpl_name)
        if os.path.exists(fixed_path):
            tpl = open(fixed_path, encoding="utf-8").read()
            cards = render_job_cards_refstyle(jobs)
            doc = (tpl.replace("{{PAGE_TITLE}}", page_title)
                      .replace("{{JOB_CARDS}}", cards)
                      .replace("{{FOOTER}}", f"本页由招聘助手于 {TODAY} 自动整理，仅供参考。"))
            return doc + tail_html, f"已用固定样式模板 {fixed_tpl_name}（仿照「企业招聘」风格）渲染 {len(jobs)} 个岗位卡片，并追加尾图"

    # 默认：轮换模板
    tpl_path, accent = _pick_template()
    cards = render_job_cards(jobs, accent)

    if tpl_path and os.path.exists(tpl_path):
        tpl = open(tpl_path, encoding="utf-8").read()
        if "{{JOB_CARDS}}" in tpl:
            # 手写占位模板：直接替换占位符
            doc = (tpl.replace("{{PAGE_TITLE}}", page_title)
                      .replace("{{JOB_CARDS}}", cards)
                      .replace("{{FOOTER}}", f"本页由招聘助手于 {TODAY} 自动整理，仅供参考。"))
            return doc + tail_html, f"已用模板 {os.path.basename(tpl_path)}（配色 {accent}）渲染 {len(jobs)} 个岗位卡片，并追加尾图"
        # 真实96模板（无占位符）：用其主题色/背景/头图套到我们的岗位卡片上
        _, bg, hero = _extract_theme(tpl_path)
        bg = bg or "#F2F2F2"
        hero_style = (f"background-image:url('{hero}');background-size:cover;background-position:center;"
                      if hero else f"background:{accent};")
        doc = (f'<section style="max-width:680px;margin:0 auto;font-family:sans-serif;color:#222;'
               f'line-height:1.7;background:{bg};">'
               f'<div style="padding:32px 20px;{hero_style}">'
               f'<div style="font-size:24px;font-weight:700;color:#fff;text-shadow:0 1px 4px rgba(0,0,0,.3);">{page_title}</div>'
               f'<div style="font-size:13px;color:#fff;opacity:.92;margin-top:6px;">{TODAY} · 招聘助手自动整理</div></div>'
               f'<div style="padding:18px 16px;">{cards}'
               f'<div style="padding:12px 0;color:#888;font-size:12px;text-align:center;">'
               f'本页由招聘助手于 {TODAY} 自动整理，仅供参考。</div></div></section>')
        return doc + tail_html, f"已用96模板 {os.path.basename(tpl_path)} 主题（配色 {accent}）渲染 {len(jobs)} 个岗位卡片，并追加尾图"
    # 内置兜底模板
    doc = (f'<div style="max-width:680px;margin:0 auto;font-family:sans-serif;color:#222;line-height:1.7;">'
           f'<div style="background:#1F4E78;color:#fff;padding:18px 22px;border-radius:10px 10px 0 0;">'
           f'<div style="font-size:20px;font-weight:700;">{page_title}</div></div>'
           f'{cards}'
           f'<div style="padding:14px 22px;color:#888;font-size:12px;">本页由招聘助手于 {TODAY} 自动整理，仅供参考。</div></div>')
    return doc + tail_html, "已用内置兜底模板渲染，并追加尾图"


# ---------- 发布到草稿箱（凭证门控） ----------
def _upload_inline_image(at, mime, raw_bytes, ext):
    """把一张图片字节上传到微信素材库，返回 mmbiz URL 或 None（带重试）。"""
    import uuid
    last_err = ""
    for attempt in range(3):
        try:
            boundary = "----WB" + uuid.uuid4().hex
            body = (f"--{boundary}\r\n"
                    f'Content-Disposition: form-data; name="media"; filename="img.{ext}"\r\n'
                    f"Content-Type: {mime}\r\n\r\n").encode() + raw_bytes + f"\r\n--{boundary}--\r\n".encode()
            req = urllib.request.Request(
                f"https://api.weixin.qq.com/cgi-bin/media/uploadimg?access_token={at}",
                data=body, headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
            resp = json.load(urllib.request.urlopen(req, timeout=30))
            if "url" in resp:
                return resp["url"]
            last_err = str(resp)
        except Exception as e:
            last_err = repr(e)
        print(f"  · 上传图片第{attempt+1}次失败: {last_err}")
    return None


def _sanitize_for_publish(content, at):
    """发布前清洗：data-src→src 还原真实图；内联 data: 图上传为 mmbiz 地址。"""
    # 1) 微信懒加载：data-src 才是真实图，移到 src（并去掉原占位 src）
    def move_datassrc(m):
        pre, real, post = m.group(1), m.group(2), m.group(3)
        pre = re.sub(r'\ssrc="[^"]*"', '', pre)
        post = re.sub(r'\ssrc="[^"]*"', '', post)
        return f'<img{pre} src="{real}"{post}'
    content = re.sub(r'<img\b([^>]*?)\bdata-src="([^"]+)"([^>]*)>', move_datassrc, content)
    # 2) 把内联 data:image 图都上传并替换（尾图 / 任何 base64 内联图）
    def up(m):
        mime = m.group(1)
        try:
            raw = base64.b64decode(m.group(2))
        except Exception:
            return m.group(0)
        ext = {"image/png": "png", "image/jpeg": "jpg", "image/jpg": "jpg",
               "image/gif": "gif", "image/webp": "webp"}.get(mime, "png")
        url = _upload_inline_image(at, mime, raw, ext)
        if url:
            return url
        return m.group(0)
    # 注意：re.sub 必须在 up() 函数体【之外】调用，否则上面的 return 会让它成为死代码
    content = re.sub(r'data:([^;]+);base64,([A-Za-z0-9+/=]+)', up, content)
    # 3) mmbiz 图强制 https（freepublish/add 拒绝 http:// 图，报 40066 invalid url）
    content = content.replace("http://mmbiz.qpic.cn", "https://mmbiz.qpic.cn")
    content = content.replace("http://mp.weixin.qq.com", "https://mp.weixin.qq.com")
    return content


def _upload_permanent_image(at, path):
    """上传图片到【永久素材】，返回 media_id（用作封面 thumb_media_id）。
    注意：正文配图用 media/uploadimg（返回 mmbiz URL）；封面必须用永久 media_id。"""
    if not (path and os.path.exists(path)):
        return None
    ext = os.path.splitext(path)[1].lower()
    mime = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
            ".gif": "image/gif", ".webp": "image/webp"}.get(ext, "image/jpeg")
    raw = open(path, "rb").read()
    boundary = "----WB" + uuid.uuid4().hex
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"media\"; "
            f"filename=\"c{ext}\"\r\nContent-Type: {mime}\r\n\r\n").encode() \
           + raw + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(
        f"https://api.weixin.qq.com/cgi-bin/material/add_material?access_token={at}&type=image",
        data=body, headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    try:
        resp = json.load(urllib.request.urlopen(req, timeout=30))
        return resp.get("media_id")
    except Exception as e:
        print(f"  · 封面上传失败: {e}")
        return None


def _get_thumb_media_id(at):
    """取封面永久 media_id：优先 tail_images 首图，回退 assets/fixed_tail.png。"""
    tail_dir = os.path.join(BASE, T2["tail_images_dir"])
    if os.path.isdir(tail_dir):
        for fn in sorted(os.listdir(tail_dir)):
            fp = os.path.join(tail_dir, fn)
            if os.path.isfile(fp) and fn.lower().rsplit(".", 1)[-1] in ("png", "jpg", "jpeg", "gif", "webp"):
                mid = _upload_permanent_image(at, fp)
                if mid:
                    return mid
    fallback = os.path.join(BASE, "assets", "fixed_tail.png")
    if os.path.exists(fallback):
        return _upload_permanent_image(at, fallback)
    return None


def _attach_tail_images(content, at):
    """发布前把尾图（tail_images/ 下图片，构建时为 data: 内联）预上传为 mmbiz 地址并直接替换，
    确保两篇草稿文末都带真实图床图（不依赖 _sanitize 对大段 base64 的正则碰运气）。"""
    tail_dir = os.path.join(BASE, T2["tail_images_dir"])
    if not os.path.isdir(tail_dir):
        return content
    for fn in sorted(os.listdir(tail_dir)):
        fp = os.path.join(tail_dir, fn)
        if not (os.path.isfile(fp) and fn.lower().rsplit(".", 1)[-1] in ("png", "jpg", "jpeg", "gif", "webp")):
            continue
        ext = os.path.splitext(fp)[1].lower().lstrip(".")
        mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
                "gif": "image/gif", "webp": "image/webp"}.get(ext, "image/png")
        raw = open(fp, "rb").read()
        url = _upload_inline_image(at, mime, raw, ext)
        if not url:
            print(f"  · 尾图 {fn} 上传失败，跳过（data: 将由 _sanitize 兜底）")
            continue
        url = url.replace("http://", "https://")
        marker = f"<!-- TAILIMG:{fn} -->"
        pat = r'<img\b([^>]*?)src="data:[^"]*"([^>]*?)>\s*' + re.escape(marker)
        content = re.sub(pat, lambda m: f'<img{m.group(1)}src="{url}"{m.group(2)}>' + marker, content)
    # 关键：微信 draft/add 会把正文末尾那串 </section> 之后的「兄弟节点」当文末垃圾丢弃。
    # 所以把所有尾图块移动到最后一个 </section> 之前（仍属正文内容树），确保入箱后可见。
    return _place_tail_blocks(content)


def _place_tail_blocks(content):
    """把 <!-- TAILIMG --> 尾图块（独立 <section> 包裹）挪到【最后一个 </section> 之内、作为该节最末子节点】。

    微信规则：会丢弃「正文最后一个 </section> 闭合标签之后的兄弟节点」。
    因此尾图必须留在最后一个 </section> 之内（不能甩在它之外），同时又是该节
    的【最后】子节点 → 既不被丢，又显示在该节末尾 = 整篇文末。

    对真实微信图文（A，正文本身多层 </section> 嵌套）这一点尤其关键：
    追加到整篇最末尾会落回"最后 </section> 之外"被丢弃；只有插进最后一个
    </section> 内部并置于其末尾才稳妥。
    """
    # 优先匹配 <section>...</section> 包裹的尾图块（新格式）
    blocks = re.findall(r'<section\b[^>]*>\s*<img[^>]*>\s*<!-- TAILIMG:[^>]*-->\s*</section>', content)
    if not blocks:
        bare = re.findall(r'<img[^>]*>\s*<!-- TAILIMG:[^>]*-->', content)
        blocks = [f'<section style="box-sizing:border-box;">{b}</section>' for b in bare]
    if not blocks:
        return content
    for b in blocks:
        content = content.replace(b, "")
    idx = content.rfind("</section>")
    if idx == -1:
        idx = content.rfind("</body>")
    if idx == -1:
        idx = len(content)
    return content[:idx] + "".join(blocks) + content[idx:]


def publish_to_draft(title, content, digest, author=""):
    """按官方规则清洗内容并推送到草稿箱（cgi-bin/draft/add）。返回 (success, msg)。
    必填：title(≤32字) / content / thumb_media_id(永久封面)。"""
    wx = config["wechat"]
    appid, secret = wx.get("appid"), wx.get("secret")
    if not (appid and secret):
        return False, "未配置微信 appid/secret"
    try:
        # 1) access_token
        tok_url = f"https://api.weixin.qq.com/cgi-bin/token?grant_type=client_credential&appid={appid}&secret={secret}"
        tok = json.load(urllib.request.urlopen(tok_url, timeout=20))
        if "access_token" not in tok:
            return False, f"获取 access_token 失败: {tok}"
        at = tok["access_token"]
        # 2) 先把尾图预上传并替换为真实 mmbiz 地址（A/B 文末都带）
        content = _attach_tail_images(content, at)
        # 3) 清洗内容（内联 data: 图上传为 mmbiz；data-src→src；http→https）
        content = _sanitize_for_publish(content, at)
        # 3) 封面永久 media_id（draft/add 必填）
        thumb = _get_thumb_media_id(at)
        if not thumb:
            return False, "无法获取封面 media_id（封面图上传失败）"
        # 4) 标题原样使用（不截断）、摘要≤128字
        title = title or "未命名文章"
        digest = (digest or "")[:128]
        payload = {"articles": [{
            "title": title,
            "author": author or "",
            "digest": digest,
            "content": content,
            "content_source_url": "",
            "thumb_media_id": thumb,
        }]}
        add_url = f"https://api.weixin.qq.com/cgi-bin/draft/add?access_token={at}"
        req = urllib.request.Request(add_url, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                                     headers={"Content-Type": "application/json"})
        resp = json.load(urllib.request.urlopen(req, timeout=30))
        if resp.get("errcode") == 0 or "media_id" in resp:
            return True, f"已加入草稿箱 media_id={resp.get('media_id')}"
        return False, f"draft/add 失败: {resp}"
    except Exception as e:
        return False, f"发布异常: {e}"


def _extract_media_id(msg):
    m = re.search(r'media_id=([A-Za-z0-9_-]+)', msg)
    return m.group(1) if m else ""


# ---------- 主流程 ----------
def main():
    links = read_links()
    if not links:
        print("selected_links.txt 为空 → Task2 跳过。")
        json.dump({"run_at": NOW_STR, "skipped": True, "reason": "no_link",
                   "articleA": False, "articleB": False},
                  open(os.path.join(BASE, "task2_status.json"), "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2)
        return

    url = links[0]
    print(f"处理链接: {url}")

    os.makedirs(os.path.join(BASE, T2["drafts_dir"]), exist_ok=True)

    # 发文稿A：优先走「线索→企业官网→模板整理」新流程；
    # 仅当 a_source.json 不存在时，回退到原文照搬（兼容旧稿）。
    a_source_path = os.path.join(BASE, T2.get("a_source", "a_source.json"))
    source = None
    if os.path.exists(a_source_path):
        try:
            source = json.load(open(a_source_path, encoding="utf-8"))
        except Exception:
            source = None
    if isinstance(source, dict) and (source.get("company") or source.get("positions")):
        a_doc, a_company = build_articleA_from_source(source)
        a_title = source.get("article_title") or f"{a_company} 招聘信息"
        a_digest = (source.get("intro") or source.get("apply_method") or "")[:128]
        print(f"  ✔ 发文稿A（官网整理）→ drafts/articleA.html（企业：{a_company}，岗位 {len(source.get('positions') or [])} 个）")
        # 消费 a_source.json，避免隔日复用到别的企业
        try:
            os.remove(a_source_path)
        except Exception:
            pass
    else:
        article = get_article(url)
        if not article:
            print("  ✘ 无法获取文章正文（实时与缓存均失败）→ 保留链接，待重试。")
            json.dump({"run_at": NOW_STR, "skipped": True, "reason": "fetch_failed", "url": url,
                       "articleA": False, "articleB": False},
                      open(os.path.join(BASE, "task2_status.json"), "w", encoding="utf-8"),
                      ensure_ascii=False, indent=2)
            return
        a_doc, _ = build_articleA(article)
        a_title = article["title"]
        a_digest = article.get("digest", "")
        print(f"  ✔ 发文稿A（原文照搬）→ drafts/articleA.html（尾图已附着）")

    a_path = os.path.join(BASE, T2["drafts_dir"], "articleA.html")
    open(a_path, "w", encoding="utf-8").write(a_doc)
    # 统计尾图（用于状态输出）
    tail_files = []
    tdir = os.path.join(BASE, T2["tail_images_dir"])
    if os.path.isdir(tdir):
        tail_files = [f for f in sorted(os.listdir(tdir))
                      if os.path.isfile(os.path.join(tdir, f))
                      and f.lower().rsplit(".", 1)[-1] in ("png", "jpg", "jpeg", "gif", "webp")]

    # 发文稿B
    b_doc, b_msg = build_articleB()
    has_b = False
    if b_doc:
        open(os.path.join(BASE, T2["drafts_dir"], "articleB.html"), "w", encoding="utf-8").write(b_doc)
        has_b = True
        print(f"  ✔ 发文稿B → drafts/articleB.html（{b_msg}）")
        # 处理完的 B 识别图按天移入 done/
        src_dir = os.path.join(BASE, T2["b_photos_dir"], TODAY)
        done_dir = os.path.join(BASE, T2["b_photos_done_dir"], TODAY)
        if os.path.isdir(src_dir):
            os.makedirs(done_dir, exist_ok=True)
            for fn in os.listdir(src_dir):
                sp = os.path.join(src_dir, fn)
                if os.path.isfile(sp):
                    try:
                        shutil.move(sp, os.path.join(done_dir, fn))
                    except Exception:
                        pass
    else:
        print(f"  · 发文稿B 未生成: {b_msg}")

    # 消费链接：删除已处理的首行
    consume_first_link(url)
    print(f"  → 已从 selected_links.txt 删除该链接")

    # 发布
    wechat = config["wechat"]
    has_cred = wechat.get("appid") and wechat.get("secret")
    if T2.get("publish_mode") == "auto" and has_cred:
        ok_a, msg_a = publish_to_draft(a_title, a_doc, a_digest)
        # 发文稿B 标题用 config.task2.articleB_title（如「企业招聘，就等你来」），
        # 切勿套用 A 标题，否则两篇标题雷同。
        b_title = T2.get("articleB_title", "本期精选岗位")
        ok_b, msg_b = (publish_to_draft(b_title, b_doc, "")
                       if has_b else (False, "无B稿"))
        media_a = _extract_media_id(msg_a) if ok_a else ""
        media_b = _extract_media_id(msg_b) if ok_b else ""
        publish_note = (f"草稿箱：A={'成功(media_id='+media_a+')' if ok_a else '失败('+msg_a+')'}；"
                        f"B={'成功(media_id='+media_b+')' if ok_b else '失败('+msg_b+')'}。"
                        f"人工在草稿箱审稿后自行发布。")
    else:
        media_a, media_b = "", ""
        publish_note = "发布模式=HTML草稿（未配置微信API凭证）；请将 drafts/articleA.html、articleB.html 正文分别粘贴至公众号编辑器，先A后B两次推送。配置 appid/secret 且 publish_mode=auto 后可自动推送到草稿箱。"

    json.dump({
        "run_at": NOW_STR, "skipped": False, "url": url,
        "articleA": True, "articleB": has_b,
        "mediaA": media_a, "mediaB": media_b,
        "tail_images": tail_files, "publish_note": publish_note,
    }, open(os.path.join(BASE, "task2_status.json"), "w", encoding="utf-8"),
        ensure_ascii=False, indent=2)
    print("  →", publish_note)
    print("Task2 完成。")


if __name__ == "__main__":
    main()
