#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Crop acceptance thresholds and text-pollution checks."""

from __future__ import annotations

from typing import Any, List, Tuple

try:
    import fitz
except ImportError:
    fitz = None  # type: ignore


def adaptive_acceptance_thresholds(
    base_height: float,
    *,
    is_table: bool = False,
    far_cov: float = 0.0,
) -> "AcceptanceThresholds":
    """
    根据基线高度和远侧覆盖率动态计算验收阈值。

    策略：
    - 大图（>400pt）：允许更激进的精裁
    - 中等图（200-400pt）：使用默认阈值
    - 小图（<200pt）：更保守
    - 远侧文字覆盖率越高，允许缩小得越多

    Args:
        base_height: 基线窗口高度（pt）
        is_table: 是否为表格
        far_cov: 远侧文字覆盖率（0.0-1.0）

    Returns:
        AcceptanceThresholds 对象
    """
    from .models import AcceptanceThresholds as AT

    # 基础阈值（根据尺寸分层）
    if base_height > 400:
        base_h, base_a = (0.50, 0.45) if is_table else (0.55, 0.50)
        base_ink, base_cov, base_text = 0.85, 0.80, 0.70
        desc = "large"
    elif base_height > 200:
        base_h, base_a = (0.50, 0.45) if is_table else (0.60, 0.55)
        base_ink, base_cov, base_text = 0.90, 0.85, 0.75
        desc = "medium"
    else:
        base_h, base_a = (0.65, 0.60) if is_table else (0.70, 0.65)
        base_ink, base_cov, base_text = 0.92, 0.88, 0.80
        desc = "small"

    # 根据远侧覆盖率进一步调整
    if far_cov >= 0.60:
        base_h = min(base_h, 0.35)
        base_a = min(base_a, 0.25)
        base_ink = min(base_ink, 0.70)
        base_cov = min(base_cov, 0.70)
        base_text = min(base_text, 0.55)
        desc += "+high_far_cov"
    elif far_cov >= 0.30:
        base_h = min(base_h, 0.45)
        base_a = min(base_a, 0.35)
        base_ink = min(base_ink, 0.75)
        base_cov = min(base_cov, 0.75)
        base_text = min(base_text, 0.60)
        desc += "+med_far_cov"
    elif far_cov >= 0.18:
        base_h = min(base_h, 0.50)
        base_a = min(base_a, 0.40)
        base_ink = min(base_ink, 0.80)
        base_cov = min(base_cov, 0.80)
        base_text = min(base_text, 0.65)
        desc += "+low_far_cov"

    return AT(
        height_ratio=base_h,
        area_ratio=base_a,
        object_coverage=base_cov,
        ink_density=base_ink,
    )


def estimate_far_side_text_coverage(
    base_clip: Any,
    text_lines: List[Tuple[Any, float, str]],
    direction: str,
    *,
    text_trim_width_ratio: float = 0.5,
    font_min: float = 7.0,
    font_max: float = 16.0,
) -> float:
    """Estimate far-side paragraph coverage on the baseline clip (0.0–1.0)."""
    if fitz is None or base_clip.height <= 1 or base_clip.width <= 1:
        return 0.0

    far_is_top = direction == "above"
    width_min = max(0.35, text_trim_width_ratio * 0.7)
    far_lines: List[Any] = []
    for lb, fs, tx in text_lines:
        if not tx.strip():
            continue
        inter = lb & base_clip
        if inter.width <= 0 or inter.height <= 0:
            continue
        if (inter.width / max(1.0, base_clip.width)) < width_min:
            continue
        if not (font_min <= fs <= font_max):
            continue
        if far_is_top:
            in_far = lb.y0 < base_clip.y0 + 0.5 * base_clip.height
        else:
            in_far = lb.y1 > base_clip.y0 + 0.5 * base_clip.height
        if in_far:
            far_lines.append(lb)

    if not far_lines:
        return 0.0

    if far_is_top:
        region_h = max(1.0, (base_clip.y0 + 0.5 * base_clip.height) - base_clip.y0)
    else:
        region_h = max(1.0, base_clip.y1 - (base_clip.y0 + 0.5 * base_clip.height))
    return sum(lb.height for lb in far_lines) / region_h


def compute_clip_quality_metrics(
    page: Any,
    clip: Any,
    image_rects: List[Any],
    vector_rects: List[Any],
    *,
    dpi: int = 72,
) -> Tuple[float, float, float]:
    """Return (area, object_coverage, ink_density) for a clip."""
    from .direction import compute_object_ratio
    from .pixel_detect import estimate_ink_ratio

    area = max(1.0, clip.width * clip.height)
    cov = compute_object_ratio(clip, image_rects, vector_rects)
    ink = 0.0
    if page is not None:
        try:
            pix = page.get_pixmap(dpi=dpi, clip=clip, alpha=False)
            ink = estimate_ink_ratio(pix)
        except Exception:
            ink = 0.0
    return area, cov, ink


