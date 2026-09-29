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

from run_all import TestSuiteResult, find_unregistered_suites, run_pytest_suite, run_script_suite


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


def test_unregistered_guard_respects_explicitly_skipped_suites(tmp_path, monkeypatch) -> None:
    import run_all

    for name in ("test_p0_env_priority.py", "test_other.py", "test_new.py"):
        (tmp_path / name).write_text("", encoding="utf-8")
    monkeypatch.setattr(run_all, "TESTS_SCRIPTS_DIR", tmp_path)
    selected = [{"path": tmp_path / "test_other.py"}]

    missing = find_unregistered_suites(
        selected, ignored_files={"test_p0_env_priority.py"}
    )
    assert [path.name for path in missing] == ["test_new.py"]


def _run_pytest(args, env_override=None):
    import os
    import subprocess

    strip = ("PDF_SKILL_ALLOW_GOLDEN_SKIP", "PDF_SKILL_GOLDEN_EXTERNAL")
    env = {k: v for k, v in os.environ.items() if k not in strip}
    if env_override:
        env.update(env_override)
    return subprocess.run(
        [sys.executable, "-m", "pytest", *args, "-q", "--collect-only",
         "-p", "no:cacheprovider"],
        capture_output=True, text=True, cwd=str(PROJECT_ROOT), env=env,
    )


def test_golden_zero_collection_fails_session() -> None:
    """目录级选择下 golden 收集数为 0 必须判失败（AGENTS §8）。

    只统计「被 -m/-k 排除」会漏掉整类假绿：--ignore 掉 golden 套件后
    会话照常 0 退出，等于回归验证根本没跑。
    """
    golden = TESTS_SCRIPTS_DIR / "test_extraction_golden.py"
    result = _run_pytest([str(TESTS_SCRIPTS_DIR), f"--ignore={golden}"])

    assert result.returncode != 0, "golden 收集数为 0 时会话必须判失败"
    assert "未收集到任何 golden 用例" in (result.stderr + result.stdout)


def test_golden_zero_collection_honors_exemption_env() -> None:
    """显式豁免环境变量下允许定向排除（此时不算全绿，仅 WARNING）。"""
    golden = TESTS_SCRIPTS_DIR / "test_extraction_golden.py"
    result = _run_pytest(
        [str(TESTS_SCRIPTS_DIR), f"--ignore={golden}"],
        env_override={"PDF_SKILL_ALLOW_GOLDEN_SKIP": "1"},
    )

    assert result.returncode == 0, result.stderr[-500:]
    assert "PDF_SKILL_ALLOW_GOLDEN_SKIP=1 已允许" in (result.stderr + result.stdout)


def test_single_suite_selection_zero_collection_fails() -> None:
    """单文件选择下 golden 零收集同样判失败（评审#4 第 3 条）。

    原实现只对「目录级选择」生效，单跑一个非 golden 文件照常 exit 0
    ——与 AGENTS §8「golden 收集数为 0 一律判失败；定向排除需显式
    设置环境变量」不符。修复后单文件会话同样变红，除非显式豁免。
    """
    result = _run_pytest([str(TESTS_SCRIPTS_DIR / "test_run_all.py")])

    assert result.returncode != 0, (
        "单文件会话 golden 零收集必须判失败（AGENTS §8），"
        "如需定向调试请显式设 PDF_SKILL_ALLOW_GOLDEN_SKIP=1"
    )
    assert "未收集到任何 golden 用例" in (result.stderr + result.stdout)


def test_single_suite_selection_passes_with_golden_external_env() -> None:
    """run_all.py 的逐文件套件调用声明 PDF_SKILL_GOLDEN_EXTERNAL=1。

    统一入口按套件逐文件调用 pytest，golden 由该入口单独整轮执行；
    声明变量后单套件会话不因零收集变红（否则 run_all 每一套都失败）。
    该变量只应被 run_all.py 设置——见 run_command/run_pytest_suite 的
    extra_env 传递。
    """
    result = _run_pytest(
        [str(TESTS_SCRIPTS_DIR / "test_run_all.py")],
        env_override={"PDF_SKILL_GOLDEN_EXTERNAL": "1"},
    )

    assert result.returncode == 0, result.stderr[-500:]


def test_run_pytest_suite_declares_golden_external() -> None:
    """run_all 的套件调用必须向子进程声明 PDF_SKILL_GOLDEN_EXTERNAL。

    不声明的话，conftest 零收集闸门（评审#4 第 3 条后对单文件也生效）
    会让 run_all.py 的每一套都变红。
    """
    import run_all

    captured = {}

    def fake_run_command(cmd, cwd=None, extra_env=None):
        captured["extra_env"] = extra_env
        return 0, "1 passed", ""

    import subprocess  # noqa: F401  # ensure module import parity
    monkeypatch_target = "run_all.run_command"
    original = run_all.run_command
    run_all.run_command = fake_run_command
    try:
        suite = TESTS_SCRIPTS_DIR / "test_run_all.py"
        result = run_all.run_pytest_suite("probe", suite, golden_external=True)
    finally:
        run_all.run_command = original
    assert captured["extra_env"] == {run_all.GOLDEN_EXTERNAL_ENV: "1"}
    assert result.exit_code == 0


def test_golden_suite_invocation_omits_golden_external() -> None:
    """golden 套件本体调用不得声明外部放行（必须真实执行与统计）。"""
    import run_all

    captured = {}

    def fake_run_command(cmd, cwd=None, extra_env=None):
        captured["extra_env"] = extra_env
        return 0, "9 passed", ""

    original = run_all.run_command
    run_all.run_command = fake_run_command
    try:
        suite = TESTS_SCRIPTS_DIR / "test_extraction_golden.py"
        run_all.run_pytest_suite(
            "golden", suite, ["-q", "-m", "golden"], golden_external=False
        )
    finally:
        run_all.run_command = original
    assert captured["extra_env"] is None, (
        "golden 套件调用不应设 PDF_SKILL_GOLDEN_EXTERNAL（否则零收集闸门失效）"
    )
