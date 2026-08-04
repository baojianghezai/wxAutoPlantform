# -*- coding: utf-8 -*-
"""publish — 微信公众号草稿箱发布模块。

从 task2_publish.py 提炼的发布相关逻辑（仅标准库），对外暴露 push_to_draft。
"""
from .wechat_draft import push_to_draft

__all__ = ["push_to_draft"]