def evaluate_refinement_acceptance(
    final_clip: Any,
    base_clip: Any,
    thresholds: "AcceptanceThresholds",
    *,
    final_metrics: Tuple[float, float, float],
    base_metrics: Tuple[float, float, float],
    page_width: float,
    allow_low_ratio_keep: bool = False,
) -> Tuple[bool, bool, str]:
    """Return (accepted, hard_reject, fallback_reason)."""
    final_area, final_cov, final_ink = final_metrics
    base_area, base_cov, base_ink = base_metrics
    base_height = max(1.0, base_clip.height)

    height_ratio = final_clip.height / base_height
    area_ratio = final_area / max(1.0, base_area)

    accepted = True
    fallback_reason = ""
    hard_reject = False

    if height_ratio < thresholds.height_ratio:
        accepted = False
        fallback_reason = (
            f"height_ratio={height_ratio:.3f} < {thresholds.height_ratio:.3f}"
        )
    elif area_ratio < thresholds.area_ratio:
        accepted = False
        fallback_reason = (
            f"area_ratio={area_ratio:.3f} < {thresholds.area_ratio:.3f}"
        )

    if final_clip.width < page_width * 0.15:
        accepted = False
        hard_reject = True
        fallback_reason = (
            f"clip_too_narrow={final_clip.width:.0f}pt < 15% of page"
        )

    base_ink_mass = base_ink * base_area
    final_ink_mass = final_ink * final_area
    base_cov_mass = base_cov * base_area
    final_cov_mass = final_cov * final_area

    ok_ink_mass = (
        final_ink_mass >= thresholds.ink_density * base_ink_mass
        if base_ink_mass > 1e-9
        else True
    )
    ok_cov_mass = (
        final_cov_mass >= thresholds.object_coverage * base_cov_mass
        if base_cov_mass > 1e-9
        else True
    )

    significant_shrink = area_ratio < 0.70
    if significant_shrink:
        ok_ink_density = (final_ink >= 0.60 * base_ink) if base_ink > 1e-9 else True
        ok_cov_density = (final_cov >= 0.60 * base_cov) if base_cov > 1e-9 else True
    else:
        ok_ink_density = True
        ok_cov_density = True

    if not (ok_ink_mass and ok_ink_density):
        accepted = False
        if not fallback_reason:
            fallback_reason = "ink below mass/density threshold"
    if not (ok_cov_mass and ok_cov_density):
        accepted = False
        if not fallback_reason:
            fallback_reason = "object_coverage below mass/density threshold"

    if not accepted and not hard_reject and allow_low_ratio_keep:
        accepted = True

    return accepted, hard_reject, fallback_reason


def detect_text_pollution(
    clip: Any,
    text_lines: List[Tuple[Any, float, str]],
    *,
    max_wide_lines: int = 5,
    max_wide_ratio: float = 0.60,
    width_ratio: float = 0.70,
    min_text_len: int = 30,
    font_min: float = 7.0,
    font_max: float = 16.0,
) -> Tuple[bool, str]:
    """
    检测裁剪区域是否主要由正文段落构成。

    如果返回 True，上层应拒绝当前候选，而不是退回 baseline 后继续保存。
    baseline 通常仍以同一个错误 caption 为锚点，会把误截结果写入 index。
    """
    if fitz is None or clip.width <= 1 or clip.height <= 1:
        return False, ""

    text_in_clip = 0
    wide_text_in_clip = 0

    for (line_rect, font_size, text) in text_lines:
        txt = text.strip()
        if len(txt) < min_text_len:
            continue
        if not (font_min <= font_size <= font_max):
            continue

        inter = line_rect & clip
        if inter.width <= 0 or inter.height <= 0:
            continue

        text_in_clip += 1
        if (inter.width / max(1.0, clip.width)) > width_ratio:
            wide_text_in_clip += 1

    if wide_text_in_clip > max_wide_lines:
        pollution_ratio = wide_text_in_clip / max(1, text_in_clip)
        if pollution_ratio > max_wide_ratio:
            return True, f"text_pollution={wide_text_in_clip}/{text_in_clip} wide_lines"

    return False, ""

def looks_like_table_text(
    clip: Any,
    text_lines: List[Tuple[Any, float, str]],
    *,
    min_lines: int = 8,
    min_short_ratio: float = 0.65,
    max_wide_long_ratio: float = 0.25,
    short_text_len: int = 40,
    wide_ratio: float = 0.55,
) -> bool:
    """判断候选框是否以短单元格文本为主，而不是连续正文段落。"""
    if fitz is None or clip.width <= 1 or clip.height <= 1:
        return False

    lines_in_clip: List[Tuple[Any, str]] = []
    for line_rect, _font_size, text in text_lines:
        txt = text.strip()
        if not txt:
            continue
        inter = line_rect & clip
        if inter.width <= 0 or inter.height <= 0:
            continue
        lines_in_clip.append((inter, txt))

    if len(lines_in_clip) < 3:
        return False

    short_like = 0
    wide_long = 0
    for line_rect, text in lines_in_clip:
        if len(text) <= short_text_len or line_rect.width < clip.width * wide_ratio:
            short_like += 1
        if len(text) > short_text_len and line_rect.width >= clip.width * wide_ratio:
            wide_long += 1

    short_ratio = short_like / len(lines_in_clip)
    wide_long_ratio = wide_long / len(lines_in_clip)
    if len(lines_in_clip) < min_lines:
        compact_rows = sum(
            1
            for line_rect, text in lines_in_clip
            if (
                len(text) <= 100
                and len(text.split()) <= 18
                and line_rect.width <= clip.width * 0.92
                and not text.rstrip().endswith((".", "。", "!", "?", "；", ";"))
            )
        )
        return compact_rows >= 3
    return short_ratio >= min_short_ratio and wide_long_ratio <= max_wide_long_ratio
