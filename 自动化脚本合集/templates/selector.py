# -*- coding: utf-8 -*-
"""模板选择器：根据 content_type 选择模板 + 渲染器。"""
import json, os
from datetime import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE, "selector_config.json")

_config = None


def _load_config():
    global _config
    if _config is None:
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, encoding="utf-8") as f:
                _config = json.load(f)
        else:
            _config = {"content_types": {}, "fallback": {}}
    return _config


def get_available_types():
    """返回所有已注册的内容类型列表。"""
    cfg = _load_config()
    return list(cfg.get("content_types", {}).keys())


def get_type_label(content_type):
    """返回内容类型的可读标签，如 '招聘岗位'。"""
    cfg = _load_config()
    ct = cfg.get("content_types", {}).get(content_type, {})
    return ct.get("label", content_type)


def list_templates(content_type):
    """返回某内容类型下的所有候选模板。"""
    cfg = _load_config()
    ct = cfg.get("content_types", {}).get(content_type, {})
    return ct.get("templates", [])


def select_template(content_type, template_id=None):
    """选择模板。

    优先：
    1. 显式指定 template_id
    2. 该类型的 default
    3. fallback
    """
    cfg = _load_config()
    ct = cfg.get("content_types", {}).get(content_type, {})

    # 1. 显式指定
    if template_id:
        for t in ct.get("templates", []):
            if t["id"] == template_id:
                return t
        # 指定的 id 不属于该类型，尝试全局查找（允许跨类型复用）

    # 2. 类型默认
    default_id = ct.get("default")
    if default_id:
        for t in ct.get("templates", []):
            if t["id"] == default_id:
                return t

    # 3. 回退
    fb = cfg.get("fallback", {})
    fb_file = fb.get("template")
    if fb_file:
        return {
            "id": "fallback",
            "name": "兜底模板",
            "file": fb_file,
            "style": "fallback",
            "renderer": fb.get("renderer", "")
        }

    return None


def get_renderer_name(content_type):
    """返回该内容类型对应的渲染器函数名。"""
    cfg = _load_config()
    ct = cfg.get("content_types", {}).get(content_type, {})
    return ct.get("renderer", "")


def classify_and_select(data):
    """根据结构化数据自动选择模板。

    参数：
        data: dict，必须包含 content_type，可选 style / template_id

    返回：
        (template_info, renderer_name)
    """
    content_type = data.get("content_type", "")
    template_id = data.get("template_id")
    style = data.get("style")

    tpl = select_template(content_type, template_id)
    if tpl is None:
        # content_type 未注册，尝试 fallback
        tpl = select_template("")
        renderer = ""
    else:
        renderer = get_renderer_name(content_type)

    # 如果数据里显式指定了 style，覆盖模板的 style（不影响文件选择）
    if style and tpl:
        tpl = dict(tpl)
        tpl["style_override"] = style

    return tpl, renderer


def load_template_html(template_info):
    """读取模板文件内容。"""
    if not template_info:
        return ""
    rel = template_info.get("file", "")
    path = os.path.join(BASE, rel)
    if not os.path.exists(path):
        return ""
    with open(path, encoding="utf-8") as f:
        return f.read()


if __name__ == "__main__":
    # 快速测试
    tests = [
        {"content_type": "job_list"},
        {"content_type": "job_list", "template_id": "zhaopin2"},
        {"content_type": "solar_term"},
        {"content_type": "unknown_type"},
    ]
    for d in tests:
        tpl, r = classify_and_select(d)
        print(f"input={d} -> template={tpl['id'] if tpl else None}, renderer={r}")
