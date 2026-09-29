# -*- coding: utf-8 -*-
"""tests/scripts 共享 pytest 配置。

A0-2「全绿定义收紧」：golden 用例默认纳入且必须实际执行、0 跳过、收集数非 0。
被 -m / -k 等方式排除的 golden 用例会让整个会话判失败（退出码非 0），
除非显式设置环境变量 PDF_SKILL_ALLOW_GOLDEN_SKIP=1（此时打印醒目 warning）。

「收集数为 0」的三种形态都要判失败（AGENTS §8）：
1. 收集后被 -m / -k 排除（pytest_deselected）；
2. 用例体内 skip（pytest_runtest_logreport）；
3. 会话根本没有收集到 golden（如 --ignore 掉 golden 套件、或只选了单个
   非 golden 文件）。golden 收集数为 0 一律判失败（评审#4 第 3 条）；
   run_all.py 按套件逐文件调用时显式设置 PDF_SKILL_GOLDEN_EXTERNAL=1
   声明「golden 由本入口另行整轮执行」，逐文件会话不判失败——该变量
   只能由统一测试入口设置，人工逐文件调试同样需要显式豁免
   （PDF_SKILL_ALLOW_GOLDEN_SKIP=1，仅 WARNING、不算全绿）。
"""

import os
import sys
from pathlib import Path

import pytest

# 允许排除 golden 用例的环境变量（本地定向调试用的显式豁免）
ALLOW_GOLDEN_SKIP_ENV = "PDF_SKILL_ALLOW_GOLDEN_SKIP"

# 统一测试入口声明「golden 由本入口另行整轮执行」的变量（run_all.py 设置）
GOLDEN_EXTERNAL_ENV = "PDF_SKILL_GOLDEN_EXTERNAL"

# golden 套件本体：用于判断本次会话的选择范围是否覆盖 golden
GOLDEN_TEST_FILE = Path(__file__).resolve().parent / "test_extraction_golden.py"

# collection 阶段被排除的 golden 用例（由 pytest_deselected 回调填充）
_deselected_golden_items = []

# 运行期被 pytest.skip() 跳过的 golden 用例（由 pytest_runtest_logreport 填充）
_skipped_golden_nodeids = []

# collection 阶段实际收集到的 golden 用例数
_collected_golden_count = 0


def _env_allows_skip() -> bool:
    return os.environ.get(ALLOW_GOLDEN_SKIP_ENV) == "1"


def _golden_run_externally() -> bool:
    """run_all.py 逐文件调用时声明 golden 由统一入口另行整轮执行。"""
    return os.environ.get(GOLDEN_EXTERNAL_ENV) == "1"


def _selection_covers_golden(config) -> bool:
    """本次会话的选择范围是否「应该」包含 golden 套件。

    评审#4 第 3 条：golden 收集数为 0 一律判失败（AGENTS §8），不再对
    「目录级选择」与「单文件选择」区别对待——单跑一个非 golden 文件
    同样是零收集会话，exit 0 会让「看起来全绿」的假绿复活。
    豁免路径只有两条：run_all.py 的显式声明（PDF_SKILL_GOLDEN_EXTERNAL=1，
    golden 由该入口单独整轮执行）与本地定向调试的
    PDF_SKILL_ALLOW_GOLDEN_SKIP=1（仅 WARNING、不算全绿）。
    """
    return True


def _fail_session(session, reason_lines) -> None:
    print(f"\n{'=' * 70}", file=sys.stderr)
    for line in reason_lines:
        print(line, file=sys.stderr)
    print(
        f"golden 被排除或跳过不算全绿；如确需排除，设环境变量 {ALLOW_GOLDEN_SKIP_ENV}=1\n"
        f"{'=' * 70}",
        file=sys.stderr,
    )
    session.exitstatus = 1


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "golden: golden 对比用例（默认纳入普通运行；排除需 "
        "PDF_SKILL_ALLOW_GOLDEN_SKIP=1，否则会话判失败）",
    )


def pytest_collection_modifyitems(session, config, items):
    """记录本次会话收集到的 golden 用例数（含被后续 -m / -k 排除之前的全量）。"""
    global _collected_golden_count
    _collected_golden_count = sum(
        1 for item in items if item.get_closest_marker("golden") is not None
    )


def pytest_deselected(items):
    """记录被 -m / -k 排除的 golden 用例（collection 阶段回调）"""
    for item in items:
        if item.get_closest_marker("golden") is not None:
            _deselected_golden_items.append(item)


def pytest_runtest_logreport(report):
    """记录运行期被 pytest.skip() 跳过的 golden 用例。

    pytest_deselected 只覆盖 collection 阶段的 -m / -k 排除，
    用例体内或 fixture 里调用 skip 不会经过它。
    """
    if report.skipped and "golden" in getattr(report, "keywords", {}):
        if report.nodeid not in _skipped_golden_nodeids:
            _skipped_golden_nodeids.append(report.nodeid)


@pytest.hookimpl(tryfirst=True)
def pytest_sessionfinish(session, exitstatus):
    """golden 用例被排除 / 跳过 / 根本没收集时强制会话变红（AGENTS §8）。

    - 未设豁免环境变量：打印失败原因并将退出码置为非 0；
    - 设了 PDF_SKILL_ALLOW_GOLDEN_SKIP=1：允许排除，但打印醒目 warning；
    - run_all.py 的逐文件调用设 PDF_SKILL_GOLDEN_EXTERNAL=1 声明 golden
      由统一入口另行整轮执行，零收集不判失败。
    """
    skipped_ids = [item.nodeid for item in _deselected_golden_items]
    skipped_ids += [n for n in _skipped_golden_nodeids if n not in skipped_ids]

    zero_collected = (
        _collected_golden_count == 0
        and _selection_covers_golden(session.config)
        and not _golden_run_externally()
    )

    if not skipped_ids and not zero_collected:
        return

    if _golden_run_externally() and not skipped_ids:
        # run_all.py 套件式调用：golden 由该入口单独执行，此处静默放行
        return

    if _env_allows_skip():
        detail = (
            f"{len(skipped_ids)} 个 golden 用例被排除或跳过"
            if skipped_ids
            else "未收集到任何 golden 用例"
        )
        print(
            f"\n{'!' * 70}\n"
            f"WARNING: {detail}（{ALLOW_GOLDEN_SKIP_ENV}=1 已允许），"
            f"本次运行不算全绿\n{'!' * 70}",
            file=sys.stderr,
        )
        return

    lines = []
    if skipped_ids:
        lines.append(f"FAIL: {len(skipped_ids)} 个 golden 用例被排除或跳过，本次运行不算全绿：")
        lines.extend(f"  - {nodeid}" for nodeid in skipped_ids)
    if zero_collected:
        lines.append(
            "FAIL: 本次会话未收集到任何 golden 用例（golden 收集数为 0 一律判失败）"
        )
        lines.append(f"  - golden 套件: {GOLDEN_TEST_FILE}")
    _fail_session(session, lines)
