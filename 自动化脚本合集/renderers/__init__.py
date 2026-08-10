# -*- coding: utf-8 -*-
"""渲染器：把 LLM 产出的结构化 JSON 渲染成公众号文章 HTML（全内联样式）。

入口为 render_article(data)，内部调用 templates/selector.py 选择模板，
再按 selector 返回的 renderer 名字反射调用本模块的渲染函数。

渲染策略：模板（templates/选出来/*.html）是 96 编辑器的成品文章，
无占位符，因此不复用其结构，只从中提取主题色（ACCENT 注释或主色），
sections 逐段渲染为内联样式片段，单顶层 <section> 包裹输出。
"""
import html
import importlib.util
import os
import re
from collections import Counter

BASE = os.path.dirname(os.path.abspath(__file__))
SELECTOR_PATH = os.path.join(os.path.dirname(BASE), "templates", "selector.py")

DEFAULT_ACCENT = "#237fb7"


# ---------------------------------------------------------------- selector

def _load_selector():
    """templates 不是包，用 importlib 按路径加载 selector.py。"""
    spec = importlib.util.spec_from_file_location("mp_selector", SELECTOR_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------- accent

def _is_dull(hex_color):
    """接近白/黑或纯灰的颜色不能当主题色。"""
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (1, 3, 5))
    if max(r, g, b) - min(r, g, b) < 24:  # 灰阶
        return True
    if r + g + b > 3 * 235 or r + g + b < 3 * 25:  # 近白 / 近黑
        return True
    return False


def extract_accent(template_html):
    """从模板 HTML 提取主题色。

    优先 <!-- ACCENT:#xxx --> 注释（跳过近白/近黑的无效值），
    否则统计模板中出现次数最多的非灰阶颜色。
    """
    m = re.search(r"<!--\s*ACCENT\s*:\s*(#[0-9A-Fa-f]{6})\s*-->", template_html)
    if m and not _is_dull(m.group(1)):
        return m.group(1).lower()

    candidates = [
        c.lower() for c in re.findall(r"#[0-9A-Fa-f]{6}\b", template_html)
        if not _is_dull(c)
    ]
    if candidates:
        return Counter(candidates).most_common(1)[0][0]
    return DEFAULT_ACCENT


def _extract_card_style(template_html):
    """从模板提取"内容卡"通用风格 token：底色/边框色/圆角/阴影/内边距。

    扫描所有带 background-color 的 style，找同时含 border+border-radius 的组合，
    取出现次数最多的作为卡片风格（96 模板的内容卡通常是米色底+细边框+圆角）。
    找不到返回空 dict，调用方退化为默认样式。
    """
    from collections import Counter
    combos = []
    for m in re.finditer(r'style="([^"]*background-color:(#[0-9A-Fa-f]{6})[^"]*)"', template_html):
        style = m.group(1)
        border = re.search(r'border:\s*\d+px\s+solid\s+(#[0-9A-Fa-f]{6})', style)
        radius = re.search(r'border-radius:\s*([0-9.]+px)', style)
        if border and radius:
            combos.append((m.group(2).lower(), border.group(1).lower(), radius.group(1).lower()))
    if not combos:
        return {}
    bg, brd, rad = Counter(combos).most_common(1)[0][0]

    shadow, padding = "", "16px 14px"
    for m in re.finditer(r'style="([^"]*)"', template_html):
        st = m.group(1)
        if "background-color:" + bg in st:
            sh = re.search(r'box-shadow:\s*([^;"\']+)', st)
            if sh:
                shadow = sh.group(1).strip()
            pd = re.search(r'padding:\s*([^;"\']+)', st)
            if pd:
                padding = pd.group(1).strip()
            break
    return {"bg": bg, "border": brd, "radius": rad, "shadow": shadow, "padding": padding}


# ---------------------------------------------------------------- helpers

def _esc(text):
    return html.escape(str(text or ""), quote=True)


def _font(flavor):
    if flavor == "solar":
        return "font-family:Kaiti SC,STKaiti,KaiTi,serif;"
    return "font-family:-apple-system,BlinkMacSystemFont,'Helvetica Neue',Helvetica,Arial,sans-serif;"


# ---------------------------------------------------------------- sections

