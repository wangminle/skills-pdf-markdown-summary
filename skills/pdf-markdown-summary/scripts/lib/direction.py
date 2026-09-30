#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
智能方向判定与全局锚点

V0.4.0 新增：从 extract_pdf_assets.py 迁移的方向判定逻辑

包含：
- compute_global_anchor: 计算全局锚点方向
- score_direction: 评估单个 caption 的方向得分
- estimate_ink_ratio_for_clip: 估计裁剪区域的墨迹密度
"""

from __future__ import annotations

import logging
import math
import re
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

from .pdf_backend import create_rect, open_pdf
from .extract_helpers import collect_draw_items, collect_image_rects, collect_text_lines
from .pixel_detect import estimate_ink_ratio, estimate_region_ink_ratio

if TYPE_CHECKING:
    import fitz

logger = logging.getLogger(__name__)


def compute_object_ratio(
    clip: "fitz.Rect",
    image_rects: List["fitz.Rect"],
    vector_rects: List["fitz.Rect"],
) -> float:
    """
    计算裁剪区域内的对象覆盖率。

    Args:
        clip: 裁剪区域
        image_rects: 图像边界框列表
        vector_rects: 矢量对象边界框列表

    Returns:
        对象覆盖率 (0.0~1.0)
    """
    area = max(1.0, clip.width * clip.height)
    acc = 0.0

    for r in image_rects + vector_rects:
        inter = r & clip
        if inter.width > 0 and inter.height > 0:
            acc += inter.width * inter.height

    return min(1.0, acc / area)


def score_direction_for_caption(
    page: "fitz.Page",
    caption_bbox: "fitz.Rect",
    page_rect: "fitz.Rect",
    image_rects: List["fitz.Rect"],
    vector_rects: List["fitz.Rect"],
    clip_height: float = 400.0,
    margin_x: float = 20.0,
    caption_gap: float = 3.0,
) -> Tuple[float, float]:
    """
    为单个 caption 计算 above 和 below 两个方向的得分。

    得分基于：
    - 墨迹密度（60% 权重）
    - 对象覆盖率（40% 权重）

    Args:
        page: PDF 页面对象
        caption_bbox: Caption 边界框
        page_rect: 页面边界框
        image_rects: 图像边界框列表
        vector_rects: 矢量对象边界框列表
        clip_height: 裁剪窗口高度
        margin_x: 水平边距
        caption_gap: Caption 与图像间隙

    Returns:
        (above_score, below_score) 元组
    """
    try:
        import fitz
    except ImportError:
        return 0.0, 0.0

    x_left = page_rect.x0 + margin_x
    x_right = page_rect.x1 - margin_x

    # Above clip
    y_bottom_above = caption_bbox.y0 - caption_gap
    y_top_above = max(page_rect.y0, y_bottom_above - clip_height)
    clip_above = create_rect(x_left, y_top_above, x_right, y_bottom_above)

    # Below clip
    y_top_below = caption_bbox.y1 + caption_gap
    y_bottom_below = min(page_rect.y1, y_top_below + clip_height)
    clip_below = create_rect(x_left, y_top_below, x_right, y_bottom_below)

    # 计算 above 得分
    try:
        pix_above = page.get_pixmap(dpi=72, clip=clip_above, alpha=False)
        ink_above = estimate_ink_ratio(pix_above)
    except Exception:
        ink_above = 0.0
    obj_above = compute_object_ratio(clip_above, image_rects, vector_rects)
    score_above = 0.6 * ink_above + 0.4 * obj_above

    # 计算 below 得分
    try:
        pix_below = page.get_pixmap(dpi=72, clip=clip_below, alpha=False)
        ink_below = estimate_ink_ratio(pix_below)
    except Exception:
        ink_below = 0.0
    obj_below = compute_object_ratio(clip_below, image_rects, vector_rects)
    score_below = 0.6 * ink_below + 0.4 * obj_below

    return score_above, score_below


def score_scan_structure_for_caption(
    page: "fitz.Page",
    caption_bbox: "fitz.Rect",
    page_rect: "fitz.Rect",
    text_lines: Optional[List[Tuple["fitz.Rect", float, str]]] = None,
    *,
    clip_height: float = 400.0,
    margin_x: float = 20.0,
    caption_gap: float = 3.0,
    min_evidence: float = 0.005,
) -> Tuple[float, float]:
    """扫描页（无原生对象）方向证据：题注上下区域的结构墨迹。

    扫描页的位图/矢量对象被整页载体过滤后，OCR 文字行是唯一文本证据，
    但文字墨迹度量的是段落而不是图形，直接用会随段落分布抖动。这里把
    全部文本行遮罩掉，只比较两侧剩下的结构墨迹（图形边框、连线、箭头），
    窗口口径与 score_direction_for_caption 一致，但 x 向取题注所在栏
    （±margin_x），避免邻栏图形污染方向判断。

    两侧结构墨迹都低于 min_evidence 时返回 (0.0, 0.0)，表示「无方向
    证据」——调用方不得据此直接给出方向。
    """
    if page is None:
        return 0.0, 0.0

    masks = [lb for (lb, _fs, txt) in (text_lines or []) if str(txt).strip()]
    x_left = max(page_rect.x0, caption_bbox.x0 - margin_x)
    x_right = min(page_rect.x1, caption_bbox.x1 + margin_x)
    if x_right - x_left <= 1.0:
        x_left, x_right = page_rect.x0 + margin_x, page_rect.x1 - margin_x

    y_bottom_above = caption_bbox.y0 - caption_gap
    y_top_above = max(page_rect.y0, y_bottom_above - clip_height)
    above_ratio = estimate_region_ink_ratio(
        page, create_rect(x_left, y_top_above, x_right, y_bottom_above),
        mask_rects=masks,
    )

    y_top_below = caption_bbox.y1 + caption_gap
    y_bottom_below = min(page_rect.y1, y_top_below + clip_height)
    below_ratio = estimate_region_ink_ratio(
        page, create_rect(x_left, y_top_below, x_right, y_bottom_below),
        mask_rects=masks,
    )

    if max(above_ratio, below_ratio) < min_evidence:
        return 0.0, 0.0
    return above_ratio, below_ratio


def compute_global_anchor(
    doc: "fitz.Document",
    caption_pattern: "re.Pattern",
    *,
    clip_height: float = 400.0,
    margin_x: float = 20.0,
    caption_gap: float = 3.0,
    margin: float = 0.02,
    is_table: bool = False,
    debug: bool = False,
) -> Optional[str]:
    """
    预扫描文档，计算全局锚点方向。

    遍历所有 caption，累计 above/below 两个方向的得分，
    如果差异超过 margin 阈值，返回得分较高的方向。

    Args:
        doc: PDF 文档对象
        caption_pattern: Caption 正则表达式
        clip_height: 裁剪窗口高度
        margin_x: 水平边距
        caption_gap: Caption 与图像间隙
        margin: 判定阈值（需要超过此比例才确定方向）
        is_table: 是否为表格（表格默认 below）
        debug: 调试模式

    Returns:
        'above' | 'below' | None（无法确定）
    """
    try:
        import fitz
    except ImportError:
        return None

    above_total = 0.0
    below_total = 0.0
    caption_count = 0
    scan_caption_count = 0
    # 扫描页的结构墨迹比例单独累计：它与原生对象评分的量纲不同（面积加权
    # vs 像素占比），混入同一总和会让扫描证据被原生证据淹没。只在整篇都
    # 没有原生题注证据时，才退到这份像素级证据。
    scan_above_total = 0.0
    scan_below_total = 0.0

    for pno in range(len(doc)):
        page = doc[pno]
        page_rect = page.rect
        dict_data = page.get_text("dict")

        # 收集对象
        draw_items = collect_draw_items(page)
        image_rects: List[fitz.Rect] = []
        vector_rects: List[fitz.Rect] = []

        # 收集对象。口径必须与对应提取主循环一致：图路径主循环只收 'O'
        # （extract_figures 的 Phase A/B 不把 H/V 线段当图形对象，局部方向
        # 证据 score_local_direction 也只看这些 rects），表格路径主循环
        # 收 H/V/O（表格线是表格的主要证据）。锚点口径宽于主循环时，纯
        # 折线/柱状图页会出现「锚点看得见线段、局部证据为空」的对撞。
        wanted_orients = ('O', 'H', 'V') if is_table else ('O',)
        for item in draw_items:
            if item.orient in wanted_orients:
                vector_rects.append(item.rect)

        image_rects = collect_image_rects(dict_data, page_rect)
        scan_only = not image_rects and not vector_rects and any(
            block.get("type") == 1 for block in dict_data.get("blocks", [])
        )
        page_text_lines = collect_text_lines(dict_data) if scan_only else None

        # 查找 captions
        for blk in dict_data.get("blocks", []):
            if blk.get("type", 0) != 0:
                continue

            for ln in blk.get("lines", []):
                spans = ln.get("spans", [])
                if not spans:
                    continue

                text = "".join(sp.get("text", "") for sp in spans)
                text_stripped = text.strip()

                match = caption_pattern.match(text_stripped)
                if not match:
                    continue
                if scan_only:
                    scan_caption_count += 1
                    # 无原生对象不等于无方向证据：遮掉 OCR 文本行后比较
                    # 题注上下两侧的结构墨迹（图形边框/连线）。
                    caption_bbox = create_rect(*(ln.get("bbox", [0, 0, 0, 0])))
                    scan_above, scan_below = score_scan_structure_for_caption(
                        page, caption_bbox, page_rect, page_text_lines,
                        clip_height=clip_height,
                        margin_x=margin_x,
                        caption_gap=caption_gap,
                    )
                    if scan_above + scan_below > 0:
                        scan_above_total += scan_above
                        scan_below_total += scan_below
                    if debug:
                        print(f"[GLOBAL_ANCHOR] Page {pno+1} (scan): "
                              f"above={scan_above:.4f}, below={scan_below:.4f}")
                    continue

                caption_bbox = create_rect(*(ln.get("bbox", [0, 0, 0, 0])))

                score_above, score_below = score_direction_for_caption(
                    page, caption_bbox, page_rect,
                    image_rects, vector_rects,
                    clip_height=clip_height,
                    margin_x=margin_x,
                    caption_gap=caption_gap,
                )

                above_total += score_above
                below_total += score_below
                caption_count += 1

                if debug:
                    print(f"[GLOBAL_ANCHOR] Page {pno+1}: above={score_above:.3f}, below={score_below:.3f}")

    if caption_count == 0:
        # 无原生对象/矢量的扫描页：用遮掉 OCR 文本行后的结构墨迹定方向。
        # 有证据就用证据，证据不足才落到约定值，不得无条件认定 above。
        scan_total = scan_above_total + scan_below_total
        if scan_total > 1e-6:
            scan_dir = "above" if scan_above_total >= scan_below_total else "below"
            if debug:
                print(f"[GLOBAL_ANCHOR] Scan structure: above={scan_above_total:.4f}, "
                      f"below={scan_below_total:.4f} -> {scan_dir}")
            return scan_dir
        if scan_caption_count and not is_table:
            # 有扫描题注但上下两侧都没有可辨结构墨迹（例如纯文字页）：
            # 此时像素证据为零，保留图题在下的常规约定。
            if debug:
                print("[GLOBAL_ANCHOR] Scan captions but no structural ink, "
                      "falling back to 'above'")
            return "above"
        if debug:
            print(f"[GLOBAL_ANCHOR] No captions found, returning None")
        return None

    # 归一化
    total = above_total + below_total
    if total < 1e-6:
        return None

    above_ratio = above_total / total
    below_ratio = below_total / total

    if debug:
        print(f"[GLOBAL_ANCHOR] Total: above={above_total:.3f} ({above_ratio:.1%}), "
              f"below={below_total:.3f} ({below_ratio:.1%}), "
              f"margin={margin:.1%}")

    # 判定
    if above_ratio > 0.5 + margin:
        return 'above'
    elif below_ratio > 0.5 + margin:
        return 'below'
    else:
        return None


def captions_share_column(
    caption_a: "fitz.Rect",
    caption_b: "fitz.Rect",
    *,
    min_ratio: float = 0.5,
) -> bool:
    """两个题注是否处于同一栏（横向显著重叠）。

    邻题注参与几何判断前必须先过栏位检查：双栏页面上两栏各有一张图表时，
    另一栏的题注在纵向上往往正好位于当前题注的同侧，若不看横向位置：
    - `direction.py`：`_neighbor_attaches_below` 会把它认作「向下关联」的
      邻题注，`_owned_by_neighbor` 随即认领当前栏题注上方的所有表格行并
      清空上方证据，方向由 above 翻成 below，截取到错误区域；
    - `clip_limit.py` / `figure_post.py`：它会成为边界停止线，把本栏 clip
      从邻栏题注处截断（实测 240→318，丢掉 78pt 图形内容）。

    阈值取较窄者的 50%：同栏题注或通栏题注重叠比例接近 1，跨栏题注
    重叠为 0 或仅栏间距级别的几点（pt）擦边。
    """
    overlap = min(caption_a.x1, caption_b.x1) - max(caption_a.x0, caption_b.x0)
    if overlap <= 1.0:
        return False
    narrower = min(caption_a.width, caption_b.width)
    if narrower <= 0:
        return False
    return overlap >= narrower * min_ratio


def score_local_direction(
    caption_bbox: "fitz.Rect",
    page_rect: "fitz.Rect",
    image_rects: List["fitz.Rect"],
    vector_rects: List["fitz.Rect"],
    clip_height: float = 400.0,
    margin_x: float = 20.0,
    caption_gap: float = 3.0,
    is_table: bool = False,
    text_lines: Optional[List[Tuple["fitz.Rect", float, str]]] = None,
    neighbor_caption_rects: Optional[List["fitz.Rect"]] = None,
) -> Tuple[str, float]:
    """
    基于局部对象密度评估单个 caption 的方向。

    分析 caption 上方和下方的对象覆盖率，返回得分更高的方向。
    与全局锚点不同，这是针对单个 caption 的局部判断。

    Args:
        caption_bbox: Caption 边界框
        page_rect: 页面边界框
        image_rects: 图像边界框列表
        vector_rects: 矢量对象边界框列表
        clip_height: 预估裁剪窗口高度
        margin_x: 水平边距
        caption_gap: Caption 与图像间隙
        is_table: 是否为表格
        neighbor_caption_rects: 同页其他 caption，用于避免把前一张表当成当前题注的内容

    Returns:
        (direction, confidence) 元组
    """
    try:
        import fitz as _fitz
    except ImportError:
        _fitz = None

    if _fitz is None:
        return ('below' if is_table else 'above', 0.5)

    collapse_above_objects = False
    if is_table and text_lines:
        search_height = min(300.0, max(160.0, clip_height * 0.5))
        page_width = max(1.0, page_rect.width)
        mid = (page_rect.x0 + page_rect.x1) / 2
        # Disjoint columns must never form a synthetic multi-cell table row.
        if caption_bbox.x1 < mid:
            text_lines = [line for line in text_lines if line[0].x0 < mid]
        elif caption_bbox.x0 > mid:
            text_lines = [line for line in text_lines if line[0].x1 > mid]
        # 只让同栏题注参与归属判断（跨栏题注见 captions_share_column 注释）
        neighbors = [
            rect for rect in (neighbor_caption_rects or [])
            if rect is not None and captions_share_column(rect, caption_bbox)
        ]

        def _looks_table_line(rect: "fitz.Rect", text: str) -> bool:
            stripped = text.strip()
            if not stripped:
                return False
            if re.match(r"^\s*(?:table|tab\.?|figure|fig\.?)\s*[A-Z]?\d+\b", stripped, re.I):
                return False
            if re.match(r"^[A-H]\.\s+\S", stripped):
                return False
            if re.match(r"^\d+(?:\.\d+)+\s+\S", stripped):
                return False
            digit_hits = len(re.findall(r"\d+(?:\.\d+)?%?", stripped))
            short_cell = len(stripped) <= 40 or rect.width < page_width * 0.55
            return digit_hits >= 2 or (short_cell and len(stripped) <= 24)

        def _structured_side(nbr: "fitz.Rect", side: str) -> Tuple[int, Optional[float]]:
            band_lines = []
            for line in text_lines:
                rect, _fs, text = line
                if not _looks_table_line(rect, text):
                    continue
                if side == "above":
                    if not (rect.y1 <= nbr.y0 - 2.0 and nbr.y0 - rect.y1 <= 50.0):
                        continue
                    gap = nbr.y0 - rect.y1
                else:
                    if not (rect.y0 >= nbr.y1 + 2.0 and rect.y0 - nbr.y1 <= 50.0):
                        continue
                    gap = rect.y0 - nbr.y1
                band_lines.append((rect, text, gap))
            if not band_lines:
                return 0, None
            rows: List[List[Tuple["fitz.Rect", str, float]]] = []
            centers: List[float] = []
            for item in sorted(band_lines, key=lambda entry: (entry[0].y0, entry[0].x0)):
                center = (item[0].y0 + item[0].y1) / 2.0
                if rows and abs(center - centers[-1]) <= 3.0:
                    rows[-1].append(item)
                    centers[-1] = sum(
                        (entry[0].y0 + entry[0].y1) / 2.0 for entry in rows[-1]
                    ) / len(rows[-1])
                else:
                    rows.append([item])
                    centers.append(center)
            structured = [row for row in rows if len(row) >= 2]
            if not structured:
                return 0, None
            return len(structured), min(item[2] for row in structured for item in row)

        def _neighbor_attaches_below(nbr: "fitz.Rect") -> bool:
            """True when the neighbor caption sits above its own table."""
            above_rows, above_gap = _structured_side(nbr, "above")
            below_rows, below_gap = _structured_side(nbr, "below")
            if below_rows == 0 or below_gap is None:
                return False
            if above_rows == 0:
                return True
            return below_gap + 8.0 < above_gap

        downward_neighbors = [nbr for nbr in neighbors if _neighbor_attaches_below(nbr)]
        collapse_above_objects = any(nbr.y1 < caption_bbox.y0 for nbr in downward_neighbors)

        def _owned_by_neighbor(line_rect: "fitz.Rect") -> bool:
            for nbr in downward_neighbors:
                if nbr.y1 <= line_rect.y0 and line_rect.y1 <= caption_bbox.y0:
                    return True
            for nbr in neighbors:
                if caption_bbox.y1 <= line_rect.y0 and line_rect.y1 <= nbr.y0:
                    dist_curr = line_rect.y0 - caption_bbox.y1
                    dist_nbr = nbr.y0 - line_rect.y1
                    if dist_nbr + 8.0 < dist_curr:
                        return True
            return False

        def table_text_features(side: str) -> Tuple[float, Optional[float], int, Optional[float]]:
            if side == 'above':
                nearby = [
                    line for line in text_lines
                    if line[0].y1 <= caption_bbox.y0 - 2.0
                    and line[0].y0 >= caption_bbox.y0 - search_height
                ]
                gaps = [caption_bbox.y0 - line[0].y1 for line in nearby]
            else:
                nearby = [
                    line for line in text_lines
                    if line[0].y0 >= caption_bbox.y1 + 2.0
                    and line[0].y1 <= caption_bbox.y1 + search_height
                ]
                gaps = [line[0].y0 - caption_bbox.y1 for line in nearby]

            caption_like_gaps = [
                (caption_bbox.y0 - line[0].y1) if side == "above" else (line[0].y0 - caption_bbox.y1)
                for line in nearby
                if re.match(
                    r"^\s*(?:table|tab\.?|figure|fig\.?)\s*[A-Z]?\d+\b",
                    line[2].strip(),
                    re.IGNORECASE,
                )
            ]
            nearby = [
                line for line in nearby
                if not re.match(
                    r"^\s*(?:table|tab\.?|figure|fig\.?)\s*[A-Z]?\d+\b",
                    line[2].strip(),
                    re.IGNORECASE,
                )
                and not _owned_by_neighbor(line[0])
                and not (
                    line[0].width < page_width * 0.08
                    and len(line[2].strip()) <= 8
                    and line[0].y0 >= page_rect.y1 - max(80.0, page_rect.height * 0.10)
                )
            ]
            gaps = [(caption_bbox.y0 - line[0].y1) if side == "above"
                    else (line[0].y0 - caption_bbox.y1) for line in nearby]

            if not nearby:
                return 0.0, None, 0, (min(caption_like_gaps) if caption_like_gaps else None)

            rows: List[List[Tuple["fitz.Rect", float, str]]] = []
            row_centers: List[float] = []
            for line in sorted(nearby, key=lambda item: (item[0].y0, item[0].x0)):
                center = (line[0].y0 + line[0].y1) / 2.0
                if rows and any(
                    min(line[0].y1, item[0].y1) - max(line[0].y0, item[0].y0)
                    >= 0.30 * min(line[0].height, item[0].height)
                    for item in rows[-1]
                ):
                    rows[-1].append(line)
                    row_centers[-1] = sum(
                        (item[0].y0 + item[0].y1) / 2.0 for item in rows[-1]
                    ) / len(rows[-1])
                else:
                    rows.append([line])
                    row_centers.append(center)

            structured_gaps: List[float] = []
            for row in rows:
                row = [line for line in row if _looks_table_line(line[0], line[2])]
                if not row:
                    continue
                row_rect = row[0][0]
                for line_rect, _font_size, _text in row[1:]:
                    row_rect = row_rect | line_rect
                if len(row) >= 2 and row_rect.width >= page_width * 0.15:
                    if side == "above":
                        structured_gaps.append(caption_bbox.y0 - row_rect.y1)
                    else:
                        structured_gaps.append(row_rect.y0 - caption_bbox.y1)

            short_like = 0
            wide_long = 0
            for line_rect, _font_size, text in nearby:
                text_len = len(text.strip())
                if text_len <= 40 or line_rect.width < page_width * 0.55:
                    short_like += 1
                if text_len >= 40 and line_rect.width >= page_width * 0.55:
                    wide_long += 1

            short_ratio = short_like / len(nearby)
            wide_long_ratio = wide_long / len(nearby)
            nearest_gap = min(structured_gaps) if structured_gaps else min(gaps)
            proximity = math.exp(-nearest_gap / 20.0)
            structure_bonus = min(1.0, len(structured_gaps) / 4.0)
            score = (
                0.20 * short_ratio
                + 0.15 * (1.0 - wide_long_ratio)
                + 0.50 * proximity
                + 0.15 * structure_bonus
            )
            return (
                score,
                (min(structured_gaps) if structured_gaps else None),
                len(structured_gaps),
                (min(caption_like_gaps) if caption_like_gaps else None),
            )

        (
            above_text_score,
            above_structured_gap,
            above_structured_count,
            above_caption_like_gap,
        ) = table_text_features('above')
        (
            below_text_score,
            below_structured_gap,
            below_structured_count,
            below_caption_like_gap,
        ) = table_text_features('below')
        score_diff = abs(above_text_score - below_text_score)
        if (
            above_structured_gap is not None
            and below_structured_gap is not None
            and below_caption_like_gap is not None
            and below_caption_like_gap <= search_height
            and above_structured_gap <= 25.0
            and abs(above_structured_gap - below_structured_gap) <= 8.0
            and below_text_score - above_text_score <= 0.12
        ):
            return 'above', 0.62
        if above_structured_count == 0 and below_structured_count > 0:
            return 'below', 0.88
        if below_structured_count == 0 and above_structured_count > 0:
            return 'above', 0.88
        if score_diff >= 0.03:
            direction = 'above' if above_text_score > below_text_score else 'below'
            confidence = min(0.95, 0.60 + score_diff * 2.0)
            return direction, confidence
        if (
            above_structured_gap is not None
            and below_structured_gap is not None
            and above_structured_count > 0
            and below_structured_count > 0
        ):
            gap_diff = abs(above_structured_gap - below_structured_gap)
            nearest_gap = min(above_structured_gap, below_structured_gap)
            if gap_diff >= 5.0 and nearest_gap <= 35.0:
                direction = 'above' if above_structured_gap < below_structured_gap else 'below'
                confidence = min(0.72, 0.60 + gap_diff / 100.0)
                return direction, confidence

    x_left = page_rect.x0 + margin_x
    x_right = page_rect.x1 - margin_x

    above_h = max(1.0, caption_bbox.y0 - page_rect.y0 - caption_gap)
    below_h = max(1.0, page_rect.y1 - caption_bbox.y1 - caption_gap)

    clip_above = create_rect(x_left, max(page_rect.y0, caption_bbox.y0 - clip_height - caption_gap), x_right, caption_bbox.y0 - caption_gap)
    clip_below = create_rect(x_left, caption_bbox.y1 + caption_gap, x_right, min(page_rect.y1, caption_bbox.y1 + clip_height + caption_gap))

    if collapse_above_objects:
        clip_above = create_rect(clip_above.x0, clip_above.y1, clip_above.x1, clip_above.y1)
    elif is_table and neighbor_caption_rects:
        for nbr in neighbor_caption_rects:
            # 同样只看同栏题注：邻栏题注不该收窄本栏的上下搜索窗
            if nbr is None or not captions_share_column(nbr, caption_bbox):
                continue
            if nbr.y1 < caption_bbox.y0:
                clip_above = create_rect(
                    clip_above.x0,
                    max(clip_above.y0, nbr.y1 + caption_gap),
                    clip_above.x1,
                    clip_above.y1,
                )
            if nbr.y0 > caption_bbox.y1:
                clip_below = create_rect(
                    clip_below.x0,
                    clip_below.y0,
                    clip_below.x1,
                    min(clip_below.y1, nbr.y0 - caption_gap),
                )

    obj_above = compute_object_ratio(clip_above, image_rects, vector_rects)
    obj_below = compute_object_ratio(clip_below, image_rects, vector_rects)

    total = obj_above + obj_below
    if total < 0.001:
        # 无任何对象证据：置信度必须是 0.0 而非 0.5。
        # determine_direction 以 local_conf >= 0.5 为直接采用门槛，
        # 0.5 哨兵与真实证据恰好 0.5 不可区分，会把零证据页面锁死在
        # 默认方向并压制全局锚点（锚点仅在 local_conf < 0.5 时接管）。
        return ('below' if is_table else 'above', 0.0)

    above_ratio = obj_above / total
    below_ratio = obj_below / total

    if above_ratio > 0.6:
        return ('above', above_ratio)
    elif below_ratio > 0.6:
        return ('below', below_ratio)

    return ('below' if is_table else 'above', max(above_ratio, below_ratio))


def correct_bare_figure_caption_direction(
    direction: str,
    caption_bbox: "fitz.Rect",
    caption_text: str,
    page_rect: "fitz.Rect",
    image_rects: List["fitz.Rect"],
    vector_rects: List["fitz.Rect"],
    neighbor_caption_rects: List["fitz.Rect"],
    *,
    clip_height: float = 400.0,
    caption_gap: float = 3.0,
) -> str:
    """纠正 caption 被下方下一张图吸走的方向。

    有些页面连续摆放两张图：当前 caption 属于上方图，但下方下一张图面积更大，
    普通对象覆盖率会把当前 caption 锚到下方。这里要求同时满足：当前已判为
    below、下方有下一张 figure caption、当前 caption 上方有更贴近的对象证据。
    """
    if direction != "below":
        return direction
    caption_text = caption_text or ""
    is_bare_caption = bool(re.match(r"^\s*(?:figure|fig\.?)\s+[A-Z]?\d+\s*$", caption_text, re.I))
    is_explicit_caption = bool(
        re.match(r"^\s*(?:figure|fig\.?)\s+[A-Z]?\d+\s*(?:[:：]|\|)\s+", caption_text, re.I)
    )
    if not (is_bare_caption or is_explicit_caption):
        return direction

    next_caption_gaps = [
        rect.y0 - caption_bbox.y1
        for rect in neighbor_caption_rects
        if rect.y0 >= caption_bbox.y1 + caption_gap
    ]
    if not next_caption_gaps:
        return direction
    if min(next_caption_gaps) > min(340.0, max(140.0, clip_height * 0.85)):
        return direction

    search_top = max(page_rect.y0, caption_bbox.y0 - min(220.0, max(80.0, clip_height * 0.55)))
    near_above = create_rect(page_rect.x0, search_top, page_rect.x1, caption_bbox.y0 - caption_gap)
    if near_above.height <= 1:
        return direction

    above_gaps: List[float] = []
    for rect in list(image_rects) + list(vector_rects):
        inter = rect & near_above
        if inter.width <= 0 or inter.height <= 0:
            continue
        horizontal_overlap = inter.width / max(1.0, min(rect.width, near_above.width))
        if horizontal_overlap < 0.20:
            continue
        gap = caption_bbox.y0 - rect.y1
        if 0 <= gap <= 90.0:
            above_gaps.append(gap)

    if not above_gaps:
        return direction
    if is_bare_caption:
        return "above"

    nearest_next_caption_gap = min(next_caption_gaps)
    search_bottom = min(
        page_rect.y1,
        caption_bbox.y1 + min(220.0, max(90.0, clip_height * 0.45)),
        caption_bbox.y1 + nearest_next_caption_gap - caption_gap,
    )
    near_below = create_rect(page_rect.x0, caption_bbox.y1 + caption_gap, page_rect.x1, search_bottom)
    below_gaps: List[float] = []
    if near_below.height > 1:
        for rect in list(image_rects) + list(vector_rects):
            inter = rect & near_below
            if inter.width <= 0 or inter.height <= 0:
                continue
            horizontal_overlap = inter.width / max(1.0, min(rect.width, near_below.width))
            if horizontal_overlap < 0.20:
                continue
            gap = rect.y0 - caption_bbox.y1
            if 0 <= gap <= near_below.height:
                below_gaps.append(gap)

    above_gap = min(above_gaps)
    below_gap = min(below_gaps) if below_gaps else None
    if above_gap <= 35.0 and (below_gap is None or below_gap >= above_gap + 12.0):
        return "above"
    return direction


def determine_direction(
    caption_bbox: "fitz.Rect",
    page_rect: "fitz.Rect",
    ident: str,
    *,
    global_anchor: Optional[str] = None,
    forced_below: Optional[set] = None,
    forced_above: Optional[set] = None,
    is_table: bool = False,
    page_position_heuristic: bool = True,
    local_evidence: Optional[Tuple[str, float]] = None,
) -> str:
    """
    确定单个图表的提取方向。

    优先级（局部优先策略）：
    1. 用户显式指定（forced_below/forced_above）
    2. 局部方向证据（local_evidence）置信度 >=0.5 直接采用
    3. 全局锚点 tie-break：局部证据弱或缺失时，优先于页面位置启发式
    4. 页面位置启发式（作为无 global_anchor 时的回退）
    5. 默认值（Figure: above, Table: below）

    修复说明：原先页面位置启发式为硬 return，会无条件覆盖 global_anchor，
    导致全文统计得到的强全局锚点对顶部/底部 caption 失效。现在 global_anchor
    作为真正的 tie-break，在局部证据不足时优先于页面位置启发式。

    Args:
        caption_bbox: Caption 边界框
        page_rect: 页面边界框
        ident: 图表编号
        global_anchor: 全局锚点方向（tie-break）
        forced_below: 强制 below 的编号集合
        forced_above: 强制 above 的编号集合
        is_table: 是否为表格
        page_position_heuristic: 是否使用页面位置启发式
        local_evidence: 局部方向证据 (direction, confidence)
            由 score_local_direction() 返回，如果不提供则不使用

    Returns:
        'above' | 'below'
    """
    forced_below = forced_below or set()
    forced_above = forced_above or set()

    # 1. 用户显式指定
    if ident in forced_below:
        return 'below'
    if ident in forced_above:
        return 'above'

    # 2. 局部方向证据（实际生效阈值为 0.5，见 docstring 第 2 条）
    if local_evidence is not None:
        local_dir, local_conf = local_evidence
        if local_conf >= 0.5:
            return local_dir

    # 3. 页面位置启发式（作为候选方向，不直接 return）
    heuristic_dir: Optional[str] = None
    if page_position_heuristic:
        if is_table:
            page_quarter = page_rect.height * 0.75
            if caption_bbox.y1 > page_rect.y0 + page_quarter:
                heuristic_dir = 'above'
        else:
            page_third = page_rect.height / 3
            if caption_bbox.y0 < page_rect.y0 + page_third:
                heuristic_dir = 'below'

    # 4. 全局锚点 tie-break：仅在局部证据缺失或极弱时优先于页面位置启发式
    if global_anchor:
        if local_evidence is None:
            return global_anchor
        _local_dir, local_conf = local_evidence
        if local_conf < 0.5:
            return global_anchor

    # 5. 应用页面位置启发式（无 global_anchor 或 global_anchor 为 None 时）
    if heuristic_dir is not None:
        return heuristic_dir

    # 6. 默认值
    return 'below' if is_table else 'above'


# ============================================================================
# 向后兼容别名
# ============================================================================

_compute_global_anchor = compute_global_anchor
_determine_direction = determine_direction
_score_direction_for_caption = score_direction_for_caption


# ============================================================================
# 模块导出
# ============================================================================

__all__ = [
    "compute_global_anchor",
    "determine_direction",
    "correct_bare_figure_caption_direction",
    "score_direction_for_caption",
    "score_local_direction",
    "compute_object_ratio",
]
