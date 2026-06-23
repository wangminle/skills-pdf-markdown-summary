#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Table-specific crop refinement helpers."""

from __future__ import annotations

import re
from typing import Any, List, Optional, Tuple

try:
    import fitz
except ImportError:
    fitz = None  # type: ignore

from .acceptance import looks_like_table_text


def expand_clip_to_rendered_horizontal_rule(
    clip: Any,
    page: Any,
    caption_rect: Any,
    direction: str,
    *,
    scale: float = 4.0,
    search_gap: float = 12.0,
    pad: float = 1.0,
    dark_threshold: int = 80,
    min_dark_fraction: float = 0.35,
) -> Any:
    """Expand the near caption edge to include a rendered horizontal table rule."""
    if fitz is None or clip.width <= 1 or clip.height <= 1:
        return clip

    page_rect = getattr(page, "rect", None)
    if page_rect is None:
        return clip

    if direction == "below":
        search_y0 = max(page_rect.y0, caption_rect.y1 + 0.25)
        search_y1 = min(page_rect.y1, clip.y0 + 1.5, caption_rect.y1 + search_gap)
    elif direction == "above":
        search_y0 = max(page_rect.y0, clip.y1 - 1.5, caption_rect.y0 - search_gap)
        search_y1 = min(page_rect.y1, caption_rect.y0 - 0.25)
    else:
        return clip

    if search_y1 <= search_y0:
        return clip

    render_clip = fitz.Rect(clip.x0, search_y0, clip.x1, search_y1) & page_rect
    if render_clip.width <= 1 or render_clip.height <= 0.5:
        return clip

    try:
        matrix = fitz.Matrix(scale, scale)
        raw_page = getattr(page, "raw", page)
        pix = raw_page.get_pixmap(matrix=matrix, clip=render_clip, alpha=False)
    except Exception:
        return clip

    if pix.width <= 0 or pix.height <= 0:
        return clip

    samples = memoryview(pix.samples)
    n = pix.n
    stride = pix.stride
    qualifying_rows: List[int] = []
    for y in range(pix.height):
        row = samples[y * stride:(y + 1) * stride]
        dark = 0
        for x in range(pix.width):
            off = x * n
            r = row[off]
            g = row[off + 1] if n > 1 else r
            b = row[off + 2] if n > 2 else r
            if (r + g + b) / 3.0 <= dark_threshold:
                dark += 1
        if dark / max(1.0, float(pix.width)) >= min_dark_fraction:
            qualifying_rows.append(y)

    if not qualifying_rows:
        return clip

    if direction == "below":
        rule_y = render_clip.y0 + min(qualifying_rows) / scale
        new_y0 = max(page_rect.y0, min(clip.y0, rule_y - pad))
        if new_y0 < clip.y0 - 0.25 and new_y0 > caption_rect.y1:
            return fitz.Rect(clip.x0, new_y0, clip.x1, clip.y1)
    else:
        rule_y = render_clip.y0 + max(qualifying_rows) / scale
        new_y1 = min(page_rect.y1, max(clip.y1, rule_y + pad))
        if new_y1 > clip.y1 + 0.25 and new_y1 < caption_rect.y0:
            return fitz.Rect(clip.x0, clip.y0, clip.x1, new_y1)

    return clip