def _hero(sec, accent, flavor, tpl_style=None):
    title = _esc(sec.get("title"))
    subtitle = _esc(sec.get("subtitle"))
    if flavor == "solar":
        parts = [
            f'<section style="margin:32px 0 24px;text-align:center;">',
            f'<p style="margin:0;font-size:26px;font-weight:bold;color:{accent};'
            f'letter-spacing:6px;{_font(flavor)}">{title}</p>',
        ]
        if subtitle:
            parts.append(
                f'<p style="margin:12px 0 0;font-size:14px;color:#888888;'
                f'letter-spacing:3px;{_font(flavor)}">{subtitle}</p>')
        parts.append(
            f'<section style="margin:18px auto 0;width:60px;border-top:2px solid {accent};"></section>')
        parts.append('</section>')
        return "".join(parts)

    parts = [
        f'<section style="margin:24px 0;padding:28px 16px;background-color:{accent};'
        f'border-radius:8px;text-align:center;">',
        f'<p style="margin:0;font-size:24px;font-weight:bold;color:#ffffff;'
        f'letter-spacing:2px;{_font(flavor)}">{title}</p>',
    ]
    if subtitle:
        parts.append(
            f'<p style="margin:10px 0 0;font-size:14px;color:#ffffff;opacity:0.85;'
            f'{_font(flavor)}">{subtitle}</p>')
    parts.append('</section>')
    return "".join(parts)


def _cards(sec, accent, flavor, tpl_style=None):
    out = []
    for item in sec.get("items", []):
        if tpl_style:
            st = tpl_style
            card_style = (f"margin:0 0 16px;padding:{st.get('padding', '16px 14px')};"
                          f"background-color:{st['bg']};border:1px solid {st['border']};"
                          f"border-radius:{st['radius']};")
            if st.get("shadow"):
                card_style += f"box-shadow:{st['shadow']};"
        else:
            card_style = (f"margin:0 0 16px;padding:16px;border:1px solid #eeeeee;"
                          f"border-left:4px solid {accent};border-radius:6px;"
                          f"background-color:#ffffff;")
        block = [
            f'<section style="{card_style}">',
            f'<p style="margin:0;font-size:17px;font-weight:bold;color:#333333;'
            f'{_font(flavor)}"><span style="display:inline-block;width:12px;height:12px;'
            f'background-color:{accent};border-radius:3px;margin-right:8px;'
            f'vertical-align:1px;"></span>{_esc(item.get("title"))}</p>',
        ]
        fields = item.get("fields") or {}
        if fields:
            rows = "".join(
                f'<p style="margin:6px 0 0;font-size:14px;color:#555555;{_font(flavor)}">'
                f'<span style="color:{accent};font-weight:bold;">{_esc(k)}：</span>'
                f'{_esc(v)}</p>'
                for k, v in fields.items())
            block.append(rows)
        tags = item.get("tags") or []
        if tags:
            chips = "".join(
                f'<span style="display:inline-block;margin:10px 6px 0 0;padding:2px 10px;'
                f'font-size:12px;color:{accent};border:1px solid {accent};'
                f'border-radius:10px;{_font(flavor)}">{_esc(t)}</span>'
                for t in tags)
            block.append(f'<section>{chips}</section>')
        desc = item.get("description")
        if desc:
            block.append(
                f'<p style="margin:10px 0 0;font-size:14px;color:#888888;'
                f'line-height:1.7;{_font(flavor)}">{_esc(desc)}</p>')
        block.append('</section>')
        out.append("".join(block))
    return "".join(out)


def _card_container(tpl_style, margin="20px 0"):
    """按模板风格生成内容卡容器（无模板风格时退化为普通 section）。"""
    if not tpl_style:
        return f'<section style="margin:{margin};">'
    st = tpl_style
    s = (f'margin:{margin};padding:{st.get("padding", "16px 14px")};'
         f'background-color:{st["bg"]};border:1px solid {st["border"]};'
         f'border-radius:{st["radius"]};')
    if st.get("shadow"):
        s += f'box-shadow:{st["shadow"]};'
    return f'<section style="{s}">'


def _key_points(sec, accent, flavor, tpl_style=None):
    title = _esc(sec.get("title"))
    points = "".join(
        f'<p style="margin:8px 0;font-size:15px;color:#444444;line-height:1.7;'
        f'{_font(flavor)}"><span style="display:inline-block;width:8px;height:8px;'
        f'margin-right:8px;background-color:{accent};border-radius:50%;'
        f'vertical-align:middle;"></span>{_esc(p)}</p>'
        for p in sec.get("points", []))
    return (
        _card_container(tpl_style) +
        f'<p style="margin:0 0 8px;font-size:17px;font-weight:bold;color:{accent};'
        f'{_font(flavor)}">{title}</p>{points}</section>')


def _paragraph(sec, accent, flavor, tpl_style=None):
    heading = sec.get("heading")
    text = _esc(sec.get("text"))
    align = "center" if flavor == "solar" else "left"
    parts = [_card_container(tpl_style)]
    if heading:
        parts.append(
            f'<p style="margin:0 0 8px;font-size:16px;font-weight:bold;color:#333333;'
            f'text-align:{align};{_font(flavor)}">{_esc(heading)}</p>')
    parts.append(
        f'<p style="margin:0;font-size:15px;color:#555555;line-height:1.8;'
        f'text-align:{align};{_font(flavor)}">{text}</p></section>')
    return "".join(parts)


