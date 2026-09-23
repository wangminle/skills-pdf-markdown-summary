#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Figure-specific final crop post-processing helpers."""

from __future__ import annotations

import re
from typing import Any, List, Optional, Tuple

try:
    import fitz
except ImportError:
    fitz = None  # type: ignore

from .text_trim import _looks_like_short_figure_label


def trim_far_side_noise_before_content(
    clip: Any,
    candidate_clip: Any,
    direction: str,
    image_rects: List[Any],
    vector_rects: List[Any],
    text_lines: Optional[List[Tuple[Any, float, str]]] = None,
    *,
    pad: float = 8.0,
    min_gap: float = 18.0,
) -> Any:
    """Trim isolated far-side noise before the first real figure content."""
    if fitz is None:
        return candidate_clip

    evidence: List[Any] = []
    header_separators: List[Any] = []
    running_margin_text: List[Any] = []

    def _add_rect(r: Any) -> None:
        inter = r & clip
        if inter.width > 0 and inter.height > 0:
            evidence.append(inter)

    for line_rect, _font_size, text in text_lines or []:
        txt = (text or "").strip()
        if not txt:
            continue
        relative_top = (line_rect.y0 - clip.y0) / max(1.0, clip.height)
        relative_bottom = (clip.y1 - line_rect.y1) / max(1.0, clip.height)
        if (
            direction == "above"
            and relative_top <= 0.18
            and (":" in txt or (len(txt) >= 8 and txt == txt.upper()))
        ):
            running_margin_text.append(line_rect)
        elif (
            direction == "below"
            and relative_bottom <= 0.18
            and len(txt) >= 8
            and txt == txt.upper()
        ):
            running_margin_text.append(line_rect)

    for r in image_rects:
        # Running headers may include a tiny raster logo immediately beside
        # their text. Keep ordinary figure images, including small subplots.
        if r.width < 20.0 and r.height < 20.0:
            adjacent_to_header = any(
                min(r.y1, line.y1) - max(r.y0, line.y0)
                >= 0.40 * min(r.height, line.height)
                and max(line.x0 - r.x1, r.x0 - line.x1, 0.0) <= 24.0
                for line in running_margin_text
            )
            if adjacent_to_header:
                continue
        _add_rect(r)

    for r in vector_rects:
        inter = r & clip
        # Page separator/header rules are often thin and very wide. They can be
        # zero-height PDF paths, so recognize them before rejecting empty rects.
        overlap_x = max(0.0, min(r.x1, clip.x1) - max(r.x0, clip.x0))
        if (
            overlap_x >= 0.70 * clip.width
            and r.height <= 4.0
            and clip.y0 <= r.y0 <= clip.y1
        ):
            header_separators.append(fitz.Rect(
                max(r.x0, clip.x0), r.y0, min(r.x1, clip.x1), r.y1
            ))
            continue
        if inter.width <= 0 or inter.height <= 0:
            continue
        # Tiny glyph paths (for example a publisher/logo mark in a running
        # header) should not establish the far edge of an entire figure.
        if inter.width < 14.0 and inter.height < 14.0:
            continue
        _add_rect(r)

    for line_rect, _font_size, text in text_lines or []:
        txt = (text or "").strip()
        if not txt:
            continue
        inter = line_rect & clip
        if inter.width <= 0 or inter.height <= 0:
            continue
        if line_rect in running_margin_text:
            continue
        # Keep figure-internal labels and compact annotations as content
        # evidence, but avoid using full-width body/caption text as a far edge.
        sentence_tail = (
            txt.rstrip().endswith((".", "。", "!", "?", "；", ";"))
            or (txt[:1].islower() and len(txt.split()) >= 2)
        )
        compact_annotation = (
            inter.width <= 0.45 * clip.width
            and len(txt) <= 80
            and not sentence_tail
            and not re.match(r"^\s*\d+(?:\.\d+)+\s+\S", txt)
        )
        if _looks_like_short_figure_label(txt) or compact_annotation:
            evidence.append(inter)

    # A running header may contain a vector logo made from many tiny paths. Once
    # a wide separator identifies that header band, ignore all evidence on its
    # page-edge side so the logo cannot keep the header in the final crop.
    if direction == "above":
        separators = [
            r for r in header_separators
            if r.y0 <= clip.y0 + 0.30 * clip.height
        ]
        if separators:
            boundary = max(r.y1 for r in separators) + 2.0
            evidence = [r for r in evidence if r.y1 > boundary]
    elif direction == "below":
        separators = [
            r for r in header_separators
            if r.y1 >= clip.y1 - 0.30 * clip.height
        ]
        if separators:
            boundary = min(r.y0 for r in separators) - 2.0
            evidence = [r for r in evidence if r.y0 < boundary]

    if not evidence:
        return candidate_clip

    if direction == "above":
        content_edge = min(r.y0 for r in evidence)
        if content_edge - candidate_clip.y0 < min_gap:
            return candidate_clip
        new_y0 = max(clip.y0, content_edge - pad)
        if new_y0 >= candidate_clip.y1:
            return candidate_clip
        return fitz.Rect(candidate_clip.x0, new_y0, candidate_clip.x1, candidate_clip.y1)

    if direction == "below":
        content_edge = max(r.y1 for r in evidence)
        if candidate_clip.y1 - content_edge < min_gap:
            return candidate_clip
        new_y1 = min(clip.y1, content_edge + pad)
        if new_y1 <= candidate_clip.y0:
            return candidate_clip
        return fitz.Rect(candidate_clip.x0, candidate_clip.y0, candidate_clip.x1, new_y1)

    return candidate_clip

