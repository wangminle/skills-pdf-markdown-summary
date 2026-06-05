#!/usr/bin/env python3
"""
P0-01 环境变量优先级修复验证测试
测试优先级：CLI 参数 > 环境变量 > 默认值

直接测试 lib/env_priority.py 的核心机制，
不依赖 subprocess 运行完整提取脚本。

测试场景：
1. get_env_with_cli_priority 三级优先级（CLI > ENV > default）
2. was_arg_explicitly_passed 检测
3. collect_explicit_args 集合收集
4. parse_comma_list / parse_comma_set 解析
5. get_env_str / get_env_int / get_env_float / get_env_bool
6. apply_preset_robust 不覆盖显式参数
"""

import os
import sys

# 项目根目录：tests/scripts/ -> 向上三级
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPTS_DIR = os.path.join(PROJECT_ROOT, "skills", "pdf-markdown-summary", "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from lib.env_priority import (
    get_env_with_cli_priority,
    was_arg_explicitly_passed,
    collect_explicit_args,
    parse_comma_list,
    parse_comma_set,
    get_env_str,
    get_env_int,
    get_env_float,
    get_env_bool,
    apply_preset_robust,
)


def test_cli_overrides_env_and_default():
    """CLI 显式传参 > 环境变量 > 默认值"""
    os.environ["TEST_ENV_DPI"] = "400"
    # CLI 显式传了 dpi=200
    result = get_env_with_cli_priority(200, "TEST_ENV_DPI", 300, True, int)
    assert result == 200, f"CLI 显式传参应生效，期望 200，实际 {result}"
    os.environ.pop("TEST_ENV_DPI", None)
    print("  OK: CLI 显式传参 200 覆盖 ENV=400 和 default=300")


def test_env_overrides_default_when_no_cli():
    """无 CLI 时，ENV 覆盖默认值"""
    os.environ["TEST_ENV_DPI"] = "400"
    # CLI 没显式传，使用 ENV
    result = get_env_with_cli_priority(300, "TEST_ENV_DPI", 300, False, int)
    assert result == 400, f"ENV 应覆盖默认值，期望 400，实际 {result}"
    os.environ.pop("TEST_ENV_DPI", None)
    print("  OK: ENV=400 正确覆盖 default=300")


def test_default_when_no_cli_no_env():
    """无 CLI 无 ENV 时，使用默认值"""
    os.environ.pop("TEST_ENV_DPI", None)
    result = get_env_with_cli_priority(300, "TEST_ENV_DPI", 300, False, int)
    assert result == 300, f"默认值应生效，期望 300，实际 {result}"
    print("  OK: default=300 正确生效")


def test_was_arg_explicitly_passed():
    """检测 CLI 参数是否被显式传递"""
    argv = ['--pdf', 'paper.pdf', '--dpi', '200', '--preset', 'robust']
    assert was_arg_explicitly_passed('dpi', argv), "dpi 应被检测为显式传递"
    assert was_arg_explicitly_passed('preset', argv), "preset 应被检测为显式传递"
    assert not was_arg_explicitly_passed('clip_height', argv), "clip_height 没被传递"
    print("  OK: was_arg_explicitly_passed 正确检测")


def test_collect_explicit_args():
    """收集所有显式传递的参数名"""
    argv = ['--pdf', 'paper.pdf', '--dpi', '200', '--clip-height', '650']
    explicit = collect_explicit_args(argv)
    assert 'pdf' in explicit, "pdf 应在显式集合中"
    assert 'dpi' in explicit, "dpi 应在显式集合中"
    assert 'clip_height' in explicit, "clip-height 应转换为 clip_height"
    print("  OK: collect_explicit_args 正确收集")


def test_parse_comma_list_and_set():
    """逗号分隔列表解析"""
    assert parse_comma_list("1,2,3") == ["1", "2", "3"]
    assert parse_comma_list("S1, S2") == ["S1", "S2"]
    assert parse_comma_list("") == []
    assert parse_comma_set("1,2,S1") == {"1", "2", "S1"}
    print("  OK: parse_comma_list / parse_comma_set 正确解析")


def test_env_type_helpers():
    """环境变量类型转换"""
    os.environ["TEST_STR"] = "hello"
    assert get_env_str("TEST_STR") == "hello"
    assert get_env_str("TEST_STR_MISSING", "fallback") == "fallback"

    os.environ["TEST_INT"] = "42"
    assert get_env_int("TEST_INT") == 42
    assert get_env_int("TEST_INT_MISSING", 0) == 0

    os.environ["TEST_FLOAT"] = "3.14"
    assert get_env_float("TEST_FLOAT") == 3.14
    assert get_env_float("TEST_FLOAT_MISSING", 0.0) == 0.0

    os.environ["TEST_BOOL_T"] = "true"
    assert get_env_bool("TEST_BOOL_T") == True
    os.environ["TEST_BOOL_F"] = "0"
    assert get_env_bool("TEST_BOOL_F") == False
    assert get_env_bool("TEST_BOOL_MISSING", False) == False

    # 清理
    for k in ["TEST_STR", "TEST_INT", "TEST_FLOAT", "TEST_BOOL_T", "TEST_BOOL_F"]:
        os.environ.pop(k, None)
    print("  OK: get_env_str/int/float/bool 正确转换")


def test_apply_preset_robust_no_override_explicit():
    """apply_preset_robust 不覆盖显式传参"""
    import argparse
    args = argparse.Namespace(
        dpi=600,  # 用户显式传了 --dpi 600
        clip_height=650,
        margin_x=20,
        caption_gap=5,
        text_trim=False,
    )
    # 模拟 sys.argv 包含显式传参
    original_argv = sys.argv
    sys.argv = ['extract_pdf_assets.py', '--pdf', 'paper.pdf', '--dpi', '600']
    try:
        apply_preset_robust(args)
        # dpi 应保持用户传的 600，不应被 preset 覆盖成 300
        assert args.dpi == 600, f"dpi 不应被 preset 覆盖，期望 600，实际 {args.dpi}"
    finally:
        sys.argv = original_argv
    print("  OK: apply_preset_robust 不覆盖显式传参 dpi=600")


def main():
    print("\n" + "#"*60)
    print("# P0-01 环境变量优先级修复验证测试")
    print("# 优先级: CLI 参数 > 环境变量 > 默认值")
    print("#"*60)

    tests = [
        test_cli_overrides_env_and_default,
        test_env_overrides_default_when_no_cli,
        test_default_when_no_cli_no_env,
        test_was_arg_explicitly_passed,
        test_collect_explicit_args,
        test_parse_comma_list_and_set,
        test_env_type_helpers,
        test_apply_preset_robust_no_override_explicit,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            passed += 1
        except AssertionError as e:
            print(f"  FAIL: {e}")
            failed += 1
        except Exception as e:
            print(f"  ERROR: {e}")
            failed += 1

    print("\n" + "="*60)
    print(f"测试结果: {passed} 通过, {failed} 失败")
    print("="*60)

    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)