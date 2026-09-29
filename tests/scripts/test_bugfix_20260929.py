"""2026-09-29 P2 修复回归测试：无边框通栏表不被误收窄。

覆盖两个问题（详见当轮审查报告 P2）：
1. limit_table_clip_to_caption_column 只统计另一侧页面内的文字行数，
   无法区分「右栏正文」和「通栏表格右侧单元格」，无边框通栏表
   （合成输入 x=30..570）被收成半栏，右侧数据行出框；
2. 收窄同时作用于 base/search 且收窄不可逆：restore_table_clip_width
   以收窄后的 base 为恢复上限，阈值形同虚设，无法恢复原始框。
"""

from __future__ import annotations

import sys
from pathlib import Path

import fitz

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = PROJECT_ROOT / "skills" / "pdf-markdown-summary" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

PAGE = fitz.Rect(0, 0, 612, 792)
MID = (PAGE.x0 + PAGE.x1) / 2.0  # 306


def _full_width_table_lines(y0: float = 210.0, row_gap: float = 18.0, n: int = 3):
    """合成无边框通栏表：每行左单元格 + 右单元格 y 居中对齐。"""
    lines = []
    for i in range(n):
        y = y0 + i * row_gap
        lines.append((fitz.Rect(40, y, 250, y + 12), 9.0, f"Metric {i}"))
        lines.append((fitz.Rect(320, y, 560, y + 12), 9.0, "0.47 0.56"))
    return lines


# ---------------------------------------------------------------------------
# P2#1: 通栏表右侧单元格不得触发收窄
# ---------------------------------------------------------------------------

def test_full_width_borderless_table_not_narrowed() -> None:
    """右栏「数据单元格」与表内行 y 对齐时，不得按双栏正文收窄。"""
    from lib.table_refine import limit_table_clip_to_caption_column

    caption = fitz.Rect(70, 180, 280, 194)  # 题注在左栏
    clip = fitz.Rect(30, 200, 570, 280)     # 完整框 x=30..570
    limited = limit_table_clip_to_caption_column(
        clip, caption, PAGE, _full_width_table_lines(), [],
    )
    assert limited.x1 >= 570, (
        f"通栏表被误收窄，右侧数据行出框 (x1={limited.x1})"
    )
    assert limited.x0 <= 30


def test_two_column_body_text_still_narrows() -> None:
    """确认是无关正文（双栏排版、无跨栏行延续）时仍允许收窄。"""
    from lib.table_refine import limit_table_clip_to_caption_column

    caption = fitz.Rect(70, 180, 280, 194)
    clip = fitz.Rect(26, 200, 586, 360)
    right_body = [
        (fitz.Rect(330, 210, 540, 222), 10.0, "B1 dialogue continues on the right."),
        (fitz.Rect(330, 226, 540, 238), 10.0, "U1 another right-column line."),
    ]
    limited = limit_table_clip_to_caption_column(clip, caption, PAGE, right_body, [])
    assert limited.x1 < 320, f"双栏正文场景未收窄 (x1={limited.x1})"


def test_sentence_like_aligned_line_still_narrows() -> None:
    """右栏正文长句即使与左栏表行 y 对齐，也是正文，仍允许收窄。"""
    from lib.table_refine import limit_table_clip_to_caption_column

    caption = fitz.Rect(70, 180, 280, 194)
    clip = fitz.Rect(30, 200, 570, 280)
    long_sentence = (
        "The quick brown fox jumps over the lazy dog and keeps running "
        "across the entire right column of the page."
    )
    lines = _full_width_table_lines()
    # 右栏长句与每个表行 y 居中对齐（双栏基线对齐的典型形态）
    for i in range(3):
        y = 210.0 + i * 18.0
        lines.append((fitz.Rect(330, y - 1, 560, y + 11), 10.0, long_sentence))
    limited = limit_table_clip_to_caption_column(clip, caption, PAGE, lines, [])
    assert limited.x1 < 320, f"右栏正文长句场景未收窄 (x1={limited.x1})"


def test_vertically_overlapping_short_cells_are_not_narrowed() -> None:
    """PDF 字形框常有 5--7pt 偏移；只要行框明显重叠就应视为同行。"""
    from lib.table_refine import limit_table_clip_to_caption_column

    caption = fitz.Rect(70, 180, 280, 194)
    clip = fitz.Rect(30, 200, 570, 280)
    lines = []
    for i in range(3):
        y = 210.0 + i * 18.0
        lines.append((fitz.Rect(40, y, 250, y + 12), 9.0, f"Metric {i}"))
        # 右侧短行 y 偏移 7pt，中心差超过旧 3.5pt 死阈值，
        # 但两个 12pt 行框仍有 5pt 垂直重叠。
        lines.append((fitz.Rect(320, y + 7, 560, y + 19), 9.0, "0.47 0.56"))
    limited = limit_table_clip_to_caption_column(clip, caption, PAGE, lines, [])
    assert limited.x1 >= 570, f"行框重叠的右侧单元格被误切 (x1={limited.x1})"