def refine_clip_to_table_band(
    clip: Any,
    caption_rect: Any,
    text_lines: List[Tuple[Any, float, str]],
    direction: str,
    *,
    typical_line_h: Optional[float] = None,
    min_cells_per_row: int = 2,
    pad: float = 6.0,
) -> Tuple[Any, bool]:
    """从图注一侧识别连续多单元格行带，并收紧表格远端边界。"""
    if fitz is None or clip.width <= 1 or clip.height <= 1:
        return clip, False

    row_tolerance = max(2.0, (typical_line_h or 10.0) * 0.45)
    candidates: List[Tuple[Any, str]] = []
    for line_rect, _font_size, text in text_lines:
        txt = text.strip()
        inter = line_rect & clip
        if not txt or inter.width <= 0 or inter.height <= 0:
            continue
        candidates.append((inter, txt))

    if not candidates:
        return clip, False

    candidates.sort(key=lambda item: (item[0].y0, item[0].x0))
    rows: List[List[Tuple[Any, str]]] = []
    row_centers: List[float] = []
    for item in candidates:
        center = (item[0].y0 + item[0].y1) / 2.0
        if rows and abs(center - row_centers[-1]) <= row_tolerance:
            rows[-1].append(item)
            row_centers[-1] = sum((r.y0 + r.y1) / 2.0 for r, _ in rows[-1]) / len(rows[-1])
        else:
            rows.append([item])
            row_centers.append(center)

    def classify_table_row(row: List[Tuple[Any, str]]) -> str:
        distinct_cells = []
        for rect, text in sorted(row, key=lambda item: item[0].x0):
            if distinct_cells and rect.x0 <= distinct_cells[-1][0].x1 + 2.0:
                previous_rect, previous_text = distinct_cells[-1]
                distinct_cells[-1] = (previous_rect | rect, previous_text + " " + text)
            else:
                distinct_cells.append((rect, text))
        if len(distinct_cells) > min_cells_per_row:
            return "strong"
        row_rect = distinct_cells[0][0]
        row_text = distinct_cells[0][1]
        for rect, _text in distinct_cells[1:]:
            row_rect = row_rect | rect
            row_text += " " + _text
        if len(distinct_cells) == min_cells_per_row:
            if row_rect.width >= clip.width * 0.55:
                return "strong"
            if row_rect.width >= clip.width * 0.20 and len(row_text) <= 160:
                return "weak"
            return "none"
        if len(distinct_cells) == 1:
            word_count = len(row_text.split())
            sentence_like = (
                len(row_text) > 100
                or word_count > 18
                or (len(row_text) > 70 and row_text.rstrip().endswith((".", "。", "!", "?", "；", ";")))
            )
            if (
                not sentence_like
                and clip.width * 0.12 <= row_rect.width <= clip.width * 0.92
            ):
                return "weak"
        return "none"

    row_kinds = [classify_table_row(row) for row in rows]
    use_weak_rows = not any(kind == "strong" for kind in row_kinds)
    if direction == "above":
        ordered_indices = list(range(len(rows) - 1, -1, -1))
    else:
        ordered_indices = list(range(len(rows)))

    def summarize_row(idx: int) -> Tuple[Any, str]:
        row_rect = None
        row_text = ""
        for rect, text in sorted(rows[idx], key=lambda item: item[0].x0):
            row_rect = fitz.Rect(rect) if row_rect is None else row_rect | rect
            row_text += " " + text
        return row_rect, row_text.strip()

    row_summaries = [summarize_row(idx) for idx in range(len(rows))]
    max_bridge_gap = max(80.0, (typical_line_h or 10.0) * 7.0)

    def has_future_table_evidence(position: int) -> bool:
        current_idx = ordered_indices[position]
        current_rect, _current_text = row_summaries[current_idx]
        if current_rect is None:
            return False
        for future_position in range(position + 1, min(len(ordered_indices), position + 9)):
            future_idx = ordered_indices[future_position]
            future_rect, future_text = row_summaries[future_idx]
            if future_rect is None:
                continue
            if direction == "above":
                distance = current_rect.y0 - future_rect.y1
            else:
                distance = future_rect.y0 - current_rect.y1
            if distance > max_bridge_gap:
                break
            if (
                row_kinds[future_idx] == "strong"
                or (
                    row_kinds[future_idx] == "weak"
                    and bool(re.search(r"\d", future_text))
                    and future_rect.width <= clip.width * 0.70
                )
            ):
                return True
        return False

    selected: List[int] = []
    started = False
    sparse_rows = 0
    strong_rows = 0
    weak_rows = 0
    max_row_gap = max(18.0, (typical_line_h or 10.0) * 2.25)
    for position, idx in enumerate(ordered_indices):
        row_rect, row_text = row_summaries[idx]
        if started and selected:
            previous_idx = selected[-1]
            if direction == "above":
                gap = min(r.y0 for r, _ in rows[previous_idx]) - max(r.y1 for r, _ in rows[idx])
            else:
                gap = min(r.y0 for r, _ in rows[idx]) - max(r.y1 for r, _ in rows[previous_idx])
            if gap > max_row_gap:
                word_count = len(row_text.split())
                numeric_count = len(re.findall(r"\d+(?:\.\d+)?%?", row_text))
                sentence_like = (
                    len(row_text) > 100
                    or word_count > 18
                    or (word_count >= 12 and numeric_count < 2)
                )
                bridges_strong_group = (
                    gap <= max_bridge_gap
                    and row_kinds[previous_idx] == "strong"
                    and row_kinds[idx] == "strong"
                    and not sentence_like
                )
                if not bridges_strong_group:
                    break

        is_numbered_section = bool(re.match(r"^\s*\d+(?:\.\d+)+\s+\S", row_text))
        has_numeric_evidence = bool(re.search(r"\d", row_text))
        weak_has_table_evidence = (
            row_kinds[idx] == "weak"
            and not is_numbered_section
            and (
                use_weak_rows
                or (
                    has_numeric_evidence
                    and row_rect is not None
                    and row_rect.width <= clip.width * 0.70
                )
                or has_future_table_evidence(position)
            )
        )
        if row_kinds[idx] == "strong" or weak_has_table_evidence:
            selected.append(idx)
            started = True
            sparse_rows = 0
            if row_kinds[idx] == "strong":
                strong_rows += 1
            else:
                weak_rows += 1
            continue
        if started:
            is_sparse_label = (
                row_rect is not None
                and row_rect.width < clip.width * 0.35
                and len(row_text) <= 30
                and not is_numbered_section
                and sparse_rows < 2
                and has_future_table_evidence(position)
            )
            if is_sparse_label:
                selected.append(idx)
                sparse_rows += 1
                continue
            break

    if len(selected) < 2 or (strong_rows == 0 and weak_rows < 3):
        return clip, False

    table_rect = None
    for idx in selected:
        for rect, _text in rows[idx]:
            table_rect = fitz.Rect(rect) if table_rect is None else table_rect | rect

    if table_rect is None:
        return clip, False

    new_clip = fitz.Rect(clip)
    if direction == "above":
        new_y0 = max(clip.y0, table_rect.y0 - pad)
        if new_y0 >= caption_rect.y0 or new_y0 <= clip.y0 + 0.5:
            return clip, False
        new_clip = fitz.Rect(clip.x0, new_y0, clip.x1, clip.y1)
    elif direction == "below":
        new_y1 = min(clip.y1, table_rect.y1 + pad)
        if new_y1 <= caption_rect.y1 or new_y1 >= clip.y1 - 0.5:
            return clip, False
        new_clip = fitz.Rect(clip.x0, clip.y0, clip.x1, new_y1)

    return new_clip, new_clip != clip

