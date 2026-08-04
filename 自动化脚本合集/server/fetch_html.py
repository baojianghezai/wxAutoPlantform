# -*- coding: utf-8 -*-
"""抓取文章原文 HTML（仅 requests + 标准库）。

对外接口：
    fetch(url) -> str
        返回正文 HTML 片段；失败抛 RuntimeError（异常信息带 url）。

策略：
- 微信链接（mp.weixin.qq.com）：提取 id="js_content" 的 div 的 innerHTML。
- 其他站点：带 UA 抓取，依次尝试 <article>、常见正文容器
  （id/class 含 article/content/main/post/entry/text/body 的 div），
  都提取不到则返回整个 <body> 内容。
"""
import re

import requests

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

_CONTAINER_RE = re.compile(
    r'<div[^>]*(?:id|class)\s*=\s*"[^"]*(?:article|content|main|post|entry|text|body)[^"]*"',
    re.I,
)


def _get(url):
    try:
        resp = requests.get(url, headers={"User-Agent": UA}, timeout=30)
    except Exception as e:
        raise RuntimeError(f"抓取失败 {url}: {e}") from e
    if resp.status_code != 200:
        raise RuntimeError(f"抓取失败 {url}: HTTP {resp.status_code}")
    if not resp.encoding or resp.encoding.lower() == "iso-8859-1":
        resp.encoding = resp.apparent_encoding or "utf-8"
    return resp.text


def _extract_tag_inner(html_text, start_match):
    """从 start_match（一个开始标签的 re.Match）出发，按同名标签配平，
    返回开始标签之后到配对结束标签之前的 innerHTML。"""
    tag = re.match(r"<\s*([a-zA-Z0-9]+)", start_match.group(0))
    if not tag:
        return ""
    tag = tag.group(1).lower()
    pos = start_match.end()
    depth = 1
    token_re = re.compile(r"<\s*(/?)\s*" + re.escape(tag) + r"[^>]*>", re.I)
    for m in token_re.finditer(html_text, pos):
        if m.group(0).rstrip(">").endswith("/"):  # 自闭合
            continue
        if m.group(1):  # 结束标签
            depth -= 1
            if depth == 0:
                return html_text[pos:m.start()]
        else:
            depth += 1
    return ""


def _extract_wechat(html_text):
    m = re.search(r'<div[^>]*id\s*=\s*"js_content"[^>]*>', html_text, re.I)
    if not m:
        return ""
    return _extract_tag_inner(html_text, m).strip()


def _extract_generic(html_text):
    # 1) <article>
    m = re.search(r"<article[^>]*>", html_text, re.I)
    if m:
        inner = _extract_tag_inner(html_text, m).strip()
        if inner:
            return inner
    # 2) 常见正文容器
    for m in _CONTAINER_RE.finditer(html_text):
        inner = _extract_tag_inner(html_text, m).strip()
        if len(inner) > 200:  # 太短的大概率不是正文
            return inner
    # 3) 回退整个 body
    m = re.search(r"<body[^>]*>", html_text, re.I)
    if m:
        inner = _extract_tag_inner(html_text, m).strip()
        if inner:
            return inner
    return ""


def fetch(url):
    """抓取 url 的正文 HTML。失败抛 RuntimeError（带 url）。"""
    if not url:
        raise RuntimeError("抓取失败: url 为空")
    html_text = _get(url)
    if "mp.weixin.qq.com" in url:
        inner = _extract_wechat(html_text)
        if not inner:
            raise RuntimeError(f"抓取失败 {url}: 未找到 js_content 正文容器")
        return inner
    inner = _extract_generic(html_text)
    if not inner:
        raise RuntimeError(f"抓取失败 {url}: 未提取到正文内容")
    return inner