def test_aligned_short_prose_still_narrows() -> None:
    """双栏正文与左栏表行共用基线时，不得仅凭 y 对齐当成表格单元。"""
    from lib.table_refine import limit_table_clip_to_caption_column

    caption = fitz.Rect(70, 180, 280, 194)
    clip = fitz.Rect(30, 200, 570, 280)
    lines = []
    prose = (
        "The model is evaluated on eight tasks",
        "These results are discussed in the appendix",
        "Our analysis covers all benchmark settings",
    )
    for i, text in enumerate(prose):
        y = 210.0 + i * 18.0
        lines.append((fitz.Rect(40, y, 250, y + 12), 9.0, f"Metric {i}"))
        lines.append((fitz.Rect(320, y, 560, y + 12), 10.0, text))
    limited = limit_table_clip_to_caption_column(clip, caption, PAGE, lines, [])
    assert limited.x1 < 320, f"对齐的右栏正文未收窄 (x1={limited.x1})"


# ---------------------------------------------------------------------------
# P2#2: 收窄不可逆——原始框显式传参作为恢复依据
# ---------------------------------------------------------------------------

def test_narrowed_clip_keeps_original_for_restore() -> None:
    """restore_table_clip_width 必须以收窄前的原始框为恢复上限。"""
    from lib.table_refine import (
        limit_table_clip_to_caption_column,
        restore_table_clip_width,
    )

    caption = fitz.Rect(70, 180, 280, 194)
    clip = fitz.Rect(30, 200, 570, 280)
    right_body = [
        (fitz.Rect(330, 210, 540, 222), 10.0, "B1 dialogue continues on the right."),
        (fitz.Rect(330, 226, 540, 238), 10.0, "U1 another right-column line."),
    ]
    base = limit_table_clip_to_caption_column(clip, caption, PAGE, right_body, [])
    assert base.x1 < 320, "构造前提不成立：未发生收窄"

    # 对象裁切把 final 误缩成窄条（宽度 < 原始框 40%）
    final = fitz.Rect(base.x0, base.y0, base.x0 + 40, base.y1)
    restored = restore_table_clip_width(
        final, base, table_band_changed=True, pre_narrow_clip=clip,
    )
    assert restored.x0 <= 30 and restored.x1 >= 570, (
        f"未恢复到收窄前原始框 (restored={restored})"
    )

    # 行带证据不成立时不得恢复（保持原守卫）
    kept = restore_table_clip_width(
        final, base, table_band_changed=False, pre_narrow_clip=clip,
    )
    assert list(kept) == list(final)


def test_restore_works_after_neighbor_caption_rebuild() -> None:
    """主链路 extract_tables 426→433→706：中间的 limit/expand 会重建矩形，
    restore 必须靠调用方显式保存的原始框恢复，不能依赖矩形自定义属性
    （fitz.Rect 拷贝构造会丢属性——旧属性方案在多表页必失效）。
    """
    from lib.clip_limit import limit_clip_by_neighbor_captions
    from lib.table_refine import (
        limit_table_clip_to_caption_column,
        restore_table_clip_width,
    )

    caption = fitz.Rect(70, 180, 280, 194)
    clip = fitz.Rect(30, 200, 570, 400)
    right_body = [
        (fitz.Rect(330, 210, 540, 222), 10.0, "B1 dialogue continues on the right."),
        (fitz.Rect(330, 226, 540, 238), 10.0, "U1 another right-column line."),
    ]
    base = limit_table_clip_to_caption_column(clip, caption, PAGE, right_body, [])
    assert base.x1 < 320, "构造前提不成立：未发生收窄"

    # 433 行：邻题注限制内部 fitz.Rect(clip) 重建矩形（旧属性方案在此丢失）
    neighbor = fitz.Rect(70, 360, 280, 374)  # 同栏下方邻题注
    base = limit_clip_by_neighbor_captions(base, caption, "below", [neighbor])
    assert not hasattr(base, "_pre_caption_column_clip"), (
        "矩形重建后自定义属性应已丢失——恢复不得依赖该属性"
    )

    final = fitz.Rect(base.x0, base.y0, base.x0 + 40, base.y1)
    # 显式传入收窄前原始框：即使 base 被收窄且重建过，仍能恢复
    restored = restore_table_clip_width(
        final, base, table_band_changed=True, pre_narrow_clip=clip,
    )
    assert restored.x0 <= 30 and restored.x1 >= 570, (
        f"主链路恢复失效 (restored={restored})"
    )
    # 对照：不传原始框时只能以收窄后的 base 为上限，无法恢复（旧行为）
    fallback = restore_table_clip_width(final, base, table_band_changed=True)
    assert fallback.x1 < 570
