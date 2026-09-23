#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Caption-path extraction status, completeness signals, and inventory reconcile."""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from .caption_detection import (
    is_caption_anchor_candidate,
    is_caption_reference,
)
from .idents import FIGURE_LINE_RE, TABLE_LINE_RE
from .models import AttachmentRecord, CaptionCandidate, CaptionIndex
from .quality import (
    STATUS_ACCEPTED,
    STATUS_ACCEPTED_WITH_MARGIN,
    STATUS_REJECTED,
    STATUS_REVIEW_REQUIRED,
)

_MARKDOWN_INSERTABLE = {STATUS_ACCEPTED, STATUS_ACCEPTED_WITH_MARGIN}


@dataclass
class AssessmentInput:
    kind: str = "figure"
    ident: str = ""
    caption: str = ""
    caption_score: float = 100.0
    is_body_citation: bool = False
    text_pollution: bool = False
    object_truncation: bool = False
    table_band_open: bool = False
    header_clipped: bool = False
    far_side_body: bool = False
    duplicate_png: bool = False
    weak_anchor: bool = False
    extra_whitespace: bool = False


@dataclass
class AssessmentResult:
    status: str
    warnings: List[str] = field(default_factory=list)
    pairing_confidence: Optional[float] = None
    boundary_confidence: Optional[float] = None
    review_required: bool = False


@dataclass
class ExpectedCaption:
    kind: str
    ident: str
    page: int
    text: str
    score: float
    candidate: CaptionCandidate


@dataclass
class InventoryReport:
    expected: List[ExpectedCaption]
    missing: List[ExpectedCaption]
    unexpected: List[AttachmentRecord]
    sequence_gaps: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "expected": len(self.expected),
            "exported": None,
            "missing": [
                {"type": item.kind, "id": item.ident, "page": item.page, "caption": item.text, "score": item.score}
                for item in self.missing
            ],
            "unexpected": [
                {"type": rec.kind, "id": rec.ident, "page": rec.page, "caption": rec.caption}
                for rec in self.unexpected
            ],
            "sequence_gaps": list(self.sequence_gaps),
        }


def markdown_insertable(
    status: Optional[str],
    *,
    review_required: Optional[bool] = None,
    warnings: Optional[Sequence[str]] = None,
) -> bool:
    """Whether an index entry may be inserted into Markdown.

    主链记录一定带 status。缺 status 的只有旧版 index、手工合并等外部条目，
    这类条目未经评估，此时改用 review_required / warnings 兜底，
    避免「没评估过」被当成「评估通过」。
    """
    if status:
        return status in _MARKDOWN_INSERTABLE
    return not (review_required or warnings)


def assess_extraction(inp: AssessmentInput) -> AssessmentResult:
    warnings: List[str] = []
    status = STATUS_ACCEPTED

    if inp.is_body_citation:
        warnings.append("body_citation")
        status = STATUS_REJECTED
    elif inp.text_pollution:
        warnings.append("text_pollution")
        status = STATUS_REJECTED
    else:
        if inp.duplicate_png:
            warnings.append("duplicate_png")
            status = STATUS_REVIEW_REQUIRED
        if inp.object_truncation:
            warnings.append("object_truncation")
            status = STATUS_REVIEW_REQUIRED
        if inp.table_band_open:
            warnings.append("table_band_open")
            status = STATUS_REVIEW_REQUIRED
        if inp.header_clipped:
            warnings.append("header_clipped")
            status = STATUS_REVIEW_REQUIRED
        if inp.far_side_body:
            warnings.append("far_side_body")
            status = STATUS_REVIEW_REQUIRED
        if inp.weak_anchor or inp.caption_score < 25.0:
            warnings.append("weak_anchor")
            status = STATUS_REVIEW_REQUIRED

    pairing = 0.9
    if inp.weak_anchor or inp.caption_score < 25.0:
        pairing = 0.45
    if inp.is_body_citation:
        pairing = 0.1

    boundary = 0.85
    if inp.object_truncation or inp.table_band_open or inp.header_clipped:
        boundary = 0.4
    if inp.text_pollution or inp.far_side_body:
        boundary = 0.25
    if inp.extra_whitespace:
        boundary = min(boundary, 0.75)

    return AssessmentResult(
        status=status,
        warnings=warnings,
        pairing_confidence=round(pairing, 3),
        boundary_confidence=round(boundary, 3),
        review_required=status in (STATUS_REVIEW_REQUIRED, STATUS_REJECTED),
    )