def expand_clip_to_nearby_figure_title(
    original_clip: Any,
    limited_clip: Any,
    text_lines: List[Tuple[Any, float, str]],
    direction: str,
    *,
    pad: float = 4.0,
    max_gap: float = 12.0,
    max_title_font_size: float = 11.0,
) -> Any:
    """恢复紧贴图主体的图内标题，避免被 layout 标题 blocker 排除。"""
    if fitz is None or original_clip.width <= 1 or original_clip.height <= 1:
        return limited_clip
    if limited_clip.width <= 1 or limited_clip.height <= 1:
        return limited_clip

    def _is_page_header(line_rect: Any, text: str) -> bool:
        width_ratio = line_rect.width / max(1.0, original_clip.width)
        return width_ratio >= 0.70 and line_rect.y0 <= original_clip.y0 + 80.0 and ":" in text

    def _is_numbered_section(text: str) -> bool:
        return bool(re.match(r"^\s*\d+(?:\.\d+)*\.?\s+\S", text))

    def _is_section_number_only(text: str) -> bool:
        return bool(re.match(r"^\s*(?:\d+(?:\.\d+)+\.?|\d+\.)\s*$", text))

    def _is_body_tail_fragment(text: str) -> bool:
        txt = text.strip()
        return (
            len(txt.split()) >= 2
            and txt.rstrip().endswith((".", "。", "!", "?", "；", ";"))
        )

    section_number_lines = [
        line_rect
        for line_rect, _font_size, text in text_lines
        if _is_section_number_only((text or "").strip())
    ]

    def _has_adjacent_section_number(line_rect: Any) -> bool:
        for number_rect in section_number_lines:
            vertical_overlap = min(line_rect.y1, number_rect.y1) - max(line_rect.y0, number_rect.y0)
            if vertical_overlap <= 0:
                continue
            overlap_ratio = vertical_overlap / max(1.0, min(line_rect.height, number_rect.height))
            horizontal_gap = line_rect.x0 - number_rect.x1
            if overlap_ratio >= 0.60 and 0 <= horizontal_gap <= 24.0:
                return True
        return False

    def _is_wrapped_body_line(rect: Any, size: float) -> bool:
        # A short last line may have no extracted punctuation. Link it to the
        # preceding body-width line instead of treating it as a figure title.
        for other, other_size, other_text in text_lines:
            if len((other_text or "").strip()) < 60:
                continue
            gap = rect.y0 - other.y1
            if (0 <= gap <= 6 and abs(size - other_size) <= 0.5
                    and abs(rect.x0 - other.x0) <= 16
                    and other.width >= original_clip.width * 0.65):
                return True
        return False

    current = fitz.Rect(limited_clip)
    while True:
        candidates: List[Any] = []
        for line_rect, font_size, text in text_lines:
            txt = (text or "").strip()
            if not txt:
                continue
            if font_size > max_title_font_size:
                continue
            if _is_body_tail_fragment(txt) or len(txt) > 100 or _is_wrapped_body_line(line_rect, font_size):
                continue
            if _is_numbered_section(txt) or _is_section_number_only(txt) or _is_page_header(line_rect, txt):
                continue
            if _has_adjacent_section_number(line_rect):
                continue
            overlap = min(line_rect.x1, current.x1) - max(line_rect.x0, current.x0)
            if overlap < 0.2 * min(line_rect.width, current.width):
                continue
            inter = line_rect & original_clip
            if inter.width <= 0 or inter.height <= 0:
                continue

            if direction == "above":
                gap = current.y0 - line_rect.y1
                if line_rect.y0 < current.y0 and -line_rect.height <= gap <= max_gap and line_rect.y1 >= original_clip.y0:
                    candidates.append(line_rect)
            elif direction == "below":
                gap = line_rect.y0 - current.y1
                if line_rect.y1 > current.y1 and -line_rect.height <= gap <= max_gap and line_rect.y0 <= original_clip.y1:
                    candidates.append(line_rect)

        if not candidates:
            break

        if direction == "above":
            new_y0 = max(original_clip.y0, min(r.y0 for r in candidates) - pad)
            if new_y0 >= current.y0 - 0.1:
                break
            current = fitz.Rect(current.x0, new_y0, current.x1, current.y1)
        elif direction == "below":
            new_y1 = min(original_clip.y1, max(r.y1 for r in candidates) + pad)
            if new_y1 <= current.y1 + 0.1:
                break
            current = fitz.Rect(current.x0, current.y0, current.x1, new_y1)
        else:
            break

    return current

