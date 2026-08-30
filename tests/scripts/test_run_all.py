#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""run_all.py 统一入口：清单内套件缺失或零收集必须判失败，禁止假绿。"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
TESTS_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(TESTS_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_SCRIPTS_DIR))

from run_all import TestSuiteResult, run_pytest_suite, run_script_suite


def _suite_failures(results):
    return sum(1 for r in results if not r.success and not r.skipped)


def test_missing_suite_file_is_failure_not_skip(tmp_path: Path) -> None:
    missing = tmp_path / "does_not_exist.py"
    result = run_pytest_suite("missing suite", missing)

    assert result.skipped is False, "清单内脚本不存在应判失败，不能标记 skipped"
    assert result.exit_code != 0
    assert result.success is False
    assert _suite_failures([result]) == 1


def test_pytest_zero_collection_is_failure_not_skip(tmp_path: Path) -> None:
    empty = tmp_path / "test_empty_no_cases.py"
    empty.write_text("# no collected tests\n", encoding="utf-8")

    result = run_pytest_suite("empty suite", empty)

    assert result.skipped is False, "pytest 零收集（exit 5）应判失败，不能标记 skipped"
    assert result.exit_code == 5
    assert result.success is False
    assert _suite_failures([result]) == 1


def test_missing_script_suite_file_is_failure_not_skip(tmp_path: Path) -> None:
    missing = tmp_path / "missing_update_golden.py"
    result = run_script_suite("missing script suite", missing)

    assert result.skipped is False, "清单内脚本不存在应判失败，不能标记 skipped"
    assert result.exit_code != 0
    assert result.success is False
    assert _suite_failures([result]) == 1


def test_authorized_skip_is_excluded_from_suite_failures() -> None:
    skipped = TestSuiteResult(
        name="Golden 对比测试",
        skipped=True,
        messages=["--skip-golden 指定跳过"],
    )
    assert skipped.success is False
    assert _suite_failures([skipped]) == 0
