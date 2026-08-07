#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
QA-01 统一测试入口

单命令跑全套测试：
  python3 tests/scripts/run_all.py

可选参数：
  -v, --verbose     显示详细输出
  --json            以 JSON 格式输出结果
  --skip-regex      跳过正则测试
  --skip-p0         跳过 P0 测试
  --skip-p1         跳过 P1 测试
  --with-golden     启用 golden 对比测试（默认已纳入，保留兼容）
  --skip-golden     跳过 golden 对比测试
  --update-golden   更新 golden 基准文件（隐含启用 golden 套件）

执行方式：
  各套件统一以 `python -m pytest <file> -q` 执行，保证 pytest 收集到的
  全量用例都被执行（而非各文件 main() 的手工清单）；通过 pytest 退出码
  判定套件成败（0=通过，非 0=失败，5=未收集到用例按跳过处理），
  通过/失败数从 pytest 输出解析，解析不到标记"数量未知"。

测试套件（共 8 个）：
1. P0 环境变量优先级测试 (test_p0_env_priority.py)
2. P1 标识符解析测试 (test_p1_ident_parsing.py)
3. QA-03 debug_artifacts 测试 (test_qa03_debug_artifacts.py)
4. QA-04 结构化日志测试 (test_qa04_structured_log.py)
5. QA-05 caption 锚点与正文污染测试 (test_caption_anchor_quality.py)
6. QA-06 PDF-to-Markdown CLI 输出路径测试 (test_pdf_to_markdown_cli.py)
7. 健壮性与一致性修复测试 (test_maintenance_fixes.py)
8. 正则表达式测试 (test_regex_patterns.py)
另有 Golden 对比测试 (test_extraction_golden.py)，默认纳入，--skip-golden 排除。
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

# 项目根目录：tests/scripts/ -> 向上三级
PROJECT_ROOT = Path(__file__).parent.parent.parent
TESTS_SCRIPTS_DIR = Path(__file__).parent  # tests/scripts/ 目录

# 允许跳过 golden 的环境变量（与 conftest.py 同口径；本地定向调试用的显式豁免）
ALLOW_GOLDEN_SKIP_ENV = "PDF_SKILL_ALLOW_GOLDEN_SKIP"


@dataclass
class TestSuiteResult:
    """测试套件结果"""
    name: str
    passed: int = 0
    failed: int = 0
    skipped: bool = False
    counts_unknown: bool = False   # 通过/失败数解析不到时置 True
    exit_code: int = 0
    duration_ms: int = 0
    messages: List[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return self.passed + self.failed

    @property
    def success(self) -> bool:
        """以退出码判定成败：exit 0=通过，非 0=失败"""
        return not self.skipped and self.exit_code == 0

    def counts_str(self) -> str:
        if self.counts_unknown:
            return "数量未知"
        return f"{self.passed}/{self.total}"


def run_command(cmd: List[str], cwd: Optional[Path] = None) -> Tuple[int, str, str]:
    """运行命令并返回 (exit_code, stdout, stderr)"""
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=str(cwd or PROJECT_ROOT),
    )
    return result.returncode, result.stdout, result.stderr


def parse_pytest_output(output: str) -> Optional[Tuple[int, int]]:
    """从 pytest 输出解析 (通过数, 失败数)；解析不到返回 None"""
    m_passed = re.search(r'(\d+)\s+passed', output)
    m_failed = re.search(r'(\d+)\s+failed', output)
    m_errors = re.search(r'(\d+)\s+error', output)

    if not (m_passed or m_failed or m_errors):
        return None

    passed = int(m_passed.group(1)) if m_passed else 0
    failed = (int(m_failed.group(1)) if m_failed else 0) + \
             (int(m_errors.group(1)) if m_errors else 0)
    return passed, failed


def parse_legacy_output(output: str) -> Optional[Tuple[int, int]]:
    """从脚本直接运行的中文输出解析 (通过数, 失败数)；解析不到返回 None"""
    m = re.search(r'(\d+)\s*通过.*?(\d+)\s*失败', output)
    if m:
        return int(m.group(1)), int(m.group(2))
    return parse_pytest_output(output)


def _fill_counts(result: TestSuiteResult, output: str, legacy: bool = False) -> None:
    """填充通过/失败数；解析不到标记"数量未知"（禁止空跑记 1 通过）"""
    parsed = parse_legacy_output(output) if legacy else parse_pytest_output(output)
    if parsed is None:
        result.counts_unknown = True
    else:
        result.passed, result.failed = parsed


