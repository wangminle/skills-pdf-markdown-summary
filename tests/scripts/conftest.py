# -*- coding: utf-8 -*-
"""tests/scripts 共享 pytest 配置。

A0-2「全绿定义收紧」：golden 用例默认纳入且必须实际执行、0 跳过。
被 -m / -k 等方式排除的 golden 用例会让整个会话判失败（退出码非 0），
除非显式设置环境变量 PDF_SKILL_ALLOW_GOLDEN_SKIP=1（此时打印醒目 warning）。
"""

import os
import sys

import pytest

# 允许排除 golden 用例的环境变量（本地定向调试用的显式豁免）
ALLOW_GOLDEN_SKIP_ENV = "PDF_SKILL_ALLOW_GOLDEN_SKIP"

# collection 阶段被排除的 golden 用例（由 pytest_deselected 回调填充）
_deselected_golden_items = []


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "golden: golden 对比用例（默认纳入普通运行；排除需 "
        "PDF_SKILL_ALLOW_GOLDEN_SKIP=1，否则会话判失败）",
    )


def pytest_deselected(items):
    """记录被 -m / -k 排除的 golden 用例（collection 阶段回调）"""
    for item in items:
        if item.get_closest_marker("golden") is not None:
            _deselected_golden_items.append(item)


@pytest.hookimpl(tryfirst=True)
def pytest_sessionfinish(session, exitstatus):
    """golden 用例被排除时强制会话变红（AGENTS §8：被跳过一律判失败）。

    - 未设豁免环境变量：打印失败原因并将退出码置为非 0；
    - 设了 PDF_SKILL_ALLOW_GOLDEN_SKIP=1：允许排除，但打印醒目 warning。
    """
    if not _deselected_golden_items:
        return
    count = len(_deselected_golden_items)
    if os.environ.get(ALLOW_GOLDEN_SKIP_ENV) == "1":
        print(
            f"\n{'!' * 70}\n"
            f"WARNING: {count} 个 golden 用例被排除"
            f"（{ALLOW_GOLDEN_SKIP_ENV}=1 已允许），本次运行不算全绿\n"
            f"{'!' * 70}",
            file=sys.stderr,
        )
        return
    print(
        f"\n{'=' * 70}\n"
        f"FAIL: {count} 个 golden 用例被排除，本次运行不算全绿：",
        file=sys.stderr,
    )
    for item in _deselected_golden_items:
        print(f"  - {item.nodeid}", file=sys.stderr)
    print(
        f"golden 被排除不算全绿；如确需排除，设环境变量 {ALLOW_GOLDEN_SKIP_ENV}=1\n"
        f"{'=' * 70}",
        file=sys.stderr,
    )
    session.exitstatus = 1