def apply_assessment(record: AttachmentRecord, result: AssessmentResult) -> AttachmentRecord:
    record.status = result.status
    record.review_required = result.review_required
    record.warnings = list(result.warnings)
    record.pairing_confidence = result.pairing_confidence
    record.boundary_confidence = result.boundary_confidence
    return record


def expected_captions_from_index(index: CaptionIndex) -> List[ExpectedCaption]:
    expected: List[ExpectedCaption] = []
    for candidates in (index.candidates or {}).values():
        by_page: Dict[int, List[CaptionCandidate]] = {}
        for cand in candidates:
            by_page.setdefault(int(cand.page), []).append(cand)
        for page, group in by_page.items():
            valid = [cand for cand in group
                     if is_caption_anchor_candidate(cand.text)
                     and not is_caption_reference(cand.text, cand.block or {},
                         FIGURE_LINE_RE if cand.kind == "figure" else TABLE_LINE_RE)]
            if not valid:
                continue
            best = max(valid, key=lambda item: item.score)
            expected.append(
                ExpectedCaption(
                    kind=best.kind,
                    ident=str(best.number),
                    page=int(best.page) + 1,
                    text=best.text,
                    score=float(best.score),
                    candidate=best,
                )
            )
    expected.sort(key=lambda item: (item.kind, item.page, item.ident))
    return expected


def _record_key(kind: str, ident: str, page: int) -> Tuple[str, str, int]:
    return (kind, str(ident), int(page))


def reconcile_inventory(
    expected: Sequence[ExpectedCaption],
    records: Sequence[AttachmentRecord],
    *, verify_files: bool = False,
) -> InventoryReport:
    exported_keys = {
        _record_key(rec.kind, rec.ident, rec.page) for rec in records
        if rec.out_path and (not verify_files or os.path.isfile(rec.out_path))
    }
    expected_keys = {_record_key(item.kind, item.ident, item.page) for item in expected}
    missing = [item for item in expected if _record_key(item.kind, item.ident, item.page) not in exported_keys]
    unexpected = [
        rec
        for rec in records
        if _record_key(rec.kind, rec.ident, rec.page) not in expected_keys
        and "table_continuation" not in rec.source_signals
    ]
    gaps = _sequence_gaps(expected)
    report = InventoryReport(
        expected=list(expected),
        missing=missing,
        unexpected=unexpected,
        sequence_gaps=gaps,
    )
    return report


def _sequence_gaps(expected: Sequence[ExpectedCaption]) -> List[str]:
    gaps: List[str] = []
    for kind in ("figure", "table"):
        numbers: List[int] = []
        for item in expected:
            if item.kind != kind:
                continue
            try:
                numbers.append(int(item.ident))
            except ValueError:
                continue
        unique = sorted(set(numbers))
        if len(unique) < 2:
            continue
        for value in range(unique[0], unique[-1]):
            if value not in set(unique):
                gaps.append(f"{kind}_{value}")
    return gaps


def _file_digest(path: str) -> Optional[str]:
    if not path or not os.path.isfile(path):
        return None
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def mark_duplicate_png_records(records: Sequence[AttachmentRecord]) -> None:
    by_page: Dict[Tuple[str, int], List[AttachmentRecord]] = {}
    for rec in records:
        by_page.setdefault((rec.kind, int(rec.page)), []).append(rec)
    for group in by_page.values():
        if len(group) < 2:
            continue
        hashes: Dict[str, List[AttachmentRecord]] = {}
        for rec in group:
            digest = _file_digest(rec.out_path)
            if not digest:
                continue
            hashes.setdefault(digest, []).append(rec)
        for shared in hashes.values():
            if len(shared) < 2:
                continue
            for rec in shared:
                if "duplicate_png" not in rec.warnings:
                    rec.warnings.append("duplicate_png")
                rec.status = STATUS_REVIEW_REQUIRED
                rec.review_required = True


