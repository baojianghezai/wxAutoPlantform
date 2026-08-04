# -*- coding: utf-8 -*-
"""冒烟测试：用一小段测试 HTML 调 push_to_draft 做一次真实推送，打印结果。

用法（在项目根目录下）：
    python -m publish.test_draft
    或
    python publish/test_draft.py
"""
import os
import sys

# 允许直接以脚本方式运行（python publish/test_draft.py）：把项目根加入 sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from publish import push_to_draft

TEST_HTML = (
    '<!doctype html><html lang=zh><head><meta charset=utf-8></head><body>'
    '<section style="box-sizing:border-box;">'
    '<p>这是一条 publish 模块的冒烟测试草稿，请忽略。</p>'
    '</section></body></html>'
)


def main():
    mid = push_to_draft("publish 模块冒烟测试", TEST_HTML,
                        author="自动化脚本", digest="冒烟测试，请忽略")
    print(f"✔ 推送成功，media_id={mid}")


if __name__ == "__main__":
    main()