def _image(sec, accent, flavor, tpl_style=None):
    url = _esc(sec.get("url"))
    caption = sec.get("caption")
    parts = [
        f'<section style="margin:24px 0;text-align:center;">'
        f'<img src="{url}" style="max-width:100%;border-radius:6px;"/>']
    if caption:
        parts.append(
            f'<p style="margin:8px 0 0;font-size:13px;color:#999999;'
            f'{_font(flavor)}">{_esc(caption)}</p>')
    parts.append('</section>')
    return "".join(parts)


_SECTION_RENDERERS = {
    "hero": _hero,
    "cards": _cards,
    "key_points": _key_points,
    "paragraph": _paragraph,
    "image": _image,
}


def _render_sections(data, accent, flavor, allowed=None, tpl_style=None):
    body = []
    for sec in data.get("sections", []):
        stype = sec.get("type")
        if allowed is not None and stype not in allowed:
            continue
        fn = _SECTION_RENDERERS.get(stype)
        if fn:
            body.append(fn(sec, accent, flavor, tpl_style))
    return "".join(body)


def _wrap(data, inner_html, accent, flavor):
    title = _esc(data.get("title"))
    digest = _esc(data.get("digest"))
    head = ""
    if title:
        head = (
            f'<p style="margin:0 0 4px;font-size:13px;color:#aaaaaa;text-align:center;'
            f'{_font(flavor)}">{title}</p>')
    if digest:
        head += (
            f'<p style="margin:0 0 12px;font-size:13px;color:#aaaaaa;text-align:center;'
            f'{_font(flavor)}">{digest}</p>')
    return (
        f'<section style="max-width:100%;padding:8px 4px;line-height:1.8;'
        f'word-break:break-word;{_font(flavor)}">{head}{inner_html}</section>')


# ---------------------------------------------------------------- renderers

def render_job_list(data, tpl, template_html):
    """招聘岗位：主题色 hero 色块 + 岗位卡片列表。"""
    accent = extract_accent(template_html)
    inner = _render_sections(data, accent, "job")
    return _wrap(data, inner, accent, "job")


def render_solar_term(data, tpl, template_html):
    """节气时令：居中、文雅排版（楷体、留白多）。"""
    accent = extract_accent(template_html)
    inner = _render_sections(data, accent, "solar")
    return _wrap(data, inner, accent, "solar")


def render_generic(data, tpl, template_html):
    """兜底：只按顺序渲染 hero / paragraph / key_points。"""
    accent = extract_accent(template_html)
    inner = _render_sections(data, accent, "job",
                             allowed={"hero", "paragraph", "key_points"})
    return _wrap(data, inner, accent, "job")


def _section_imbalance(part):
    """<section> 开闭差值（忽略自闭合标签）。"""
    opens = len(re.findall(r"<section\b(?![^>]*?/>)", part))
    closes = len(re.findall(r"</section>", part))
    return opens - closes


def _strip_leading_closes(text, n):
    """从开头剥掉 n 个 </section>。"""
    for _ in range(n):
        m = re.search(r"</section>", text)
        if not m:
            break
        text = text[:m.start()] + text[m.end():]
    return text


def render_inject(data, tpl, template_html):
    """注入式渲染：把渲染内容替换到模板的 <!-- INJECT_START/END --> 之间。

    模板其余部分（头部装饰、尾部二维码等）原样保留，实现"套版式"。
    两个标记之间的区域应是一组完整的兄弟块（自平衡）；若不平衡则做补偿。
    模板里没有标记时回退 render_generic。
    """
    marker_s = "<!-- INJECT_START -->"
    marker_e = "<!-- INJECT_END -->"
    i_s = template_html.find(marker_s)
    i_e = template_html.find(marker_e)
    if i_s < 0 or i_e < 0 or i_e <= i_s:
        return render_generic(data, tpl, template_html)

    accent = extract_accent(template_html)
    tpl_style = _extract_card_style(template_html)
    inner = _render_sections(data, accent, "job", tpl_style=tpl_style)
    content = f'<section class="_editor" data-role="injected">{inner}</section>'

    before = template_html[:i_s]
    region = template_html[i_s + len(marker_s):i_e]
    after = template_html[i_e + len(marker_e):]

    r = _section_imbalance(region)
    if r < 0:
        # 区域比开始多闭合了 |r| 个：原来由区域内闭合的标签需要补回
        content += "</section>" * (-r)
    elif r > 0:
        # 区域多开了 r 个，after 开头会有 r 个孤儿闭合，剥掉
        after = _strip_leading_closes(after, r)

    return before + content + after


def render_article(data):
    """分发入口：selector 选模板 + 渲染器名，反射调用对应渲染函数。"""
    selector = _load_selector()
    tpl, renderer_name = selector.classify_and_select(data)
    template_html = selector.load_template_html(tpl)
    fn = globals().get(renderer_name) if renderer_name else None
    if not callable(fn):
        fn = render_generic
    return fn(data, tpl, template_html)