def apply_unexpected_rejects(report: InventoryReport) -> None:
    from .caption_detection import is_likely_reference_context

    for rec in report.unexpected:
        caption = rec.caption or ""
        if is_caption_anchor_candidate(caption):
            continue
        if not is_likely_reference_context(caption):
            continue
        if rec.status == STATUS_REJECTED:
            continue
        if "unexpected_caption" not in rec.warnings:
            rec.warnings.append("unexpected_caption")
        rec.status = STATUS_REJECTED
        rec.review_required = True


def _outside_bands(
    obj: Tuple[float, float, float, float],
    final: Tuple[float, float, float, float],
    *,
    min_thickness: float = 2.0,
) -> List[Tuple[float, float, float, float]]:
    """把对象框落在 final 之外的部分拆成若干矩形条带。

    比 min_thickness 更薄的条带丢弃：与几何判定的 2pt 容差一致，避免仅擦过
    边界的细线被当成被裁掉的内容。
    """
    ox0, oy0, ox1, oy1 = obj
    fx0, fy0, fx1, fy1 = final
    if min(ox1, fx1) <= max(ox0, fx0) or min(oy1, fy1) <= max(oy0, fy0):
        return [obj]
    bands: List[Tuple[float, float, float, float]] = []
    if oy0 < fy0:
        bands.append((ox0, oy0, ox1, min(oy1, fy0)))
    if oy1 > fy1:
        bands.append((ox0, max(oy0, fy1), ox1, oy1))
    mid_y0, mid_y1 = max(oy0, fy0), min(oy1, fy1)
    if ox0 < fx0:
        bands.append((ox0, mid_y0, min(ox1, fx0), mid_y1))
    if ox1 > fx1:
        bands.append((max(ox0, fx1), mid_y0, ox1, mid_y1))
    return [
        b for b in bands
        if b[2] - b[0] > min_thickness and b[3] - b[1] > min_thickness
    ]