def restore_table_clip_width(
    clip: Any,
    base_clip: Any,
    *,
    table_band_changed: bool,
    min_width_ratio: float = 0.40,
) -> Any:
    """可靠表格行带成立时，恢复被对象裁切误缩成局部列的 X 范围。"""
    if fitz is None or not table_band_changed or base_clip.width <= 1:
        return clip
    if clip.width >= base_clip.width * min_width_ratio:
        return clip
    return fitz.Rect(base_clip.x0, clip.y0, base_clip.x1, clip.y1)

def restore_table_tail_after_layout_trim(
    original_clip: Any,
    adjusted_clip: Any,
    text_lines: List[Tuple[Any, float, str]],
    direction: str,
    *,
    min_tail_height: float = 12.0,
) -> Any:
    """当 layout 远端裁剪误切掉表格尾部行时，恢复表格尾部边界。"""
    if fitz is None or original_clip.width <= 1 or original_clip.height <= 1:
        return adjusted_clip
    if adjusted_clip.width <= 1 or adjusted_clip.height <= 1:
        return adjusted_clip

    if direction == "below":
        if adjusted_clip.y1 >= original_clip.y1 - min_tail_height:
            return adjusted_clip
        tail_clip = fitz.Rect(
            adjusted_clip.x0,
            adjusted_clip.y1,
            adjusted_clip.x1,
            original_clip.y1,
        )
        if looks_like_table_text(tail_clip, text_lines):
            return fitz.Rect(
                adjusted_clip.x0,
                adjusted_clip.y0,
                adjusted_clip.x1,
                original_clip.y1,
            )
    elif direction == "above":
        if adjusted_clip.y0 <= original_clip.y0 + min_tail_height:
            return adjusted_clip
        tail_clip = fitz.Rect(
            adjusted_clip.x0,
            original_clip.y0,
            adjusted_clip.x1,
            adjusted_clip.y0,
        )
        if looks_like_table_text(tail_clip, text_lines):
            return fitz.Rect(
                adjusted_clip.x0,
                original_clip.y0,
                adjusted_clip.x1,
                adjusted_clip.y1,
            )

    return adjusted_clip

def expand_clip_to_nearby_table_header(
    original_clip: Any,
    limited_clip: Any,
    text_lines: List[Tuple[Any, float, str]],
    caption_rect: Any,
    direction: str,
    *,
    pad: float = 4.0,
    max_gap: float = 8.0,
    max_header_height: float = 60.0,
    table_probe_height: float = 180.0,
) -> Any:
    """恢复被 layout blocker 裁掉的多行表头。"""
    if fitz is None or not text_lines:
        return limited_clip
    if original_clip.width <= 1 or original_clip.height <= 1:
        return limited_clip
    if limited_clip.width <= 1 or limited_clip.height <= 1:
        return limited_clip

    if direction == "above":
        if limited_clip.y0 <= original_clip.y0 + 0.5:
            return limited_clip
        probe = fitz.Rect(
            limited_clip.x0,
            limited_clip.y0,
            limited_clip.x1,
            min(limited_clip.y1, limited_clip.y0 + table_probe_height),
        )
        if not looks_like_table_text(probe, text_lines, min_lines=3):
            return limited_clip
        band_y0 = max(original_clip.y0, limited_clip.y0 - max_header_height)
        band_y1 = limited_clip.y0 + max_gap
    elif direction == "below":
        if limited_clip.y1 >= original_clip.y1 - 0.5:
            return limited_clip
        probe = fitz.Rect(
            limited_clip.x0,
            max(limited_clip.y0, limited_clip.y1 - table_probe_height),
            limited_clip.x1,
            limited_clip.y1,
        )
        if not looks_like_table_text(probe, text_lines, min_lines=3):
            return limited_clip
        band_y0 = limited_clip.y1 - max_gap
        band_y1 = min(original_clip.y1, limited_clip.y1 + max_header_height)
    else:
        return limited_clip

    band = fitz.Rect(original_clip.x0, band_y0, original_clip.x1, band_y1)
    candidates: List[Any] = []
    for line_rect, _font_size, text in text_lines:
        txt = (text or "").strip()
        if not txt:
            continue
        if re.match(r"^\s*(?:Figure|Table)\s+\S+", txt, re.I):
            continue
        if (line_rect & caption_rect).width > 0 and (line_rect & caption_rect).height > 0:
            continue

        inter = line_rect & band
        if inter.width <= 0 or inter.height <= 0:
            continue
        if inter.width < max(24.0, original_clip.width * 0.04):
            continue
        if len(txt) > 140:
            continue
        if len(txt) > 80 and txt.rstrip().endswith((".", "。", "!", "?", "；", ";")):
            continue

        if direction == "above" and line_rect.y0 < limited_clip.y0:
            candidates.append(line_rect & original_clip)
        elif direction == "below" and line_rect.y1 > limited_clip.y1:
            candidates.append(line_rect & original_clip)

    if len(candidates) < 2:
        return limited_clip

    if direction == "above":
        nearest_gap = limited_clip.y0 - max(r.y1 for r in candidates)
        if nearest_gap > max_gap:
            return limited_clip
        new_y0 = max(original_clip.y0, min(r.y0 for r in candidates) - pad)
        if new_y0 < limited_clip.y0 and limited_clip.y1 - new_y0 >= 40.0:
            return fitz.Rect(limited_clip.x0, new_y0, limited_clip.x1, limited_clip.y1)
    else:
        nearest_gap = min(r.y0 for r in candidates) - limited_clip.y1
        if nearest_gap > max_gap:
            return limited_clip
        new_y1 = min(original_clip.y1, max(r.y1 for r in candidates) + pad)
        if new_y1 > limited_clip.y1 and new_y1 - limited_clip.y0 >= 40.0:
            return fitz.Rect(limited_clip.x0, limited_clip.y0, limited_clip.x1, new_y1)

    return limited_clip