def expand_clip_to_nearby_figure_objects(
    limited_clip: Any,
    caption_rect: Any,
    direction: str,
    image_rects: List[Any],
    vector_rects: List[Any],
    page_rect: Any,
    neighbor_caption_rects: Optional[List[Any]] = None,
    *,
    gap: float = 6.0,
    pad: float = 6.0,
    max_gap: float = 18.0,
    max_expand: float = 140.0,
) -> Any:
    """Recover connected figure objects clipped off at the far side of the baseline.

    Some architecture diagrams have small modules slightly beyond the fixed baseline
    height. They are real figure objects, not text blockers, and should be pulled
    back only when they touch the current far edge or are very close to it.
    """
    if fitz is None or limited_clip.width <= 1 or limited_clip.height <= 1:
        return limited_clip
    if page_rect is None:
        return limited_clip

    neighbor_caption_rects = neighbor_caption_rects or []
    page_width = max(1.0, page_rect.width)

    def _is_object_candidate(rect: Any) -> bool:
        if rect.width <= 0 or rect.height <= 0:
            return False
        if rect.width < 20.0 or rect.height < 14.0:
            return False
        if rect.width * rect.height < 120.0:
            return False
        if rect.width >= page_width * 0.65 and rect.height <= 2.0:
            return False
        if rect.width * rect.height < 24.0 and min(rect.width, rect.height) < 4.0:
            return False
        horizontal_overlap = min(rect.x1, limited_clip.x1) - max(rect.x0, limited_clip.x0)
        if horizontal_overlap <= 0:
            return False
        return True

    objects = [
        fitz.Rect(rect)
        for rect in list(image_rects) + list(vector_rects)
        if _is_object_candidate(rect)
    ]
    if not objects:
        return limited_clip

    current = fitz.Rect(limited_clip)

    if direction == "above":
        boundary = page_rect.y0
        previous_caps = [
            rect for rect in neighbor_caption_rects
            if rect.y1 <= caption_rect.y0 and rect.y1 < limited_clip.y0 - 0.5
        ]
        if previous_caps:
            boundary = max(boundary, max(rect.y1 for rect in previous_caps) + gap)
        boundary = max(boundary, limited_clip.y0 - max_expand)

        while True:
            edge = current.y0
            candidates = [
                rect for rect in objects
                if rect.y0 < edge
                and rect.y1 >= edge - max_gap
                and rect.y1 <= caption_rect.y0 - gap
                and rect.y1 >= boundary
            ]
            if not candidates:
                break
            new_y0 = max(boundary, min(rect.y0 for rect in candidates) - pad)
            if new_y0 >= current.y0 - 0.5:
                break
            current = fitz.Rect(current.x0, new_y0, current.x1, current.y1)

    elif direction == "below":
        boundary = page_rect.y1
        next_caps = [
            rect for rect in neighbor_caption_rects
            if rect.y0 >= caption_rect.y1 and rect.y0 > limited_clip.y1 + 0.5
        ]
        if next_caps:
            boundary = min(boundary, min(rect.y0 for rect in next_caps) - gap)
        boundary = min(boundary, limited_clip.y1 + max_expand)

        while True:
            edge = current.y1
            candidates = [
                rect for rect in objects
                if rect.y1 > edge
                and rect.y0 <= edge + max_gap
                and rect.y0 >= caption_rect.y1 + gap
                and rect.y0 <= boundary
            ]
            if not candidates:
                break
            new_y1 = min(boundary, max(rect.y1 for rect in candidates) + pad)
            if new_y1 <= current.y1 + 0.5:
                break
            current = fitz.Rect(current.x0, current.y0, current.x1, new_y1)

    return current

def pad_figure_clip_near_caption(
    clip: Any,
    caption_rect: Any,
    direction: str,
    *,
    pad: float = 4.0,
    min_caption_gap: float = 2.0,
) -> Any:
    """Add a tiny final-side padding near the caption without touching the caption."""
    if fitz is None or clip.width <= 1 or clip.height <= 1:
        return clip
    if direction == "above":
        max_y1 = caption_rect.y0 - min_caption_gap
        new_y1 = min(max_y1, clip.y1 + pad)
        if new_y1 > clip.y1 + 0.1:
            return fitz.Rect(clip.x0, clip.y0, clip.x1, new_y1)
    elif direction == "below":
        min_y0 = caption_rect.y1 + min_caption_gap
        new_y0 = max(min_y0, clip.y0 - pad)
        if new_y0 < clip.y0 - 0.1:
            return fitz.Rect(clip.x0, new_y0, clip.x1, clip.y1)
    return clip