def run_pytest_suite(
    name: str,
    script_path: Path,
    pytest_args: Optional[List[str]] = None,
    verbose: bool = False,
) -> TestSuiteResult:
    """以 pytest 运行单个测试套件"""
    result = TestSuiteResult(name=name)

    if not script_path.exists():
        result.skipped = True
        result.messages.append(f"脚本不存在: {script_path}")
        return result

    cmd = [sys.executable, "-m", "pytest", str(script_path)]
    cmd.extend(pytest_args if pytest_args is not None else ["-q"])

    start_time = time.time()
    exit_code, stdout, stderr = run_command(cmd)
    result.duration_ms = int((time.time() - start_time) * 1000)
    result.exit_code = exit_code

    output = stdout + stderr

    if exit_code == 5:
        # pytest 未收集到任何用例
        result.skipped = True
        result.messages.append("pytest 未收集到用例")
        return result

    _fill_counts(result, output)

    if verbose:
        result.messages.append(output)
    elif exit_code != 0:
        for line in output.split('\n'):
            if 'FAIL' in line or '失败' in line or 'failed' in line.lower():
                result.messages.append(line.strip())

    return result


def run_script_suite(
    name: str,
    script_path: Path,
    args: Optional[List[str]] = None,
    verbose: bool = False,
) -> TestSuiteResult:
    """直接以 python 运行脚本（仅用于 --update-golden 等 pytest 不支持的入口）"""
    result = TestSuiteResult(name=name)

    if not script_path.exists():
        result.skipped = True
        result.messages.append(f"脚本不存在: {script_path}")
        return result

    cmd = [sys.executable, str(script_path)] + list(args or [])

    start_time = time.time()
    exit_code, stdout, stderr = run_command(cmd)
    result.duration_ms = int((time.time() - start_time) * 1000)
    result.exit_code = exit_code

    output = stdout + stderr
    _fill_counts(result, output, legacy=True)

    if verbose:
        result.messages.append(output)

    return result