def objects_truncated_on_far_side(
    final_bbox: Sequence[float],
    search_bbox: Sequence[float],
    object_bboxes: Iterable[Sequence[float]],
    direction: str,
    *,
    min_area: float = 400.0,
    min_outside_height: float = 24.0,
    max_detached_gap: float = 12.0,
    ink_probe: Optional[Callable[[Sequence[float]], bool]] = None,
) -> bool:
    """判断是否有对象被裁剪框切断。

    对象框取自绘图路径与位图块，二者都系统性大于可见范围：路径外框包含被
    clip path 裁掉的部分，位图外框包含白边。传入 ink_probe 后，只有框外部分
    确实渲染出墨迹才判为截断；不传则沿用纯几何判定。

    与裁剪框完全不相交的对象只在贴近边界（间距不超过 max_detached_gap）时才
    可能是被整块切掉的同一幅内容，更远的属于同页另一个资产。

    历史名称 far_side 仅描述完全分离对象的搜索方向：部分相交对象在任意侧
    （包括题注侧）丢失可见内容均告警；完全分离的题注侧对象不计入。
    min_area 默认400平方点，低于此面积的对象不参与该几何检查；细小文字
    的截断由独立 text_crosses_clip_boundary 检查，微小图形仍属检测盲区。
    """
    if len(final_bbox) < 4 or len(search_bbox) < 4:
        return False
    fx0, fy0, fx1, fy1 = (float(v) for v in final_bbox[:4])
    sx0, sy0, sx1, sy1 = (float(v) for v in search_bbox[:4])

    def lost_outside(obj: Tuple[float, float, float, float]) -> bool:
        if ink_probe is None:
            return True
        return any(ink_probe(b) for b in _outside_bands(obj, (fx0, fy0, fx1, fy1)))

    for obj in object_bboxes:
        if len(obj) < 4:
            continue
        ox0, oy0, ox1, oy1 = (float(v) for v in obj[:4])
        inter_s_w = max(0.0, min(ox1, sx1) - max(ox0, sx0))
        inter_s_h = max(0.0, min(oy1, sy1) - max(oy0, sy0))
        if inter_s_w <= 0 or inter_s_h <= 0:
            continue
        area = max(0.0, ox1 - ox0) * max(0.0, oy1 - oy0)
        if area < min_area:
            continue
        inter_f_w = max(0.0, min(ox1, fx1) - max(ox0, fx0))
        inter_f_h = max(0.0, min(oy1, fy1) - max(oy0, fy0))
        # 相交并不等于完整。之前45%覆盖阈值会把裁掉半幅图判为通过。
        if (ox0 >= fx0-1.0 and oy0 >= fy0-1.0
                and ox1 <= fx1+1.0 and oy1 <= fy1+1.0):
            continue
        if inter_f_w > 0 and inter_f_h > 0:
            lost_fraction = 1.0 - inter_f_w * inter_f_h / max(1.0, area)
            if lost_fraction > 0.02 and max(
                fx0-ox0, fy0-oy0, ox1-fx1, oy1-fy1
            ) > 2.0 and lost_outside((ox0, oy0, ox1, oy1)):
                return True
        if direction == "below" and oy1 <= fy0 + 1.0:
            continue
        if direction == "above" and oy0 >= fy1 - 1.0:
            continue
        if inter_f_w <= 0 or inter_f_h <= 0:
            gap = max(fy0 - oy1, oy0 - fy1, fx0 - ox1, ox0 - fx1)
            if gap > max_detached_gap:
                continue
        outside_h = inter_s_h if inter_f_h <= 0 else max(0.0, (oy1 - oy0) - inter_f_h)
        if outside_h >= min_outside_height and lost_outside((ox0, oy0, ox1, oy1)):
            return True
    return False


def text_crosses_clip_boundary(
    final_bbox, text_bboxes, *, tolerance=1.0, min_inside_height_ratio=0.0
) -> bool:
    """Detect partially clipped glyph boxes; outside prose is not figure evidence.

    min_inside_height_ratio 要求文本行落在框内的高度占比达到该比例才算被裁，
    用于排除只擦到上下边缘的邻行（表格路径的行间边界本就贴着相邻行）。
    """
    fx0,fy0,fx1,fy1 = final_bbox
    for x0,y0,x1,y1 in text_bboxes:
        width = min(x1,fx1)-max(x0,fx0)
        height = min(y1,fy1)-max(y0,fy0)
        if width <= 0 or height <= 0:
            continue
        if height < min_inside_height_ratio * max(1e-6, y1 - y0):
            continue
        if max(fx0-x0,fy0-y0,x1-fx1,y1-fy1)>tolerance:
            return True
    return False


_CAPTION_SAFE = re.compile(r"[^\w]+")


def select_index_candidate(
    index: CaptionIndex,
    kind: str,
    ident: str,
    page: int,
    *,
    min_keep_score: float = 25.0,
) -> Tuple[Optional[CaptionCandidate], bool]:
    """Return (candidate, weak_anchor). Explicit low-score captions are kept for review."""
    best = index.get_best_for_page(kind, ident, page, min_score=min_keep_score)
    if best is not None:
        return best, False
    best = index.get_best_for_page(kind, ident, page, min_score=0.0)
    if best is None:
        return None, False
    if is_caption_anchor_candidate(best.text):
        return best, True
    return None, False


