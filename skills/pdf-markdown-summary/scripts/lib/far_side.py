#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Far-side body text evidence and trimming helpers."""

from __future__ import annotations

import re
from typing import Any, List, Optional, Tuple

try:
    import fitz
except ImportError:
    fitz = None  # type: ignore

from .text_trim import _looks_like_short_figure_label


def detect_far_side_text_evidence(
    clip: Any,
    text_lines: List[Tuple[Any, float, str]],
    direction: str,
    edge_zone: float = 40.0,
    min_width_ratio: float = 0.30,
    font_min: float = 7.0,
    font_max: float = 16.0,
) -> Tuple[bool, float]:
    """
    检测远端边缘附近是否有正文行证据。

    用于单调性约束：当远端附近有正文行时，Phase D 不应该扩展到这些行的区域。

    Args:
        clip: 当前裁剪区域
        text_lines: 文本行列表 [(rect, font_size, text), ...]
        direction: 方向 ('above' | 'below')
        edge_zone: 远端边缘检测范围（pt）
        min_width_ratio: 正文行最小宽度比例
        font_min/font_max: 正文字号范围

    Returns:
        (has_evidence, suggested_limit):
        - has_evidence: 是否检测到正文证据
        - suggested_limit: 建议的边界限制
    """
    if fitz is None or clip.height <= 1 or clip.width <= 1:
        return False, 0.0

    far_is_top = (direction == 'above')
    evidence_lines: List[Any] = []

    for (lb, fs, text) in text_lines:
        txt = text.strip()
        if not txt:
            continue

        inter = lb & clip
        if inter.width <= 0 or inter.height <= 0:
            continue

        width_ratio = inter.width / max(1.0, clip.width)
        if width_ratio < min_width_ratio:
            continue

        if not (font_min <= fs <= font_max):
            continue

        if len(txt) < 10:
            continue

        if _looks_like_short_figure_label(txt):
            continue

        if far_is_top:
            dist_to_far_edge = lb.y0 - clip.y0
            if dist_to_far_edge < edge_zone:
                evidence_lines.append(lb)
        else:
            dist_to_far_edge = clip.y1 - lb.y1
            if dist_to_far_edge < edge_zone:
                evidence_lines.append(lb)

    if evidence_lines:
        gap = 6.0
        if far_is_top:
            suggested_limit = max(lb.y1 for lb in evidence_lines) + gap
        else:
            suggested_limit = min(lb.y0 for lb in evidence_lines) - gap
        return True, suggested_limit

    return False, 0.0

def trim_far_side_text_post_autocrop(
    clip: Any,
    text_lines: List[Tuple[Any, float, str]],
    direction: str,
    *,
    typical_line_h: Optional[float] = None,
    scan_lines: int = 3,
    min_width_ratio: float = 0.30,
    min_text_len: int = 15,
    font_min: float = 7.0,
    font_max: float = 16.0,
    gap: float = 6.0,
) -> Tuple[Any, bool]:
    """
    Phase D 后的轻量去正文后处理。

    在 autocrop 完成后，扫描远端边缘附近的正文行，如果检测到明确的正文，
    向内推 y0/y1（只动 y，不动 x）。

    Args:
        clip: 当前裁剪区域
        text_lines: 文本行列表
        direction: 方向 ('above' | 'below')
        typical_line_h: 典型行高
        scan_lines: 扫描行数
        min_width_ratio: 正文最小宽度比例
        min_text_len: 正文最小长度
        font_min/font_max: 正文字号范围
        gap: 裁剪后的间隙

    Returns:
        (new_clip, was_trimmed): 新的裁剪区域和是否进行了裁剪
    """
    if fitz is None or clip.height <= 1 or clip.width <= 1:
        return clip, False

    if typical_line_h and typical_line_h > 0:
        scan_range = typical_line_h * scan_lines
    else:
        scan_range = 45.0

    far_is_top = (direction == 'above')
    text_to_trim: List[Any] = []

    for (lb, fs, text) in text_lines:
        txt = text.strip()
        if not txt:
            continue

        inter = lb & clip
        if inter.width <= 0 or inter.height <= 0:
            continue

        width_ratio = inter.width / max(1.0, clip.width)
        is_body_tail_fragment = (
            txt[:1].islower()
            and len(txt.split()) >= 2
            and txt.rstrip().endswith((".", "。", "!", "?", "；", ";"))
        )
        if width_ratio < min_width_ratio and not is_body_tail_fragment:
            continue
        if len(txt) < min_text_len:
            continue
        if not (font_min <= fs <= font_max):
            continue
        if _looks_like_short_figure_label(txt):
            continue

        if far_is_top:
            dist = lb.y0 - clip.y0
            if dist < scan_range:
                text_to_trim.append(lb)
        else:
            dist = clip.y1 - lb.y1
            if dist < scan_range:
                text_to_trim.append(lb)

    if not text_to_trim:
        return clip, False

    new_clip = fitz.Rect(clip)
    if far_is_top:
        max_y1 = max(lb.y1 for lb in text_to_trim)
        new_y0 = max_y1 + gap
        if new_y0 < clip.y0 + 0.5 * clip.height:
            new_clip = fitz.Rect(clip.x0, new_y0, clip.x1, clip.y1)
    else:
        min_y0 = min(lb.y0 for lb in text_to_trim)
        new_y1 = min_y0 - gap
        if new_y1 > clip.y0 + 0.5 * clip.height:
            new_clip = fitz.Rect(clip.x0, clip.y0, clip.x1, new_y1)

    was_trimmed = (new_clip != clip)
    return new_clip, was_trimmed

def trim_far_side_text_iterative(
    clip: Any,
    text_lines: List[Tuple[Any, float, str]],
    direction: str,
    *,
    typical_line_h: Optional[float] = None,
    max_passes: int = 8,
) -> Tuple[Any, bool]:
    """有限迭代清理远端连续正文，遇到非正文内容后停止。"""
    current = clip
    changed = False

    for _ in range(max_passes):
        next_clip, was_trimmed = trim_far_side_text_post_autocrop(
            current,
            text_lines,
            direction,
            typical_line_h=typical_line_h,
            scan_lines=3,
        )
        if not was_trimmed or next_clip == current:
            break
        current = next_clip
        changed = True

    return current, changed
