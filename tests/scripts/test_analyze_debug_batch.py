#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
analyze_debug_batch.py 回归测试。

覆盖 fallback_to_baseline 判据（20260928 修复，20260929 增补 x 向判据）：
仅高度比值≈1 不算回退——phase_d 收缩后 expand_clip_to_nearby_figure_title
（BUG-079）把图内标题扩回来，final 高度接近 baseline 但 y 边界不重合，
属预期精修。只有 y0/y1 与 baseline 基本重合（差 < 2pt）才是真回退。
20260928-045 批次 7 个旧信号中 6 个为该类误报。

20260929 增补：x 方向同理。final y 与 baseline 重合但 x0/x1 已明显收缩
（如宽度只剩基准 60%）说明裁剪真正生效，是预期精修而非回退原框，
同样不得误报 fallback_to_baseline；真回退要求 x/y 四边均基本重合。

另覆盖 main() 输出完整性：flagged 项超过 12 个时不得静默截断
（20260928-045 批次 98 项 flagged 只打印 76 项）。
"""

from __future__ import annotations

import contextlib
import io
import os
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "tests", "scripts"))

from analyze_debug_batch import main as analyze_main
from analyze_debug_batch import parse_legend


def _write_legend(path: Path, *, stage_rects: dict) -> None:
    """按 debug legend 实际格式写一份合成 legend。

    stage_rects: {"baseline": (x0,y0,x1,y1), "phase_d": (...), "final": (...)}
    """
    lines = [f"=== Figure 1 Debug Legend (Page 3) ===", ""]
    lines.append("Caption: 72.0,44.0 -> 540.0,84.0 (468.0x40.0pt)")
    lines.append("")
    for name in ("baseline", "phase_a", "phase_b", "phase_d", "final"):
        if name not in stage_rects:
            continue
        x0, y0, x1, y1 = stage_rects[name]
        w, h = x1 - x0, y1 - y0
        lines.append(f"{name}:")
        lines.append(f"  Position: {x0},{y0} -> {x1},{y1}")
        lines.append(f"  Size: {w}×{h}pt")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def test_true_fallback_y_edges_match_baseline() -> None:
    """x/y 四边均与 baseline 重合且 phase_d 收缩 → 应标记 fallback_to_baseline。"""
    with tempfile.TemporaryDirectory() as td:
        legend = Path(td) / "Figure_1_p3_stages_legend.txt"
        _write_legend(
            legend,
            stage_rects={
                "baseline": (26.0, 517.9, 586.0, 694.5),
                "phase_d": (114.0, 527.5, 497.0, 690.2),  # 高度比 0.80
                # 20260929 起 x 也参与判定：final x 须与 baseline 基本重合
                "final": (26.5, 518.8, 585.5, 694.2),    # x/y 四边差均 < 2pt
            },
        )
        a = parse_legend(legend)
        assert a is not None, "legend 解析失败"
        assert "fallback_to_baseline" in a.notes, f"真回退未被标记: {a.notes}"


def test_title_reexpand_not_flagged_as_fallback() -> None:
    """final 高度≈baseline 但 y0 明显下移（图内标题回扩）→ 不得误报回退。

    复刻 20260928-045 Kimi Figure 9 p15：phase_d y0=261.4 收缩后，
    expand_clip_to_nearby_figure_title 把 final y0 扩回 188.9
    （baseline y0=183.1，差 5.8pt > 2pt），final/baseline 高度比 0.993。
    旧判据（仅看高度比）会误报 fallback_to_baseline。
    """
    with tempfile.TemporaryDirectory() as td:
        legend = Path(td) / "Figure_9_p15_stages_legend.txt"
        _write_legend(
            legend,
            stage_rects={
                "baseline": (26.0, 183.1, 586.0, 437.9),
                "phase_d": (114.8, 261.4, 497.6, 438.1),  # 高度比 0.69
                "final": (114.8, 188.9, 497.6, 441.9),    # y0 差 5.8pt → 标题回扩
            },
        )
        a = parse_legend(legend)
        assert a is not None, "legend 解析失败"
        assert "fallback_to_baseline" not in a.notes, (
            f"标题回扩被误报为回退: {a.notes}"
        )


def test_final_small_h_still_flagged() -> None:
    """final_small_h 判据不受本次修改影响。"""
    with tempfile.TemporaryDirectory() as td:
        legend = Path(td) / "Table_3_p7_stages_legend.txt"
        _write_legend(
            legend,
            stage_rects={
                "baseline": (66.1, 507.8, 527.6, 719.7),
                "phase_b": (66.1, 560.0, 527.6, 719.7),
                "final": (66.1, 630.0, 527.6, 719.7),  # 高度比 ≈ 0.42 < 0.55
            },
        )
        a = parse_legend(legend)
        assert a is not None
        assert any(n.startswith("final_small_h=") for n in a.notes), f"{a.notes}"


def test_x_shrink_not_flagged_as_fallback() -> None:
    """final y 与 baseline 重合但 x 向已收缩 → 裁剪生效，不得误报回退。

    复现 20260929 缺陷：旧判据只比较 y0/y1，x 宽度已缩到基准 60% 的框
    （裁掉左右空白是预期精修）仍被误报 fallback_to_baseline。
    """
    with tempfile.TemporaryDirectory() as td:
        legend = Path(td) / "Figure_2_p5_stages_legend.txt"
        _write_legend(
            legend,
            stage_rects={
                "baseline": (26.0, 300.0, 586.0, 500.0),   # 宽 560
                "phase_d": (135.0, 320.0, 477.0, 498.0),   # 高度比 0.89
                "final": (135.0, 300.5, 477.0, 499.5),     # y 差 < 2pt，宽 342 ≈ 60%
            },
        )
        a = parse_legend(legend)
        assert a is not None, "legend 解析失败"
        assert "fallback_to_baseline" not in a.notes, (
            f"x 向收缩被误报为回退: {a.notes}"
        )


def test_main_prints_all_flagged_items() -> None:
    """flagged 超过 12 项时 main() 不得静默截断（20260928-045 只打印 76/98）。"""
    n_flagged = 15
    with tempfile.TemporaryDirectory() as td:
        batch = Path(td) / "20260929-001"
        dbg = batch / "SomePDF" / "images" / "debug"
        dbg.mkdir(parents=True)
        for i in range(n_flagged):
            legend = dbg / f"Figure_{i + 1}_p1_stages_legend.txt"
            _write_legend(
                legend,
                stage_rects={
                    "baseline": (26.0, 300.0, 586.0, 500.0),
                    "phase_b": (26.0, 360.0, 586.0, 500.0),
                    "final": (26.0, 430.0, 586.0, 500.0),  # 高度比 0.35 → final_small_h
                },
            )
        buf = io.StringIO()
        old_argv = sys.argv
        sys.argv = ["analyze_debug_batch.py", str(batch)]
        try:
            with contextlib.redirect_stdout(buf):
                rc = analyze_main()
        finally:
            sys.argv = old_argv
        assert rc == 0
        flag_lines = [l for l in buf.getvalue().splitlines() if l.startswith("  FLAG ")]
        assert len(flag_lines) == n_flagged, (
            f"flagged 输出被截断：只打印 {len(flag_lines)}/{n_flagged} 项"
        )


def main() -> int:
    tests = [
        test_true_fallback_y_edges_match_baseline,
        test_title_reexpand_not_flagged_as_fallback,
        test_final_small_h_still_flagged,
        test_x_shrink_not_flagged_as_fallback,
        test_main_prints_all_flagged_items,
    ]
    passed = failed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except AssertionError as e:
            print(f"FAIL {t.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"ERROR {t.__name__}: {e}")
            failed += 1
    print(f"\n测试结果: {passed} 通过, {failed} 失败")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