def finalize_caption_inventory(
    records: List[AttachmentRecord],
    pdf_path: str,
    out_dir: str,
    *,
    dpi: int = 300,
) -> Dict[str, Any]:
    """Mark unexpected/duplicates, crop missing explicit captions, return inventory summary."""
    try:
        import fitz
    except ImportError:
        return {}

    from .caption_detection import build_caption_index

    doc = fitz.open(pdf_path)
    try:
        index = build_caption_index(doc)
        expected = expected_captions_from_index(index)
        report = reconcile_inventory(expected, records, verify_files=True)
        apply_unexpected_rejects(report)
        for item in report.missing:
            page = doc[item.candidate.page]
            gap_record = render_inventory_gap(page, item, out_dir, dpi=dpi)
            if gap_record is None:
                records.append(
                    AttachmentRecord(
                        kind=item.kind,
                        ident=item.ident,
                        page=item.page,
                        caption=item.text,
                        out_path="",
                        source_signals=["inventory"],
                        warnings=["inventory_gap_unclippable"],
                        review_required=True,
                        status=STATUS_REJECTED,
                    )
                )
            else:
                records.append(gap_record)
        mark_duplicate_png_records(records)
        final_report = reconcile_inventory(expected, records, verify_files=True)
        payload = final_report.to_dict()
        payload["exported"] = sum(bool(rec.out_path) and os.path.isfile(rec.out_path) for rec in records)
        payload["inferred_continuations"] = [
            {"type": rec.kind, "id": rec.ident, "page": rec.page}
            for rec in records if "table_continuation" in rec.source_signals
        ]
        payload["review_required_count"] = sum(rec.review_required for rec in records)
        payload["missing_count"] = len(report.missing)
        payload["unexpected_count"] = len(report.unexpected)
        return payload
    finally:
        doc.close()


def gap_clip_from_caption(caption_rect: Any, page_rect: Any, *, height: float = 280.0) -> Any:
    y0 = min(page_rect.y1 - 8.0, caption_rect.y1 + 2.0)
    y1 = min(page_rect.y1, y0 + height)
    if y1 - y0 < 24.0:
        y0 = max(page_rect.y0, caption_rect.y0 - height)
        y1 = max(page_rect.y0 + 8.0, caption_rect.y0 - 2.0)
    x0 = max(page_rect.x0, min(caption_rect.x0 - 12.0, page_rect.x0 + 8.0))
    x1 = min(page_rect.x1, max(caption_rect.x1 + 12.0, page_rect.x1 - 8.0))
    return type(caption_rect)(x0, y0, x1, y1)


def render_inventory_gap(
    page: Any,
    expected: ExpectedCaption,
    out_dir: str,
    *,
    dpi: int = 300,
) -> Optional[AttachmentRecord]:
    try:
        import fitz
    except ImportError:
        return None
    caption_rect = expected.candidate.rect
    page_rect = page.rect
    clip = gap_clip_from_caption(caption_rect, page_rect)
    os.makedirs(out_dir, exist_ok=True)
    safe = _CAPTION_SAFE.sub("_", expected.text)[:48].strip("_") or expected.ident
    filename = f"{expected.kind.title()}_{expected.ident}_inventory_gap_{safe}.png"
    out_path = os.path.join(out_dir, filename)
    try:
        pix = page.get_pixmap(dpi=dpi, clip=clip)
        pix.save(out_path)
    except Exception:
        return None
    record = AttachmentRecord(
        kind=expected.kind,
        ident=expected.ident,
        page=expected.page,
        caption=expected.text,
        out_path=out_path,
        final_bbox=[clip.x0, clip.y0, clip.x1, clip.y1],
        caption_bbox=[caption_rect.x0, caption_rect.y0, caption_rect.x1, caption_rect.y1],
        content_bboxes=[[clip.x0, clip.y0, clip.x1, clip.y1]],
        source_signals=["inventory"],
        warnings=["inventory_gap"],
        review_required=True,
        status=STATUS_REVIEW_REQUIRED,
        pairing_confidence=round(min(1.0, expected.score / 100.0), 3),
        boundary_confidence=0.3,
    )
    return record