def main(argv: Optional[List[str]] = None) -> int:
    """主函数"""
    parser = argparse.ArgumentParser(
        description="QA-01 统一测试入口"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="显示详细输出"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="以 JSON 格式输出结果"
    )
    parser.add_argument(
        "--skip-regex",
        action="store_true",
        help="跳过正则测试"
    )
    parser.add_argument(
        "--skip-p0",
        action="store_true",
        help="跳过 P0 测试"
    )
    parser.add_argument(
        "--skip-p1",
        action="store_true",
        help="跳过 P1 测试"
    )
    parser.add_argument(
        "--with-golden",
        action="store_true",
        help="启用 golden 对比测试（默认已纳入，保留兼容）"
    )
    parser.add_argument(
        "--skip-golden",
        action="store_true",
        help="跳过 golden 对比测试（退出码非 0；需 "
             "PDF_SKILL_ALLOW_GOLDEN_SKIP=1 才视为合法跳过）"
    )
    parser.add_argument(
        "--update-golden",
        action="store_true",
        help="更新 golden 基准文件（隐含启用 golden 套件）"
    )

    args = parser.parse_args(argv)

    print("\n" + "#"*70)
    print("# QA-01 统一测试入口 - 单命令跑全套")
    print("#"*70)

    results: List[TestSuiteResult] = []

    test_suites = []

    if not args.skip_p0:
        test_suites.append({
            "name": "P0 环境变量优先级测试",
            "path": TESTS_SCRIPTS_DIR / "test_p0_env_priority.py",
        })

    if not args.skip_p1:
        test_suites.append({
            "name": "P1 标识符解析测试",
            "path": TESTS_SCRIPTS_DIR / "test_p1_ident_parsing.py",
        })

    # QA-03: debug 输出与 index 关联
    test_suites.append({
        "name": "QA-03 debug_artifacts 写入测试",
        "path": TESTS_SCRIPTS_DIR / "test_qa03_debug_artifacts.py",
    })

    # QA-04: 失败分级与结构化日志
    test_suites.append({
        "name": "QA-04 结构化日志 run.log.jsonl 测试",
        "path": TESTS_SCRIPTS_DIR / "test_qa04_structured_log.py",
    })

    test_suites.append({
        "name": "QA-05 caption 锚点与正文污染测试",
        "path": TESTS_SCRIPTS_DIR / "test_caption_anchor_quality.py",
    })

    test_suites.append({
        "name": "QA-06 PDF-to-Markdown CLI 输出路径测试",
        "path": TESTS_SCRIPTS_DIR / "test_pdf_to_markdown_cli.py",
    })

    test_suites.append({
        "name": "健壮性与一致性修复测试",
        "path": TESTS_SCRIPTS_DIR / "test_maintenance_fixes.py",
    })

    if not args.skip_regex:
        test_suites.append({
            "name": "正则表达式测试",
            "path": TESTS_SCRIPTS_DIR / "test_regex_patterns.py",
        })

    # 运行所有 pytest 套件
    for suite in test_suites:
        print(f"\n{'='*60}")
        print(f"运行: {suite['name']}")
        print('='*60)

        result = run_pytest_suite(
            name=suite["name"],
            script_path=suite["path"],
            pytest_args=[] if args.verbose else ["-q"],
            verbose=args.verbose,
        )
        results.append(result)
        _print_suite_result(result)

    # Golden 套件：A0-2 起默认纳入；--skip-golden 排除；--update-golden 走脚本直接入口
    golden_included = not args.skip_golden or args.update_golden
    if golden_included:
        print(f"\n{'='*60}")
        print("运行: Golden 对比测试")
        print('='*60)

        golden_path = TESTS_SCRIPTS_DIR / "test_extraction_golden.py"
        if args.update_golden:
            golden_args = ["--update-golden"]
            if args.verbose:
                golden_args.append("-v")
            result = run_script_suite(
                name="Golden 对比测试（更新基准）",
                script_path=golden_path,
                args=golden_args,
                verbose=args.verbose,
            )
        else:
            result = run_pytest_suite(
                name="Golden 对比测试",
                script_path=golden_path,
                pytest_args=(["-m", "golden"] if args.verbose else ["-q", "-m", "golden"]),
                verbose=args.verbose,
            )
        results.append(result)
        _print_suite_result(result)
    else:
        skipped = TestSuiteResult(
            name="Golden 对比测试",
            skipped=True,
            messages=["--skip-golden 指定跳过"],
        )
        results.append(skipped)
        print(f"\n  SKIP: Golden 对比测试 - {skipped.messages[0]}")

    # 汇总结果
    total_passed = sum(r.passed for r in results)
    total_failed = sum(r.failed for r in results)
    total_skipped = sum(1 for r in results if r.skipped)
    total_duration = sum(r.duration_ms for r in results)
    # 套件级成败以退出码判定，而非解析到的用例数
    suite_failures = sum(1 for r in results if not r.success and not r.skipped)

    print("\n" + "="*70)
    print("测试汇总")
    print("="*70)

    for r in results:
        if r.skipped:
            status = "SKIP"
        elif r.success:
            status = "OK"
        else:
            status = "FAIL"
        print(f"  {status}  {r.name}: {r.counts_str()} ({r.duration_ms}ms)")

    print("-"*70)
    print(f"  总计: {total_passed} 通过, {total_failed} 失败, {total_skipped} 跳过")
    print(f"  耗时: {total_duration}ms")
    print("="*70)

    if args.json:
        output = {
            "summary": {
                "passed": total_passed,
                "failed": total_failed,
                "skipped": total_skipped,
                "duration_ms": total_duration,
            },
            "suites": [
                {
                    "name": r.name,
                    "passed": r.passed,
                    "failed": r.failed,
                    "skipped": r.skipped,
                    "counts_unknown": r.counts_unknown,
                    "exit_code": r.exit_code,
                    "duration_ms": r.duration_ms,
                }
                for r in results
            ]
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))

    # A0-2：golden 被 --skip-golden 跳过时，verdict 必须明确且退出码非 0
    #（本地定向调试可设 PDF_SKILL_ALLOW_GOLDEN_SKIP=1 豁免，但仍打印 warning）
    golden_skipped = args.skip_golden and not args.update_golden
    if golden_skipped:
        if os.environ.get(ALLOW_GOLDEN_SKIP_ENV) == "1":
            print(
                f"\nWARNING: golden 套件被 --skip-golden 跳过"
                f"（{ALLOW_GOLDEN_SKIP_ENV}=1 已允许），本次不算全绿"
            )
        else:
            print("\nVERDICT: 部分运行，golden 被跳过，不算全绿")
            print(f"如确需排除，设环境变量 {ALLOW_GOLDEN_SKIP_ENV}=1")
            return 1

    return 0 if suite_failures == 0 else 1


def _print_suite_result(result: TestSuiteResult) -> None:
    """打印单个套件结果"""
    if result.skipped:
        print(f"  SKIP: {result.messages[0] if result.messages else '未知原因'}")
    elif result.success:
        print(f"  OK: {result.counts_str()} 通过 ({result.duration_ms}ms)")
    else:
        print(f"  FAIL: {result.counts_str()} ({result.duration_ms}ms)")
        for msg in result.messages[:5]:
            print(f"      {msg}")


if __name__ == "__main__":
    sys.exit(main())
