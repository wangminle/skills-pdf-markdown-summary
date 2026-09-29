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


def table_remainder_is_open(final_clip: Any, baseline: Any, text_lines: List, direction: str) -> bool:
    """只在原始、邻题注约束后的窗口内检查余量，不使用整页恢复搜索区。"""
    if direction == "below" and baseline.y1 > final_clip.y1 + 36.0:
        remainder = fitz.Rect(final_clip.x0, final_clip.y1, final_clip.x1, baseline.y1)
    elif direction == "above" and final_clip.y0 > baseline.y0 + 36.0:
        remainder = fitz.Rect(final_clip.x0, baseline.y0, final_clip.x1, final_clip.y0)
    else:
        return False
    # 余量窗口常与同页矢量图的散点标签重叠（Kimi K3 Table 5 下方 Figure 13
    # 的轴刻度/图例全是 4-6pt 短行，短行占比判据把它们当表格行误报
    # table_band_open）。以已收录表格行的字号中位数为基准过滤明显更小/更大
    # 的行；表内无文本行（纯线表格）时不过滤，保持原行为。
    inner_sizes = sorted(
        size for rect, size, text in text_lines
        if (text or "").strip()
        and (rect & final_clip).width > 0 and (rect & final_clip).height > 0
    )
    if inner_sizes:
        median_size = inner_sizes[len(inner_sizes) // 2]
        text_lines = [
            (rect, size, text) for rect, size, text in text_lines
            if abs(size - median_size) <= 2.5
        ]
    return looks_like_table_text(remainder, text_lines, min_lines=3)


def _rendered_rule_rows(
    page: Any,
    render_clip: Any,
    *,
    scale: float = 4.0,
    dark_threshold: int = 80,
    min_dark_fraction: float = 0.35,
) -> List[int]:
    """返回 render_clip 内「横向长线」所在的渲染行号（空列表=无线）。

    近题注边与远侧边共用同一判据：整行暗像素占比 >= min_dark_fraction。
    """
    try:
        matrix = fitz.Matrix(scale, scale)
        raw_page = getattr(page, "raw", page)
        pix = raw_page.get_pixmap(matrix=matrix, clip=render_clip, alpha=False)
    except Exception:
        return []

    if pix.width <= 0 or pix.height <= 0:
        return []

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
    return qualifying_rows


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

    qualifying_rows = _rendered_rule_rows(
        page, render_clip, scale=scale,
        dark_threshold=dark_threshold, min_dark_fraction=min_dark_fraction,
    )
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

def _other_side_line_continues_table(
    line_rect: Any,
    text: str,
    text_lines: Optional[List[Tuple[Any, float, str]]],
    mid: float,
    side: str,
    caption_rect: Any,
    clip: Any,
) -> bool:
    """判断另一侧的短文字行是否为通栏表格的延续单元格。

    无边框通栏表的右侧单元格与表内行 y 居中对齐（同一行跨栏延续），
    旧实现只数行数，会把它们当右栏正文触发收窄，把右半表切掉。
    判据：该行不是完整正文句，且与题注侧某条表内行有
    显著垂直重叠。PDF 字形框的 y 坐标常有几点偏移，不再使用固定
    3.5pt 中心距离。双栏正文即使基线对齐，也先由句子形态排除。
    """
    txt = (text or "").strip()
    words = re.findall(r"[A-Za-z]+(?:['’-][A-Za-z]+)?", txt)
    has_numeric_cell = bool(re.search(r"\d", txt)) and len(words) <= 4
    has_prose_verb = bool(re.search(
        r"\b(?:am|is|are|was|were|be|been|has|have|had|do|does|did|can|could|"
        r"will|would|may|might|shows?|uses?|covers?|includes?|contains?|provides?|"
        r"achieves?|outperforms?|discuss(?:es|ed)?|evaluat(?:es|ed))\b",
        txt,
        re.IGNORECASE,
    ))
    sentence_like = (
        len(txt) > 80
        or len(words) > 16
        or (
            not has_numeric_cell
            and len(words) >= 5
            and (
                has_prose_verb
                or txt.rstrip().endswith((".", "。", "!", "?", "；", ";"))
            )
        )
    )
    if sentence_like:
        return False
    for partner, _fs, partner_text in text_lines or []:
        if partner is None or partner is line_rect:
            continue
        if not (partner_text or "").strip():
            continue
        if side == "left":
            # 另一侧在右栏：伙伴必须在题注侧（左半）
            if partner.x0 > mid - 8:
                continue
        else:
            if partner.x1 < mid + 8:
                continue
        # 伙伴须与表框纵向相交（即表内行），且不能是题注自身
        if min(partner.y1, clip.y1) - max(partner.y0, clip.y0) <= 0:
            continue
        if (partner & caption_rect).get_area() > 0:
            continue
        overlap = min(partner.y1, line_rect.y1) - max(partner.y0, line_rect.y0)
        min_height = min(max(0.0, partner.height), max(0.0, line_rect.height))
        if min_height > 0 and overlap / min_height >= 0.30:
            return True
    return False


def limit_table_clip_to_caption_column(
    clip: Any,
    caption_rect: Any,
    page_rect: Any,
    text_lines: Optional[List[Tuple[Any, float, str]]] = None,
    drawings: Optional[List] = None,
) -> Any:
    """双栏页里，单栏题注的表框不要横贯另一栏。

    通栏横线仍然保留整页宽度。另一栏没有独立文字时也不收窄，
    避免把单栏论文里左对齐的通栏表裁掉。另一栏的文字行须先确认
    不是通栏表的跨栏延续行（见 _other_side_line_continues_table）
    才计入收窄证据。收窄前的原始框由调用方显式保存并传给
    restore_table_clip_width 作为恢复上限（否则收窄不可逆）——
    不要挂在返回矩形上：fitz.Rect 链上任何重建都会丢自定义属性。
    """
    if fitz is None or clip is None or page_rect is None or page_rect.width <= 1:
        return clip
    if clip.width < page_rect.width * 0.75:
        return clip
    mid = (page_rect.x0 + page_rect.x1) / 2.0
    cap_cx = (caption_rect.x0 + caption_rect.x1) / 2.0
    if abs(cap_cx - mid) < page_rect.width * 0.08:
        return clip
    side = "left" if cap_cx < mid else "right"
    for drawing in drawings or []:
        raw = drawing.get("rect") if isinstance(drawing, dict) else None
        if raw is None:
            continue
        rect = fitz.Rect(raw)
        if rect.height > 2.5 or rect.width < page_rect.width * 0.65:
            continue
        if min(rect.y1, clip.y1) - max(rect.y0, clip.y0) > 0:
            return clip
    other = 0
    for line_rect, _fs, text in text_lines or []:
        if line_rect is None:
            continue
        if min(line_rect.y1, clip.y1) - max(line_rect.y0, clip.y0) < 4:
            continue
        if side == "left" and line_rect.x0 > mid + 8:
            pass
        elif side == "right" and line_rect.x1 < mid - 8:
            pass
        else:
            continue
        if _other_side_line_continues_table(
            line_rect, text, text_lines, mid, side, caption_rect, clip,
        ):
            continue
        other += 1
    if other < 2:
        return clip
    gutter = 8.0
    if side == "left":
        narrowed = fitz.Rect(clip.x0, clip.y0, min(clip.x1, mid - gutter), clip.y1)
    else:
        narrowed = fitz.Rect(max(clip.x0, mid + gutter), clip.y0, clip.x1, clip.y1)
    return narrowed


def restore_table_clip_width(
    clip: Any,
    base_clip: Any,
    *,
    table_band_changed: bool,
    min_width_ratio: float = 0.40,
    pre_narrow_clip: Any = None,
) -> Any:
    """可靠表格行带成立时，恢复被对象裁切误缩成局部列的 X 范围。

    pre_narrow_clip 是 limit_table_clip_to_caption_column 收窄前的
    原始框（由调用方显式保存并传入），有则以它为恢复上限；否则以
    base_clip 为上限——若 base 本身已被收窄，40% 阈值会形同虚设，
    通栏表被误收窄后永远无法恢复。不要用矩形自定义属性传递原始框：
    fitz.Rect 拷贝构造会丢属性，主调用链上的任何重建都让属性失效。
    """
    if fitz is None or not table_band_changed or base_clip.width <= 1:
        return clip
    original = pre_narrow_clip
    if original is None or original.width <= 1:
        original = base_clip
    if clip.width >= original.width * min_width_ratio:
        return clip
    return fitz.Rect(original.x0, clip.y0, original.x1, clip.y1)

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

def _is_short_table_header_label(text: str) -> bool:
    txt = (text or "").strip()
    if not txt:
        return False
    words = txt.split()
    return (
        len(txt) <= 40
        and len(words) <= 4
        and not txt.rstrip().endswith((".", "。", "!", "?", "；", ";"))
    )


def _caption_overlap_blocks_header(line_rect: Any, caption_rect: Any, text: str) -> bool:
    """Skip caption-overlapping lines, but keep short header cells that only graze the caption."""
    overlap = line_rect & caption_rect
    if overlap.width <= 0 or overlap.height <= 0:
        return False
    if _is_short_table_header_label(text) and overlap.height < max(4.0, line_rect.height * 0.5):
        return False
    return True


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

    def _collect_header_candidates(
        clip: Any,
        band: Any,
        toward_caption: str,
        search_clip: Any,
    ) -> List[Any]:
        found: List[Any] = []
        for line_rect, _font_size, text in text_lines:
            txt = (text or "").strip()
            if not txt:
                continue
            if re.match(r"^\s*(?:Figure|Table)\s+\S+", txt, re.I):
                continue
            if _caption_overlap_blocks_header(line_rect, caption_rect, txt):
                continue
            if len(txt) > 140:
                continue
            if len(txt) > 80 and txt.rstrip().endswith((".", "。", "!", "?", "；", ";")):
                continue

            inter = line_rect & band
            if inter.width <= 0 or inter.height <= 0:
                continue
            if inter.width < max(24.0, search_clip.width * 0.04):
                continue

            if toward_caption in ("above", "below_near"):
                if line_rect.y0 >= clip.y0:
                    continue
                if line_rect.y0 < clip.y0 - max_header_height:
                    continue
                found.append(line_rect)
            elif toward_caption == "below_far" and line_rect.y1 > clip.y1:
                found.append(line_rect)
        return found

    def _apply_near_header(clip: Any, band_y0: float, band_y1: float, y0_floor: float) -> Any:
        probe = fitz.Rect(
            clip.x0,
            clip.y0,
            clip.x1,
            min(clip.y1, clip.y0 + table_probe_height),
        )
        if not looks_like_table_text(probe, text_lines, min_lines=3):
            return clip
        band = fitz.Rect(original_clip.x0, band_y0, original_clip.x1, band_y1)
        candidates = _collect_header_candidates(clip, band, "below_near" if direction == "below" else "above", original_clip)
        if len(candidates) < 2:
            return clip
        nearest_gap = clip.y0 - max(r.y1 for r in candidates)
        if nearest_gap > max_gap:
            return clip
        new_y0 = max(y0_floor, min(r.y0 for r in candidates) - pad)
        if new_y0 < clip.y0 and clip.y1 - new_y0 >= 40.0:
            return fitz.Rect(clip.x0, new_y0, clip.x1, clip.y1)
        return clip

    if direction == "above":
        if limited_clip.y0 <= original_clip.y0 + 0.5:
            return limited_clip
        return _apply_near_header(
            limited_clip,
            max(original_clip.y0, limited_clip.y0 - max_header_height),
            limited_clip.y0 + max_gap,
            original_clip.y0,
        )

    if direction != "below":
        return limited_clip

    recovered = limited_clip
    probe = fitz.Rect(
        recovered.x0,
        recovered.y0,
        recovered.x1,
        min(recovered.y1, recovered.y0 + table_probe_height),
    )
    if looks_like_table_text(probe, text_lines, min_lines=3):
        title_floor = caption_rect.y0 + min(12.0, max(8.0, caption_rect.height * 0.15))
        recovered = _apply_near_header(
            recovered,
            recovered.y0 - max_header_height,
            recovered.y0 + max_gap,
            title_floor,
        )

    far_side_cut = limited_clip.y1 < original_clip.y1 - 0.5
    if not far_side_cut:
        return recovered

    far_probe = fitz.Rect(
        recovered.x0,
        max(recovered.y0, recovered.y1 - table_probe_height),
        recovered.x1,
        recovered.y1,
    )
    if not looks_like_table_text(far_probe, text_lines, min_lines=3):
        return recovered
    band = fitz.Rect(
        original_clip.x0,
        recovered.y1 - max_gap,
        original_clip.x1,
        min(original_clip.y1, recovered.y1 + max_header_height),
    )
    candidates = _collect_header_candidates(recovered, band, "below_far", original_clip)
    if len(candidates) < 2:
        return recovered
    nearest_gap = min(r.y0 for r in candidates) - recovered.y1
    if nearest_gap > max_gap:
        return recovered
    new_y1 = min(original_clip.y1, max(r.y1 for r in candidates) + pad)
    if new_y1 > recovered.y1 and new_y1 - recovered.y0 >= 40.0:
        return fitz.Rect(recovered.x0, recovered.y0, recovered.x1, new_y1)
    return recovered

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
        stripped = text.strip()
        sentence_like = (
            len(stripped) > 80
            or len(words) > 16
            or (len(stripped) > 50 and stripped.rstrip().endswith((".", "。", "!", "?", "；", ";")))
        )
        if sentence_like and row_rect.width >= clip.width * 0.55:
            return True
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
        if _is_caption_like(txt):
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

    new_x0 = max(probe.x0, min(clip.x0, text_rect.x0 - pad))
    new_y0 = max(probe.y0, min(clip.y0, text_rect.y0 - pad))
    new_x1 = min(probe.x1, max(clip.x1, text_rect.x1 + pad))
    new_y1 = min(probe.y1, max(clip.y1, text_rect.y1 + pad))

    if new_x1 - new_x0 < 1 or new_y1 - new_y0 < 1:
        return clip
    expanded_clip = fitz.Rect(new_x0, new_y0, new_x1, new_y1)
    return _trim_far_side_to_first_structured_row(expanded_clip)

# 字母上标脚注起始（"a These 19 languages..."）：学术表格常见格式，
# Qwen3-Omni Table 6/17 实测首行 size 5.5、紧贴表底。要求单个小写字母后
# 跟标点或空白再接内容，避免 "a.k.a." 这类无空格缩写误匹配。
_LETTER_NOTE_START_RE = re.compile(r"^[a-z][).]?\s+\S")


def _table_note_rects(clip: Any, text_lines: List) -> List[Any]:
    """仅关联贴近表底、同列的小字号显式尾注及紧邻续行。

    字号容差 1.5、总高上限 64：DeepSeek Table 4 实测续行 max-span 字号
    与首行差 0.72、总高 47.3pt。Qwen 的上标虽是 5.5pt，
    collect_text_lines 返回整行最大字号 7.3pt，不能据上标放宽整行阈值。
    """
    ordered = sorted(text_lines, key=lambda item: (item[0].y0, item[0].x0))
    notes = []
    note_size = None
    start_y = None
    last_letter_marker = None
    for rect, size, text in ordered:
        text = (text or "").strip()
        if not text or rect.x0 < clip.x0 - 8 or rect.x1 > clip.x1 + 8:
            continue
        if not notes:
            if not (re.match(r"^(?:Notes?[.:]|注[：:])", text, re.I)
                    or _LETTER_NOTE_START_RE.match(text)):
                continue
            # 首行窗口须覆盖「尾注块已整体在框内」的二次调用：trim/far_side
            # 用扩边后的 clip 重新推导豁免时，首行距框底可达 尾注块高 64pt
            # （Qwen T6 实测 54.3pt），51pt 窗口会把首行落在框外、豁免失效，
            # 尾注被反过来当正文裁掉（final y1 停在 741.2 的成因）。
            if not (clip.y1 - 84 <= rect.y0 <= clip.y1 + 12) or size > 10:
                continue
            notes.append(rect)
            note_size, start_y = size, rect.y0
            if _LETTER_NOTE_START_RE.match(text):
                last_letter_marker = text[0].lower()
        else:
            # 轻微重叠通常是同行外来文字，不能跨过去继续桥接正文。
            # 仅 a→b→c 等明确连续的字母脚注允许这种重叠；Qwen T6/T17
            # 的 c 行与 b 行 bbox 实测重叠 1.8pt。
            if rect.y0 < notes[-1].y1 - 1:
                overlap = notes[-1].y1 - rect.y0
                letter_marker = text[0].lower() if _LETTER_NOTE_START_RE.match(text) else None
                sequential_marker = (
                    letter_marker is not None
                    and last_letter_marker is not None
                    and ord(letter_marker) == ord(last_letter_marker) + 1
                )
                if not sequential_marker or overlap > 0.5 * min(rect.height, notes[-1].height):
                    break
            if (rect.y0 - notes[-1].y1 > 4 or abs(size - note_size) > 1.5
                    or rect.y1 - start_y > 64 or text.startswith(("•", "Table ", "Figure "))):
                break
            notes.append(rect)
            if _LETTER_NOTE_START_RE.match(text):
                last_letter_marker = text[0].lower()
    return notes


def expand_clip_to_table_notes(
    clip: Any,
    text_lines: List,
    caption_rect: Optional[Any] = None,
    *,
    pad: float = 3.0,
) -> Any:
    """恢复表格底线外的显式注释，不扩大到随后的正文列表。

    caption_rect: 题注矩形。尾注是「表格自己的一部分」，题注在 Markdown 里
    单独渲染，不允许被拖进截图。判据只看尾注行本身是否压到题注——不用
    「回扩后整块 vs 题注」相交的粗判，因为 clip 本来就贴着题注边界，
    那样会把本来正常的回扩一起否掉。
    """
    notes = _table_note_rects(clip, text_lines)
    if not notes:
        return clip
    if caption_rect is not None and any(
        (note & caption_rect).get_area() > 0 for note in notes
    ):
        return clip
    grown = fitz.Rect(min(clip.x0, min(r.x0 for r in notes) - pad), clip.y0,
                      max(clip.x1, max(r.x1 for r in notes) + pad),
                      max(clip.y1, max(r.y1 for r in notes) + pad))
    if grown.height <= 1 or grown.width <= 1:
        return clip
    return grown


# 短脚注可以整行纳入以保住外框线；更高的正文块不跟着吞进来。
_BORDER_TEXT_EXTEND_LIMIT = 24.0


def _overlapping_text_lines(text_lines, x0, x1):
    lines = []
    for line_rect, _fs, _text in text_lines or []:
        if line_rect is None:
            continue
        if min(line_rect.x1, x1) - max(line_rect.x0, x0) <= 0.5:
            continue
        lines.append(line_rect)
    return lines


def _edge_inside_line(edge, line_rect) -> bool:
    return line_rect.y0 + 1e-3 < edge < line_rect.y1 - 1e-3


def _edge_inside_any(edge, lines) -> bool:
    return any(_edge_inside_line(edge, line) for line in lines)


def _short_line_past_rule(line_rect, rule_edge, *, toward_bottom: bool) -> bool:
    height = line_rect.y1 - line_rect.y0
    extra = (line_rect.y1 - rule_edge) if toward_bottom else (rule_edge - line_rect.y0)
    return height <= _BORDER_TEXT_EXTEND_LIMIT and extra <= _BORDER_TEXT_EXTEND_LIMIT


def _extend_through_short_lines(edge, lines, rule_edge, *, toward_bottom: bool):
    """边落在后续短行内部时，沿这些短行走到外侧，不穿过高正文。"""
    for _ in range(8):
        hosts = [
            line for line in lines
            if _edge_inside_line(edge, line)
            and _short_line_past_rule(line, rule_edge, toward_bottom=toward_bottom)
        ]
        if not hosts:
            return edge
        nxt = max(line.y1 for line in hosts) if toward_bottom else min(line.y0 for line in hosts)
        if abs(nxt - edge) <= 1e-3:
            return edge
        edge = nxt
    return edge


def _clear_bottom_edge(proposed, rule_y1, lines, clip_y1):
    """底边落到文字行内部时，改到行界上；保不住横线又不该吞正文时放弃扩展。"""
    if not _edge_inside_any(proposed, lines):
        return proposed
    stops = []
    for line in lines:
        if line.y0 >= rule_y1 - 0.05 and not _edge_inside_any(line.y0, lines):
            stops.append(line.y0)
        overlaps_rule = line.y0 < rule_y1 - 0.05
        if overlaps_rule and _short_line_past_rule(line, rule_y1, toward_bottom=True):
            far = _extend_through_short_lines(line.y1, lines, rule_y1, toward_bottom=True)
            if not _edge_inside_any(far, lines):
                stops.append(far)
    valid = [edge for edge in stops if edge >= rule_y1 - 0.05]
    if not valid:
        return clip_y1
    return min(valid)


def _clear_top_edge(proposed, rule_y0, lines, clip_y0):
    """顶边与底边对称。"""
    if not _edge_inside_any(proposed, lines):
        return proposed
    stops = []
    for line in lines:
        if line.y1 <= rule_y0 + 0.05 and not _edge_inside_any(line.y1, lines):
            stops.append(line.y1)
        overlaps_rule = line.y1 > rule_y0 + 0.05
        if overlaps_rule and _short_line_past_rule(line, rule_y0, toward_bottom=False):
            far = _extend_through_short_lines(line.y0, lines, rule_y0, toward_bottom=False)
            if not _edge_inside_any(far, lines):
                stops.append(far)
    valid = [edge for edge in stops if edge <= rule_y0 + 0.05]
    if not valid:
        return clip_y0
    return max(valid)


def _fit_border_edge_around_text(
    clip,
    new_y0,
    new_y1,
    top_rule_y0,
    bottom_rule_y1,
    text_lines,
    x0,
    x1,
):
    """调整补边，使外框线留在框内，且边不落在文字行内部。"""
    lines = _overlapping_text_lines(text_lines, x0, x1)
    if bottom_rule_y1 is not None and new_y1 > clip.y1:
        new_y1 = _clear_bottom_edge(new_y1, bottom_rule_y1, lines, clip.y1)
    if top_rule_y0 is not None and new_y0 < clip.y0:
        new_y0 = _clear_top_edge(new_y0, top_rule_y0, lines, clip.y0)
    return new_y0, new_y1


def expand_table_clip_to_border_rules(
    clip: Any,
    page: Any,
    text_lines: Optional[List[Tuple[Any, float, str]]] = None,
    *,
    max_gap: float = 4.0,
    pad: float = 1.5,
    min_rule_width: float = 0.55,
) -> Any:
    """把紧贴 clip 上/下边缘的表格横线（外框线）并入截图。

    Qwen3-Omni Table 6/17（底线距 clip 底 3.6pt）、Kimi Table 5（顶线距
    clip 顶 0.94pt）这类被文字收边排除掉的外框线会触发
    object_truncation/table_band_open 评审告警，且截图缺一条边。
    只并入水平方向与 clip 显著重叠、宽度达到 clip 55% 的横线；
    距离超过 max_gap 的线（多半属于下一个元素）不并入。

    硬约束：扩展不得切开文字行，也不得为此丢掉已经选中的外框线。
    行首在横线外侧时，把该侧收到行首（Qwen T6/T17 脚注在底线下方 0.9pt）。
    短行已经跨过原 clip 边，或字框压住横线时，收到行首会切字或丢线，
    改为纳入整行。与横线重叠的高正文不整段吞入，这一侧放弃扩展。
    """
    if fitz is None or clip.width <= 1 or clip.height <= 1:
        return clip
    page_rect = getattr(page, "rect", None)
    if page_rect is None:
        return clip
    x0 = min(clip.x0, page_rect.x1)
    x1 = max(clip.x1, page_rect.x0)
    min_w = (x1 - x0) * min_rule_width
    new_y0, new_y1 = clip.y0, clip.y1
    top_rule_y0 = None
    bottom_rule_y1 = None
    for d in page.get_drawings():
        rect = fitz.Rect(d["rect"])
        if rect.height > 2.5 or rect.width < min_w:
            continue
        horiz_overlap = min(rect.x1, x1) - max(rect.x0, x0)
        if horiz_overlap < min_w:
            continue
        if 0 <= clip.y0 - rect.y1 <= max_gap:
            new_y0 = min(new_y0, rect.y0 - pad)
            top_rule_y0 = rect.y0 if top_rule_y0 is None else min(top_rule_y0, rect.y0)
        if 0 <= rect.y0 - clip.y1 <= max_gap:
            new_y1 = max(new_y1, rect.y1 + pad)
            bottom_rule_y1 = rect.y1 if bottom_rule_y1 is None else max(bottom_rule_y1, rect.y1)

    new_y0, new_y1 = _fit_border_edge_around_text(
        clip,
        new_y0,
        new_y1,
        top_rule_y0,
        bottom_rule_y1,
        text_lines,
        x0,
        x1,
    )

    if new_y0 >= clip.y0:
        new_y0 = clip.y0
    if new_y1 <= clip.y1:
        new_y1 = clip.y1
    if new_y0 == clip.y0 and new_y1 == clip.y1:
        return clip
    # PyMuPDF 的空交集 Rect（x0>=x1）布尔值仍为 True，`or clip` 兜底不生效，
    # 必须显式判 is_empty；退化交集时回退原 clip 而非返回畸形框。
    clamped = fitz.Rect(clip.x0, new_y0, clip.x1, new_y1) & page_rect
    return clip if clamped.is_empty else clamped


def trim_table_clip_far_side_body(
    clip: Any,
    caption_rect: Any,
    text_lines: List[Tuple[Any, float, str]],
    direction: str,
    *,
    pad: float = 4.0,
    min_keep: float = 40.0,
) -> Any:
    """Drop a full-width body paragraph that follows a table on the far side."""
    if fitz is None or clip.width <= 1 or clip.height <= 1:
        return clip

    note_rects = _table_note_rects(clip, text_lines)

    def _is_body(text: str, rect: Any) -> bool:
        if any((rect & note).get_area() >= 0.9 * rect.get_area() for note in note_rects):
            return False
        txt = (text or "").strip()
        if not txt or re.match(r"^\s*(?:Table|Figure|Tab\.?|Fig\.?)\s+\S+", txt, re.I):
            return False
        words = txt.split()
        wide = rect.width >= clip.width * 0.55
        sentence_like = (
            len(txt) > 80
            or len(words) > 16
            or (len(txt) > 50 and txt.rstrip().endswith((".", "。", "!", "?", "；", ";")))
        )
        return wide and sentence_like

    if direction == "below":
        first_body = None
        for line_rect, _fs, text in sorted(text_lines, key=lambda item: item[0].y0):
            inter = line_rect & clip
            if inter.width <= 0 or inter.height <= 0:
                continue
            if line_rect.y0 <= caption_rect.y1 + 2.0:
                continue
            if _is_body(text, inter):
                first_body = line_rect
                break
        if first_body is None:
            return clip
        new_y1 = first_body.y0 - pad
        if new_y1 >= caption_rect.y1 + min_keep and new_y1 < clip.y1 - 0.5:
            return fitz.Rect(clip.x0, clip.y0, clip.x1, new_y1)
        return clip

    if direction == "above":
        last_body = None
        for line_rect, _fs, text in sorted(text_lines, key=lambda item: item[0].y0, reverse=True):
            inter = line_rect & clip
            if inter.width <= 0 or inter.height <= 0:
                continue
            if line_rect.y1 >= caption_rect.y0 - 2.0:
                continue
            if _is_body(text, inter):
                last_body = line_rect
                break
        if last_body is None:
            return clip
        new_y0 = last_body.y1 + pad
        if new_y0 <= caption_rect.y0 - min_keep and new_y0 > clip.y0 + 0.5:
            return fitz.Rect(clip.x0, new_y0, clip.x1, clip.y1)
        return clip

    return clip

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