def expand_table_clip_to_text_bounds(
    clip: Any,
    reference_clip: Any,
    caption_rect: Any,
    text_lines: List[Tuple[Any, float, str]],
    direction: str,
    layout_text_blocks: Optional[List[Any]] = None,
    *,
    pad: float = 2.5,
    max_expand: float = 8.0,
    far_max_expand: float = 160.0,
    connected_row_gap: float = 24.0,
    min_caption_gap: float = 1.0,
) -> Any:
    """给 Table final 增加少量文本 bbox 安全边距，避免 autocrop 贴字。"""
    if fitz is None or clip.width <= 1 or clip.height <= 1:
        return clip
    if reference_clip.width <= 1 or reference_clip.height <= 1:
        return clip
    table_like_before_trim = looks_like_table_text(clip, text_lines)

    def _is_caption_like(txt: str) -> bool:
        return bool(re.match(r"^\s*(?:Table|Figure|Tab\.?|Fig\.?)\s+\S+", txt, re.I))

    def _group_rows(search_rect: Any) -> List[Tuple[Any, int, str]]:
        rows: List[List[Tuple[Any, str]]] = []
        centers: List[float] = []
        for line_rect, _font_size, text in sorted(
            text_lines,
            key=lambda item: (item[0].y0, item[0].x0),
        ):
            txt = (text or "").strip()
            if not txt or _is_caption_like(txt):
                continue
            if (line_rect & caption_rect).width > 0 and (line_rect & caption_rect).height > 0:
                continue
            inter = line_rect & search_rect
            if inter.width <= 0 or inter.height <= 0:
                continue
            if inter.width < max(10.0, clip.width * 0.02):
                continue
            center = (line_rect.y0 + line_rect.y1) / 2.0
            if rows and abs(center - centers[-1]) <= 3.5:
                rows[-1].append((line_rect & search_rect, txt))
                centers[-1] = sum((r.y0 + r.y1) / 2.0 for r, _txt in rows[-1]) / len(rows[-1])
            else:
                rows.append([(line_rect & search_rect, txt)])
                centers.append(center)

        row_rects: List[Tuple[Any, int, str]] = []
        for row in rows:
            row_rect = fitz.Rect(row[0][0])
            parts: List[str] = []
            for rect, txt in row:
                row_rect |= rect
                parts.append(txt)
            row_rects.append((row_rect, len(row), " ".join(parts).strip()))
        return row_rects

    def _looks_like_table_row(row_rect: Any, part_count: int, text: str) -> bool:
        words = text.split()
        numeric_count = len(re.findall(r"\d+(?:\.\d+)?%?|[-–]|/", text))
        if part_count >= 2:
            return True
        if numeric_count >= 2 and row_rect.width <= clip.width * 0.90:
            return True
        if len(text) <= 45:
            return True
        if row_rect.width <= clip.width * 0.55 and len(words) <= 14:
            return True
        return False

    def _looks_like_structured_table_row(row_rect: Any, part_count: int, text: str) -> bool:
        return part_count >= 2

    def _looks_like_body_row(row_rect: Any, part_count: int, text: str) -> bool:
        if part_count >= 2:
            return False
        words = text.split()
        if len(words) < 8:
            return False
        if row_rect.width < clip.width * 0.60:
            return False
        return True

    def _looks_like_body_line(line_rect: Any, text: str) -> bool:
        words = text.split()
        if len(words) < 8:
            return False
        if line_rect.width < clip.width * 0.60:
            return False
        return True

    def _numeric_token_count(text: str) -> int:
        return len(re.findall(r"\d+(?:\.\d+)?%?|[-–]|/", text))

    def _block_text(block: Any) -> str:
        units = getattr(block, "units", None) or []
        if units:
            return " ".join((getattr(unit, "text", "") or "").strip() for unit in units).strip()
        return ""

    def _expand_far_side_to_layout_row(current: Any) -> Any:
        if not layout_text_blocks:
            return current
        blocks: List[Tuple[Any, str, str]] = []
        for block in layout_text_blocks:
            rect = getattr(block, "bbox", None)
            block_type = getattr(block, "block_type", "") or ""
            if rect is None:
                continue
            text = _block_text(block)
            if not text:
                continue
            blocks.append((rect, block_type, text))
        if not blocks:
            return current

        def _same_row_peer_rects(title_rect: Any) -> List[Any]:
            peers: List[Any] = []
            for rect, block_type, text in blocks:
                if rect is title_rect:
                    continue
                overlap = min(rect.y1, title_rect.y1) - max(rect.y0, title_rect.y0)
                if overlap <= 0.45 * min(rect.height, title_rect.height):
                    continue
                if rect.x1 > title_rect.x0 + 1 and rect.x0 < title_rect.x1 - 1:
                    continue
                if re.match(r"^\s*\d+(?:\.\d+)*$", text):
                    continue
                if rect.width >= 0.55 * current.width and len(text.split()) >= 8:
                    continue
                if block_type in ("paragraph_group", "list_group") or block_type.startswith("title_"):
                    peers.append(rect)
            return peers

        candidates: List[Any] = []
        for rect, block_type, text in blocks:
            if not block_type.startswith("title_"):
                continue
            if direction == "below":
                gap_to_edge = rect.y0 - current.y1
                if not (0 <= gap_to_edge <= connected_row_gap):
                    continue
            elif direction == "above":
                gap_to_edge = current.y0 - rect.y1
                if not (0 <= gap_to_edge <= connected_row_gap):
                    continue
            else:
                continue
            peers = _same_row_peer_rects(rect)
            if not peers:
                continue
            row_rect = fitz.Rect(rect)
            for peer in peers:
                row_rect |= peer
            candidates.append(row_rect)

        if not candidates:
            return current
        if direction == "below":
            new_y1 = min(reference_clip.y1, max(row.y1 for row in candidates) + pad)
            if new_y1 > current.y1 + 0.5 and new_y1 - current.y0 >= 40.0:
                return fitz.Rect(current.x0, current.y0, current.x1, new_y1)
        elif direction == "above":
            new_y0 = max(reference_clip.y0, min(row.y0 for row in candidates) - pad)
            if new_y0 < current.y0 - 0.5 and current.y1 - new_y0 >= 40.0:
                return fitz.Rect(current.x0, new_y0, current.x1, current.y1)
        return current

    def _trim_far_side_body_prefix(current: Any) -> Any:
        rows = _group_rows(current)
        if not rows:
            return current

        if direction == "above":
            ordered = sorted(rows, key=lambda item: item[0].y0)
            body_seen = False
            for row, part_count, text in ordered:
                if row.y0 < current.y0 - 0.5:
                    continue
                if _looks_like_body_row(row, part_count, text):
                    body_seen = True
                    continue
                if body_seen and _looks_like_structured_table_row(row, part_count, text):
                    new_y0 = max(current.y0, row.y0 - pad)
                    if new_y0 > current.y0 + 0.5 and current.y1 - new_y0 >= 40.0:
                        return fitz.Rect(current.x0, new_y0, current.x1, current.y1)
                    return current
                if not body_seen and _looks_like_table_row(row, part_count, text):
                    return current
        elif direction == "below":
            ordered = sorted(rows, key=lambda item: item[0].y0, reverse=True)
            body_seen = False
            for row, part_count, text in ordered:
                if row.y1 > current.y1 + 0.5:
                    continue
                if _looks_like_body_row(row, part_count, text):
                    body_seen = True
                    continue
                if body_seen and _looks_like_structured_table_row(row, part_count, text):
                    new_y1 = min(current.y1, row.y1 + pad)
                    if new_y1 < current.y1 - 0.5 and new_y1 - current.y0 >= 40.0:
                        return fitz.Rect(current.x0, current.y0, current.x1, new_y1)
                    return current
                if not body_seen and _looks_like_table_row(row, part_count, text):
                    return current
        return current

    def _trim_far_side_to_first_structured_row(current: Any) -> Any:
        """裁掉 Table final 远端被带入的正文尾句或大段空白。

        只在能看到强结构表格行时触发；单个短文本行不作为安全起点，避免把
        普通正文尾句误当表格。
        """
        rows = _group_rows(current)
        if not rows:
            return current

        def _looks_like_noise_prefix_row(row_rect: Any, part_count: int, text: str) -> bool:
            if part_count >= 2:
                return False
            stripped = text.strip()
            if not stripped:
                return True
            if _looks_like_body_row(row_rect, part_count, stripped):
                return True
            if stripped.endswith((".", "。", "!", "?", "；", ";")):
                return True
            return False

        if direction == "above":
            ordered = sorted(rows, key=lambda item: item[0].y0)
            for row, part_count, text in ordered:
                if row.y0 < current.y0 - 0.5:
                    continue
                strong_table_start = part_count >= 2
                if not strong_table_start:
                    continue
                leading_rows = [
                    prior
                    for prior in ordered
                    if prior[0].y1 <= row.y0 + 0.5 and prior[0].y0 >= current.y0 - 0.5
                ]
                has_leading_noise = bool(leading_rows)
                large_gap = row.y0 - current.y0 > max(18.0, 1.5 * typical_line_height_from_rows(rows))
                if has_leading_noise:
                    nearby_header = any(
                        not _looks_like_noise_prefix_row(prior_row, prior_parts, prior_text)
                        and row.y0 - prior_row.y1 <= connected_row_gap
                        for prior_row, prior_parts, prior_text in leading_rows
                    )
                    if nearby_header:
                        return current
                if has_leading_noise or large_gap:
                    new_y0 = max(current.y0, row.y0 - pad)
                    if new_y0 > current.y0 + 0.5 and current.y1 - new_y0 >= 40.0:
                        return fitz.Rect(current.x0, new_y0, current.x1, current.y1)
                return current

        elif direction == "below":
            ordered = sorted(rows, key=lambda item: item[0].y0, reverse=True)
            for row, part_count, text in ordered:
                if row.y1 > current.y1 + 0.5:
                    continue
                strong_table_end = part_count >= 2
                if not strong_table_end:
                    continue
                trailing_rows = [
                    later
                    for later in ordered
                    if later[0].y0 >= row.y1 - 0.5 and later[0].y1 <= current.y1 + 0.5
                ]
                has_trailing_noise = bool(trailing_rows)
                large_gap = current.y1 - row.y1 > max(18.0, 1.5 * typical_line_height_from_rows(rows))
                if has_trailing_noise:
                    nearby_footer = any(
                        (
                            not _looks_like_noise_prefix_row(later_row, later_parts, later_text)
                            or (
                                later_parts == 1
                                and later_row.width <= current.width * 0.45
                                and len(later_text.split()) <= 8
                                and not re.match(r"^\s*\d+(?:\.\d+)+\s+\S", later_text)
                            )
                        )
                        and later_row.y0 - row.y1 <= connected_row_gap
                        for later_row, later_parts, later_text in trailing_rows
                    )
                    if nearby_footer:
                        return current
                if has_trailing_noise or large_gap:
                    new_y1 = min(current.y1, row.y1 + pad)
                    if new_y1 < current.y1 - 0.5 and new_y1 - current.y0 >= 40.0:
                        return fitz.Rect(current.x0, current.y0, current.x1, new_y1)
                return current

        return current

    def typical_line_height_from_rows(rows: List[Tuple[Any, int, str]]) -> float:
        heights = [row.height for row, _parts, _text in rows if row.height > 0]
        if not heights:
            return 10.0
        heights = sorted(heights)
        return heights[len(heights) // 2]

    def _expand_far_side_to_connected_rows(current: Any) -> Any:
        search_rect = fitz.Rect(reference_clip)
        if direction == "above":
            search_rect.y1 = min(search_rect.y1, caption_rect.y0 - min_caption_gap)
            search_rect.y0 = max(search_rect.y0, current.y0 - far_max_expand)
        elif direction == "below":
            search_rect.y0 = max(search_rect.y0, caption_rect.y1 + min_caption_gap)
            search_rect.y1 = min(search_rect.y1, current.y1 + far_max_expand)
        else:
            return current
        if search_rect.width <= 1 or search_rect.height <= 1:
            return current

        rows = _group_rows(search_rect)
        if not rows:
            return current

        if direction == "above":
            selected_top = current.y0
            touched = False
            for row, part_count, text in sorted(rows, key=lambda item: item[0].y0, reverse=True):
                if row.y0 >= current.y1:
                    continue
                if row.y0 >= current.y0 - 0.5:
                    continue
                if row.y0 > selected_top + connected_row_gap:
                    continue
                gap = selected_top - row.y1
                if gap > connected_row_gap:
                    if touched:
                        break
                    continue
                if _looks_like_body_row(row, part_count, text):
                    break
                if not _looks_like_table_row(row, part_count, text):
                    break
                selected_top = min(selected_top, row.y0)
                touched = True
            if not touched or current.y0 - selected_top < 0.5:
                return current
            return fitz.Rect(
                current.x0,
                max(reference_clip.y0, selected_top - pad),
                current.x1,
                current.y1,
            )

        selected_bottom = current.y1
        touched = False
        for row, part_count, text in sorted(rows, key=lambda item: item[0].y0):
            if row.y1 <= current.y0:
                continue
            if row.y1 <= current.y1 + 0.5:
                continue
            if row.y1 < selected_bottom - connected_row_gap:
                continue
            gap = row.y0 - selected_bottom
            if gap > connected_row_gap:
                if touched:
                    break
                continue
            if _looks_like_body_row(row, part_count, text):
                break
            if not _looks_like_table_row(row, part_count, text):
                break
            selected_bottom = max(selected_bottom, row.y1)
            touched = True
        if not touched or selected_bottom - current.y1 < 0.5:
            return current
        return fitz.Rect(
            current.x0,
            current.y0,
            current.x1,
            min(reference_clip.y1, selected_bottom + pad),
        )

    trimmed_clip = _trim_far_side_body_prefix(clip)
    if not table_like_before_trim and not looks_like_table_text(trimmed_clip, text_lines):
        expanded_weak_clip = _expand_far_side_to_connected_rows(trimmed_clip)
        expanded_weak_clip = _expand_far_side_to_layout_row(expanded_weak_clip)
        if expanded_weak_clip == trimmed_clip:
            return clip
        clip = expanded_weak_clip
    else:
        clip = _expand_far_side_to_connected_rows(trimmed_clip)
        clip = _expand_far_side_to_layout_row(clip)
    clip = _trim_far_side_to_first_structured_row(clip)

    x0_bound = min(reference_clip.x0, clip.x0)
    x1_bound = max(reference_clip.x1, clip.x1)
    y0_bound = reference_clip.y0
    y1_bound = reference_clip.y1

    if direction == "above":
        y1_bound = max(y1_bound, caption_rect.y0 - min_caption_gap)
    elif direction == "below":
        y0_bound = min(y0_bound, caption_rect.y1 + min_caption_gap)

    probe = fitz.Rect(
        max(x0_bound, clip.x0 - max_expand),
        max(y0_bound, clip.y0 - max_expand),
        min(x1_bound, clip.x1 + max_expand),
        min(y1_bound, clip.y1 + max_expand),
    )
    if probe.width <= 1 or probe.height <= 1:
        return clip

    text_rect = None
    for line_rect, _font_size, text in text_lines:
        txt = (text or "").strip()
        if not txt:
            continue
        if re.match(r"^\s*Table\s+\S+", txt, re.I):
            continue
        caption_overlap = line_rect & caption_rect
        if caption_overlap.width > 0 and caption_overlap.height > 0:
            continue
        inter = line_rect & probe
        if inter.width <= 0 or inter.height <= 0:
            continue
        if direction == "above" and line_rect.y1 <= clip.y0 + 0.5 and _looks_like_body_line(line_rect, txt):
            continue
        if direction == "below" and line_rect.y0 >= clip.y1 - 0.5 and _looks_like_body_line(line_rect, txt):
            continue
        text_rect = fitz.Rect(line_rect) if text_rect is None else text_rect | line_rect

    if text_rect is None:
        return clip

    new_x0 = max(x0_bound, min(clip.x0, text_rect.x0 - pad))
    new_y0 = max(y0_bound, min(clip.y0, text_rect.y0 - pad))
    new_x1 = min(x1_bound, max(clip.x1, text_rect.x1 + pad))
    new_y1 = min(y1_bound, max(clip.y1, text_rect.y1 + pad))

    if new_x1 - new_x0 < 1 or new_y1 - new_y0 < 1:
        return clip
    expanded_clip = fitz.Rect(new_x0, new_y0, new_x1, new_y1)
    return _trim_far_side_to_first_structured_row(expanded_clip)

def trim_table_far_side_section_heading(
    clip: Any,
    caption_rect: Any,
    direction: str,
    layout_text_blocks: Optional[List[Any]],
    text_lines: Optional[List[Tuple[Any, float, str]]],
    *,
    typical_line_h: Optional[float] = None,
    gap: float = 6.0,
    far_region_ratio: float = 0.40,
    min_height: float = 40.0,
) -> Any:
    """从表格 final 远端去掉紧跟表格的章节标题。

    Qwen3-Omni 等论文里，章节标题的编号（如 ``5.1.2`` / ``5.2`` / ``9.2``）
    常被 PDF 抽取拆到后续正文段落，留下无编号的短标题（``Performance of
    Audio→Text``），绕过所有“编号章节标题”过滤，被表格远端纳入截图。

    判别一个远端 ``title_`` 块是否为章节标题，使用两个稳定信号：

    - 它紧跟其后就是一整段满宽正文段落（章节标题后必有正文），而表格列表头
      其后是表格数据行而非段落；
    - 它远端方向没有窄的表格单元格行（否则它只是表格内部的小节行，而非尾部标题）。
    """
    if fitz is None or not layout_text_blocks:
        return clip
    if clip.width <= 1 or clip.height <= 1:
        return clip

    lh = typical_line_h if (typical_line_h and typical_line_h > 0) else 10.0
    para_tol = 3.0 * lh

    def _block_text(block: Any) -> str:
        units = getattr(block, "units", None) or []
        if units:
            return " ".join((getattr(unit, "text", "") or "").strip() for unit in units).strip()
        return ""

    titles: List[Tuple[Any, str]] = []
    paragraphs: List[Tuple[Any, str]] = []
    for block in layout_text_blocks:
        block_type = getattr(block, "block_type", "") or ""
        rect = getattr(block, "bbox", None)
        if rect is None:
            continue
        if block_type.startswith("title_"):
            titles.append((rect, _block_text(block)))
        elif block_type in ("paragraph_group", "list_group"):
            paragraphs.append((rect, _block_text(block)))
    if not titles or not paragraphs:
        return clip

    def _is_body_paragraph(rect: Any, text: str) -> bool:
        words = text.split()
        if len(words) < 8:
            return False
        if rect.width < 0.55 * clip.width:
            return False
        if re.match(r"^\s*\d+(?:\.\d+)+\s+\S", text):
            return True
        if re.search(r"[.!?。！？；;:,，]($|\s)", text):
            return True
        return False

    def _has_near_section_number(title_rect: Any, title_text: str) -> bool:
        if re.match(r"^\s*\d+(?:\.\d+)+\s+\S", title_text):
            return True
        for line_rect, _font_size, text in text_lines or []:
            s = (text or "").strip()
            if not re.match(r"^\d+(?:\.\d+)+$", s):
                continue
            overlap = min(line_rect.y1, title_rect.y1) - max(line_rect.y0, title_rect.y0)
            if overlap <= 0.35 * min(title_rect.height, line_rect.height):
                continue
            if line_rect.x1 <= title_rect.x0 + max(18.0, 1.5 * lh):
                return True
        return False

    def _followed_by_body(title_rect: Any) -> bool:
        for p, text in paragraphs:
            if not _is_body_paragraph(p, text):
                continue
            if p.width < 0.55 * clip.width:
                continue
            if direction == "below":
                gap = p.y0 - title_rect.y1
                if -0.5 * lh <= gap <= para_tol:
                    return True
            elif direction == "above":
                gap = title_rect.y0 - p.y1
                if -0.5 * lh <= gap <= para_tol:
                    return True
            elif title_rect.y0 - lh <= p.y0 <= title_rect.y1 + para_tol:
                return True
        return False

    def _table_cells_beyond(title_rect: Any) -> int:
        count = 0
        for line_rect, _font_size, text in text_lines or []:
            if not (text or "").strip():
                continue
            inter = line_rect & clip
            if inter.width <= 0 or inter.height <= 0:
                continue
            if inter.width >= 0.55 * clip.width:
                continue  # 宽行视为正文段落，不计入表格单元格
            if direction == "below":
                if line_rect.y0 > title_rect.y1 + 0.3 * lh:
                    count += 1
            else:
                if line_rect.y1 < title_rect.y0 - 0.3 * lh:
                    count += 1
        return count

    def _has_same_row_table_context(title_rect: Any) -> bool:
        """标题同一横向行带是否存在并排的表格单元格。

        若有（如被误判为标题的表格最后一行 ``Generation RTF(...) 0.47 0.56``），
        说明它其实是表格行而非章节标题，应保留不裁。

        同时看左右两侧，以覆盖最右侧数据单元格被误判为标题的场景。
        章节编号（如 ``5.1.2``）需排除，以免误判真正的章节标题。
        """
        peer_cells = 0
        for line_rect, _font_size, text in text_lines or []:
            s = (text or "").strip()
            if not s:
                continue
            if re.match(r"^\d+(?:\.\d+)+$", s):
                continue
            overlap = min(line_rect.y1, title_rect.y1) - max(line_rect.y0, title_rect.y0)
            if overlap <= 0.5 * min(title_rect.height, line_rect.height):
                continue
            if line_rect.x1 > title_rect.x0 + 1 and line_rect.x0 < title_rect.x1 - 1:
                continue
            if line_rect.width >= 0.55 * clip.width and len(s.split()) >= 8:
                continue  # 宽长句是正文，不是并排表格单元格
            if line_rect.width >= 0.55 * clip.width:
                continue  # 宽行是正文段落，不是数据单元格
            if any(ch.isdigit() for ch in s) or len(s) <= 45:
                peer_cells += 1
        for block in layout_text_blocks or []:
            rect = getattr(block, "bbox", None)
            if rect is None:
                continue
            if rect is title_rect:
                continue
            text = _block_text(block)
            if not text or re.match(r"^\s*\d+(?:\.\d+)*\s*$", text):
                continue
            overlap = min(rect.y1, title_rect.y1) - max(rect.y0, title_rect.y0)
            if overlap <= 0.45 * min(title_rect.height, rect.height):
                continue
            if rect.x1 > title_rect.x0 + 1 and rect.x0 < title_rect.x1 - 1:
                continue
            if rect.width >= 0.55 * clip.width and len(text.split()) >= 8:
                continue
            if any(ch.isdigit() for ch in text) or len(text) <= 45:
                peer_cells += 1
        return peer_cells >= 1

    def _has_near_table_header_context(title_rect: Any) -> bool:
        row_centers: List[float] = []
        row_parts: List[int] = []
        for line_rect, _font_size, text in text_lines or []:
            s = (text or "").strip()
            if not s or re.match(r"^\d+(?:\.\d+)+$", s):
                continue
            inter = line_rect & clip
            if inter.width <= 0 or inter.height <= 0:
                continue
            if line_rect.width >= 0.55 * clip.width and len(s.split()) >= 8:
                continue
            if direction == "below":
                if not (title_rect.y0 - 0.5 * lh <= line_rect.y0 <= title_rect.y1 + 2.0 * lh):
                    continue
            else:
                if not (title_rect.y0 - 0.5 * lh <= line_rect.y0 <= title_rect.y1 + 2.5 * lh):
                    continue
            center = (line_rect.y0 + line_rect.y1) / 2.0
            matched = False
            for idx, existing in enumerate(row_centers):
                if abs(center - existing) <= 3.5:
                    row_parts[idx] += 1
                    matched = True
                    break
            if not matched:
                row_centers.append(center)
                row_parts.append(1)
        return any(parts >= 2 for parts in row_parts)

    def _is_section_heading_candidate(title_rect: Any, title_text: str) -> bool:
        if _has_same_row_table_context(title_rect):
            return False
        has_section_number = _has_near_section_number(title_rect, title_text)
        if has_section_number:
            return True
        if _has_near_table_header_context(title_rect):
            return False
        if _followed_by_body(title_rect):
            return True
        return False

    if direction == "below":
        cut: Optional[float] = None
        for title_rect, title_text in titles:
            inter = title_rect & clip
            if inter.width <= 0 or inter.height <= 0:
                continue
            if title_rect.y0 < clip.y0 + far_region_ratio * clip.height:
                continue
            if title_rect.y0 <= caption_rect.y1:
                continue
            if not _is_section_heading_candidate(title_rect, title_text):
                continue
            candidate = title_rect.y0 - gap
            if clip.y0 + min_height < candidate < clip.y1:
                cut = candidate if cut is None else min(cut, candidate)
        if cut is not None:
            return fitz.Rect(clip.x0, clip.y0, clip.x1, cut)
    elif direction == "above":
        cut = None
        for title_rect, title_text in titles:
            inter = title_rect & clip
            if inter.width <= 0 or inter.height <= 0:
                continue
            if title_rect.y1 > clip.y1 - far_region_ratio * clip.height:
                continue
            if title_rect.y1 >= caption_rect.y0:
                continue
            if not _is_section_heading_candidate(title_rect, title_text):
                continue
            candidate = title_rect.y1 + gap
            if clip.y0 < candidate < clip.y1 - min_height:
                cut = candidate if cut is None else max(cut, candidate)
        if cut is not None:
            return fitz.Rect(clip.x0, cut, clip.x1, clip.y1)

    return clip
