"""Recover captionless table pages using continuation markers and repeated ruled headers.

Only adjacent pages with the same column header and horizontal-rule extent are
linked. This is evidence-driven recovery, not a fixed page/asset exception.
"""
from __future__ import annotations

import os
import re
from typing import Any, List, Optional, Tuple

import fitz

from .assess import AssessmentInput, apply_assessment, assess_extraction, text_crosses_clip_boundary
from .extract_helpers import collect_text_lines
from .models import AttachmentRecord
from .output import get_unique_path

_CONTINUED = re.compile(r'^continued\s+on\s+(?:the\s+)?next\s+page[.\s]*$', re.I)


def _rules(page: Any, extent: Optional[Tuple[float, float]] = None) -> List[Any]:
    rules = []
    for drawing in page.get_drawings():
        rect = drawing['rect']
        if rect.height > 1.5 or rect.width < 0.35 * page.rect.width:
            continue
        if extent and max(abs(rect.x0-extent[0]), abs(rect.x1-extent[1])) > 2.0:
            continue
        rules.append(fitz.Rect(rect))
    return sorted(rules, key=lambda r: r.y0)


def _header(lines, top, bottom, left, right):
    cells = [(r, text.strip()) for r, _size, text in lines
             if text.strip() and r.y0 >= top-1 and r.y1 <= bottom+1
             and r.x0 >= left-2 and r.x1 <= right+2]
    return [(re.sub(r'\s+', ' ', text).casefold(), r.x0-left)
            for r, text in sorted(cells, key=lambda x: (round(x[0].y0/3), x[0].x0))]


def preceding_table_parts(doc: Any, record: AttachmentRecord):
    """Return [(zero-based page, bbox)] before a terminal captioned table page."""
    if record.kind != 'table' or not record.final_bbox or record.page < 2:
        return []
    clip = fitz.Rect(record.final_bbox)
    page = doc[record.page-1]
    rules = [r for r in _rules(page) if clip.y0-2 <= r.y0 <= clip.y1+2
             and abs(r.x0-clip.x0)<12 and abs(r.x1-clip.x1)<12]
    if len(rules)<3:
        return []
    first, second = rules[:2]
    extent = (first.x0, first.x1)
    header = _header(collect_text_lines(page.get_text('dict')), first.y0, second.y0, *extent)
    if len(header)<2:
        return []
    parts = []
    for pno in range(record.page-2, -1, -1):
        previous = doc[pno]
        lines = collect_text_lines(previous.get_text('dict'))
        markers = [r for r, _size, text in lines if _CONTINUED.fullmatch(text.strip())]
        if len(markers)!=1:
            break
        marker = markers[0]
        bands = [r for r in _rules(previous, extent) if r.y0 < marker.y0]
        start = None
        for upper, lower in zip(bands, bands[1:]):
            candidate = _header(lines, upper.y0, lower.y0, *extent)
            if len(candidate)==len(header) and all(
                a[0]==b[0] and abs(a[1]-b[1])<6 for a,b in zip(candidate,header)
            ):
                start = upper.y0
                break
        if start is None or len([r for r in bands if r.y0>=start])<3:
            break
        bottom = bands[-1].y0
        # The marker must actually follow this ruled table, not a distant object.
        if marker.y0-bottom > 30 or bottom-start < 40:
            break
        if any(re.match(r'^(?:Table|Figure)\s+\d+[.:|]', text.strip())
               for r,_size,text in lines if start<r.y0<bottom):
            break
        parts.append((pno, fitz.Rect(extent[0]-3,start-3,extent[1]+3,bottom+3) & previous.rect))
    return list(reversed(parts))


def recover_table_continuations(doc: Any, records: List[AttachmentRecord], out_dir: str,
                                *, dpi: int = 300, debug_visual: bool = False) -> None:
    known = {(r.kind,r.ident,r.page) for r in records}
    for anchor in list(records):
        parts = preceding_table_parts(doc, anchor)
        if not parts:
            continue
        first_page = parts[0][0]+1
        anchor.continued = True
        for pno, clip in parts:
            key = ('table',anchor.ident,pno+1)
            if key in known:
                continue
            path, _ = get_unique_path(os.path.join(out_dir,f'Table_{anchor.ident}_p{pno+1}_continued.png'))
            doc[pno].get_pixmap(dpi=dpi,clip=clip).save(path)
            debug = []
            if debug_visual:
                from .debug_visual import create_debug_stage, save_debug_visualization
                from .idents import stable_debug_number
                debug = save_debug_visualization(doc[pno],out_dir,stable_debug_number(anchor.ident),pno+1,
                    stages=[create_debug_stage('final',clip)],caption_rect=None,kind='table') or []
            record = AttachmentRecord(
                kind='table',ident=anchor.ident,page=pno+1,caption=anchor.caption,
                out_path=path,continued=(pno+1 != first_page),final_bbox=list(clip),
                content_bboxes=[list(clip)],source_signals=['table_continuation','repeated_header','horizontal_rules'],
                pairing_confidence=0.9,boundary_confidence=0.85,debug_artifacts=debug,
            )
            text_boxes = [r for r, _size, text in collect_text_lines(doc[pno].get_text('dict')) if text.strip()]
            records.append(apply_assessment(record, assess_extraction(AssessmentInput(
                kind='table', ident=anchor.ident, caption=anchor.caption,
                object_truncation=text_crosses_clip_boundary(list(clip), text_boxes, min_inside_height_ratio=0.5),
            ))))
            known.add(key)
    records.sort(key=lambda r:(r.num_key(),r.page))
