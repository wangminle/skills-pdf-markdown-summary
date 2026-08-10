#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A2/A3 缺陷回归：配对一对一、多框、逐页回退、质量检测、四态落盘。"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import fitz
import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPTS_DIR = os.path.join(PROJECT_ROOT, "skills", "pdf-markdown-summary", "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from lib.models import AttachmentRecord
from lib.pairing import pair_layout_regions, pair_page
from lib.pipeline import _match_records_to_candidates, run_refinement_pipeline
from lib.quality import (
    STATUS_ACCEPTED,
    STATUS_REJECTED,
    STATUS_REVIEW_REQUIRED,
    assess_quality,
    detect_truncation,
)
from lib.regions import LayoutResult, PageRegion, RegionBBox
from lib.refiners.figure import FigureRefiner
from lib.refiners.base import RefinementContext, RefinementResult


def test_assess_quality_honors_truncation_and_pollution() -> None:
    qa = assess_quality(
        final_bbox=[0, 0, 100, 80],
        candidate_bbox=[0, 0, 100, 100],
        text_pollution=True,
        truncation=True,
    )
    assert qa.truncation_detected is True
    assert qa.text_pollution_detected is True
    assert qa.status == STATUS_REJECTED
    assert "truncation_detected" in qa.warnings
    assert "text_pollution_detected" in qa.warnings


def test_detect_truncation_flags_cut_candidate_content() -> None:
    """精修框显著丢弃候选框内对象时，应判截断。"""
    candidate = [50.0, 50.0, 250.0, 250.0]
    final = [50.0, 50.0, 250.0, 140.0]
    object_rects = [
        fitz.Rect(60, 60, 240, 120),
        fitz.Rect(60, 160, 240, 240),
    ]
    truncated, reason = detect_truncation(
        final_bbox=final,
        candidate_bbox=candidate,
        object_rects=object_rects,
    )
    assert truncated, reason


def test_detect_truncation_ok_when_full_coverage() -> None:
    candidate = [50.0, 50.0, 250.0, 250.0]
    final = [45.0, 45.0, 255.0, 255.0]
    object_rects = [fitz.Rect(60, 60, 240, 240)]
    truncated, reason = detect_truncation(
        final_bbox=final,
        candidate_bbox=candidate,
        object_rects=object_rects,
    )
    assert not truncated, reason


def test_figure_refiner_uses_real_quality_signals(monkeypatch: pytest.MonkeyPatch) -> None:
    """FigureRefiner 不得硬编码 truncation=False / 假 text_pollution。"""
    captured: Dict[str, Any] = {}

    def fake_assess(**kwargs: Any):
        captured.update(kwargs)
        return assess_quality(**kwargs)

    monkeypatch.setattr("lib.refiners.figure.assess_quality", fake_assess)

    class _PassStep:
        name = "pass"

        def apply(self, current_bbox, ctx):
            return RefinementResult(bbox=list(current_bbox), step_name=self.name, moved=False)

    refiner = FigureRefiner(steps=[_PassStep()])
    text_lines = []
    for i in range(8):
        y0 = 70 + i * 35
        text_lines.append((
            fitz.Rect(60, y0, 540, y0 + 12),
            10.0,
            "This is a long body paragraph line that spans most of the extracted clip width.",
        ))
    ctx = RefinementContext(
        candidate_bbox=[50.0, 50.0, 550.0, 500.0],
        text_lines=text_lines,
        image_rects=[fitz.Rect(60, 300, 500, 480)],
        vector_rects=[],
    )
    result = refiner.refine(ctx)
    assert "text_pollution" in captured
    assert "truncation" in captured
    assert captured["text_pollution"] is True
    assert result.quality is not None
    assert result.quality.text_pollution_detected is True


def test_match_records_one_to_one_no_duplicate_candidate() -> None:
    """A3 匹配必须一对一：两个 record 不能绑到同一候选。"""
    records = [
        AttachmentRecord(
            kind="figure", ident="1", page=1, caption="F1", out_path="a.png",
            final_bbox=[0, 0, 100, 100],
        ),
        AttachmentRecord(
            kind="figure", ident="2", page=1, caption="F2", out_path="b.png",
            final_bbox=[10, 10, 110, 110],
        ),
    ]

    @dataclass
    class _Cand:
        kind: str = "figure"
        content_bboxes: List[List[float]] = field(default_factory=list)
        caption_bbox: Optional[List[float]] = None

    @dataclass
    class _PR:
        page: int = 1
        pairs: List = field(default_factory=list)

    shared = [0.0, 0.0, 100.0, 100.0]
    other = [200.0, 200.0, 300.0, 300.0]
    c1 = _Cand(content_bboxes=[shared], caption_bbox=[0, 110, 100, 130])
    c2 = _Cand(content_bboxes=[shared], caption_bbox=[0, 110, 100, 130])
    c3 = _Cand(content_bboxes=[other], caption_bbox=[200, 310, 300, 330])
    pr = _PR(pairs=[(c1, [c1]), (c2, [c2]), (c3, [c3])])

    mapping = _match_records_to_candidates(records, {1: pr})
    assert len(mapping) >= 1
    if len(mapping) == 2:
        def _union_key(val):
            frames = _extract_frames(val)
            u = _union(frames)
            return tuple(round(v, 2) for v in u)

        b0 = _union_key(mapping[0])
        b1 = _union_key(mapping[1])
        assert b0 != b1, f"duplicate candidate binding: {mapping}"


def test_match_records_preserves_multi_content_bboxes() -> None:
    """匹配结果应保留多 panel content_bboxes，而不是只给 union。"""
    records = [
        AttachmentRecord(
            kind="figure", ident="1", page=1, caption="F1", out_path="a.png",
            final_bbox=[0, 0, 210, 100],
            caption_bbox=[0, 110, 210, 130],
        ),
    ]

    @dataclass
    class _Cand:
        kind: str = "figure"
        content_bboxes: List[List[float]] = field(default_factory=list)
        caption_bbox: Optional[List[float]] = None

    @dataclass
    class _PR:
        page: int = 1
        pairs: List = field(default_factory=list)

    frames = [[0.0, 0.0, 100.0, 100.0], [110.0, 0.0, 210.0, 100.0]]
    cand = _Cand(content_bboxes=frames, caption_bbox=[0, 110, 210, 130])
    pr = _PR(pairs=[(cand, [cand])])
    mapping = _match_records_to_candidates(records, {1: pr})
    assert 0 in mapping
    bboxes = _extract_frames(mapping[0])
    assert len(bboxes) == 2, f"expected 2 frames, got {bboxes}"


def test_multi_frame_does_not_swallow_neighbor_with_own_caption() -> None:
    """两图两 caption 且相邻时，不得并成 multi-frame 吞掉第二张。"""
    caps = [
        RegionBBox(0, 210, 100, 230, kind="caption"),
        RegionBBox(120, 210, 220, 230, kind="caption"),
    ]
    contents = [
        RegionBBox(0, 0, 100, 200, kind="figure"),
        RegionBBox(120, 0, 220, 200, kind="figure"),
    ]
    result = pair_page(page=1, captions=caps, contents=contents, kind="figure")
    assert len(result.pairs) == 2, (
        f"pairs={len(result.pairs)}, frames={[p[0].content_bboxes for p in result.pairs]}, "
        f"orphan_caps={len(result.orphan_captions)}"
    )
    assert all(len(p[0].content_bboxes) == 1 for p in result.pairs)
    assert len(result.orphan_captions) == 0


def test_external_caption_per_page_fallback_to_layout() -> None:
    """外部 caption 只覆盖部分页时，缺页应回退 Layout caption。"""
    lr = LayoutResult(pdf_path="", pdf_hash="", backend="test", backend_version="0")
    p1 = PageRegion(page=1)
    p1.figure_regions = [RegionBBox(50, 50, 200, 200, kind="figure")]
    p1.caption_regions = [RegionBBox(50, 210, 200, 230, kind="caption")]
    p2 = PageRegion(page=2)
    p2.figure_regions = [RegionBBox(50, 50, 200, 200, kind="figure")]
    p2.caption_regions = [RegionBBox(50, 210, 200, 230, kind="caption")]
    lr.pages = {1: p1, 2: p2}

    external = [
        (1, "Figure 1", [50.0, 210.0, 200.0, 230.0], "figure"),
    ]
    results = pair_layout_regions(lr, caption_candidates=external)
    assert 1 in results and len(results[1].pairs) == 1
    assert 2 in results and len(results[2].pairs) == 1, (
        f"page2 pairs={len(results.get(2).pairs) if 2 in results else 0}, "
        f"orphan_contents={len(results.get(2).orphan_contents) if 2 in results else 'missing'}"
    )


def test_pipeline_writes_four_state_on_non_acceptable(
    monkeypatch: pytest.MonkeyPatch, tmp_path,
) -> None:
    """review_required/rejected 时必须写回 status/warnings/review_required。"""
    from lib.quality import QualityAssessment

    records = [
        AttachmentRecord(
            kind="figure",
            ident="1",
            page=1,
            caption="Figure 1",
            out_path="fig.png",
            final_bbox=[10.0, 10.0, 200.0, 200.0],
            caption_bbox=[10.0, 210.0, 200.0, 230.0],
            status=STATUS_ACCEPTED,
            review_required=False,
        ),
    ]
    png = tmp_path / "fig.png"
    png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)

    @dataclass
    class _Cand:
        kind: str = "figure"
        content_bboxes: List[List[float]] = field(
            default_factory=lambda: [[10.0, 10.0, 200.0, 200.0]]
        )
        caption_bbox: Optional[List[float]] = None

    @dataclass
    class _PR:
        page: int = 1
        pairs: List = field(default_factory=list)

    cand = _Cand(caption_bbox=[10.0, 210.0, 200.0, 230.0])
    pairing = {1: _PR(pairs=[(cand, [cand])])}

    class _FakeRefiner:
        def refine(self, ctx):
            qa = QualityAssessment(
                confidence=0.2,
                status=STATUS_REVIEW_REQUIRED,
                warnings=["text_pollution_detected"],
                text_pollution_detected=True,
            )
            return RefinementResult(
                bbox=[10.0, 10.0, 200.0, 200.0],
                step_name="fake",
                quality=qa,
                notes="fake",
            )

    monkeypatch.setattr("lib.refiners.FigureRefiner", _FakeRefiner)
    monkeypatch.setattr("lib.refiners.TableRefiner", _FakeRefiner)

    pdf_path = tmp_path / "t.pdf"
    doc = fitz.open()
    doc.new_page(width=300, height=400)
    doc.save(pdf_path)
    doc.close()

    report = run_refinement_pipeline(
        records=records,
        pairing_results=pairing,
        pdf_path=str(pdf_path),
        out_dir=str(tmp_path),
        dpi=72,
    )
    assert report.total_records == 1
    rec = records[0]
    assert rec.status == STATUS_REVIEW_REQUIRED, rec.status
    assert rec.review_required is True
    assert "text_pollution_detected" in rec.warnings


def _extract_frames(val: Any) -> List[List[float]]:
    if isinstance(val, dict):
        frames = val.get("content_bboxes") or []
        if frames:
            return [list(f) for f in frames]
        bbox = val.get("bbox") or val.get("candidate_bbox")
        return [list(bbox)] if bbox else []
    if isinstance(val, (list, tuple)) and val and isinstance(val[0], (list, tuple)):
        return [list(f) for f in val]
    if isinstance(val, (list, tuple)) and len(val) == 4:
        return [list(val)]
    return []


def _union(frames: List[List[float]]) -> List[float]:
    return [
        min(b[0] for b in frames),
        min(b[1] for b in frames),
        max(b[2] for b in frames),
        max(b[3] for b in frames),
    ]
