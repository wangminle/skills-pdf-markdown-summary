#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A2/A3 缺陷回归：配对一对一、多框、逐页回退、质量检测、四态落盘。"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import fitz
import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPTS_DIR = os.path.join(PROJECT_ROOT, "skills", "pdf-markdown-summary", "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from lib.models import AttachmentRecord
from lib.pairing import pair_layout_regions, pair_page
from lib.pipeline import _match_records_to_candidates, _optimal_assignment, run_refinement_pipeline
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


def test_vertical_neighbors_are_not_merged_before_second_caption_pairs() -> None:
    """上下相距不超过 30pt 的两张独立图，不得在第二张题注配对前被并走。

    第一张题注夹在两图之间，到第二张图的边距小于等于第二张题注自己的边距，
    「另一题注更近」判据失效。第二张图仍属于第二张题注（它是该题注的最佳内容），
    分组前必须排除，否则只剩一条含两图的配对，第二张题注变成孤儿。
    """
    fig1 = RegionBBox(0, 0, 200, 180, kind="figure")
    cap1 = RegionBBox(0, 185, 200, 200, kind="caption")
    fig2 = RegionBBox(0, 205, 200, 400, kind="figure")
    cap2 = RegionBBox(0, 405, 200, 420, kind="caption")

    result = pair_page(page=1, captions=[cap1, cap2], contents=[fig1, fig2], kind="figure")

    assert len(result.pairs) == 2, (
        f"应各自配对，实际 {len(result.pairs)} 对 "
        f"frames={[p[0].content_bboxes for p in result.pairs]} "
        f"orphan_caps={len(result.orphan_captions)}"
    )
    assert len(result.orphan_captions) == 0
    assert all(len(p[0].content_bboxes) == 1 for p in result.pairs)

    # 单题注的上下两块仍是多框，不能被这条归属规则拆开
    panels = [
        RegionBBox(0, 0, 200, 100, kind="figure"),
        RegionBBox(0, 120, 200, 220, kind="figure"),
    ]
    only = RegionBBox(0, 230, 200, 248, kind="caption")
    merged = pair_page(page=1, captions=[only], contents=panels, kind="figure")
    assert len(merged.pairs) == 1
    assert len(merged.pairs[0][0].content_bboxes) == 2


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


def test_two_captions_two_contents_pair_one_to_one() -> None:
    """等距并列两图两题注必须各配各的，不得合并成多框。

    两个题注与两框的 edge_distance 完全相同时（左右并列典型形态），
    「没有更近的其他题注」判据失效：右题注与右框水平对齐显著更好，
    右框应留给右题注。合并会导致一张 PNG 裁进两个独立图、另一题注成孤儿。
    """
    left = RegionBBox.from_list([0, 0, 100, 200])
    right = RegionBBox.from_list([110, 0, 210, 200])
    cap_l = RegionBBox.from_list([0, 210, 150, 230])
    cap_r = RegionBBox.from_list([60, 210, 210, 230])

    result = pair_page(1, [cap_l, cap_r], [left, right], kind="figure")

    assert len(result.pairs) == 2, (
        f"应各自配对，实际 {len(result.pairs)} 对"
    )
    assert not result.orphan_captions
    assert not result.orphan_contents
    for cand, _ in result.pairs:
        assert len(cand.content_bboxes) == 1, cand.content_bboxes


def test_layout_caption_fallback_filters_by_kind() -> None:
    """外部候选缺某页某类型时，回退题注必须按类型筛。

    第 2 页只有 table 内容而 Layout 把该页题注标成 figure 类时，
    figure 题注不得配 table 内容；无法判别类型的通用 caption
    不受影响（否则单类型文档题注被误丢）。
    """
    pages = {
        1: PageRegion.from_regions(1, [
            RegionBBox.from_list([50, 100, 300, 300], kind="figure"),
            RegionBBox(50, 310, 300, 330, kind="caption", raw_class="figure-caption"),
        ]),
        2: PageRegion.from_regions(2, [
            RegionBBox.from_list([50, 100, 500, 400], kind="table"),
            RegionBBox(50, 410, 300, 430, kind="caption", raw_class="figure-caption"),
        ]),
    }
    layout = LayoutResult(
        pdf_path="x.pdf", pdf_hash="h", backend="pymupdf4llm",
        backend_version="1", pages=pages,
    )
    external = [(1, "Figure 1: foo", [50, 310, 300, 330], "figure")]

    results = pair_layout_regions(layout, caption_candidates=external)

    # 第 1 页正常配对
    p1_pairs = results.get(1).pairs if results.get(1) else []
    assert len(p1_pairs) == 1
    # 第 2 页 table 不得配 figure 题注
    p2 = results.get(2)
    if p2 is not None:
        for cand, _ in p2.pairs:
            assert cand.caption_bbox != [50.0, 410.0, 300.0, 430.0], (
                "figure-caption 不得配 table 内容"
            )
    # 通用 caption（raw_class="caption"）仍参与配对
    pages_generic = {
        3: PageRegion.from_regions(3, [
            RegionBBox.from_list([50, 100, 500, 400], kind="table"),
            RegionBBox(50, 410, 300, 430, kind="caption", raw_class="caption"),
        ]),
    }
    layout_generic = LayoutResult(
        pdf_path="x.pdf", pdf_hash="h", backend="pymupdf4llm",
        backend_version="1", pages=pages_generic,
    )
    results_generic = pair_layout_regions(layout_generic, caption_candidates=external)
    p3 = results_generic.get(3)
    assert p3 is not None and len(p3.pairs) == 1, "通用 caption 应参与配对"


def test_matching_prefers_maximum_cardinality() -> None:
    """一对一匹配先保数量再保 IoU。

    纯 IoU 贪心会让与两候选都重叠的记录先占用另一记录的唯一候选，
    后者失去精修机会。链式冲突与同框折叠一并覆盖。
    """
    @dataclass
    class _Cand:
        kind: str = "figure"
        page: int = 1
        content_bboxes: List[List[float]] = field(default_factory=list)
        caption_bbox: Optional[List[float]] = None
        sources: Dict[str, str] = field(default_factory=lambda: {"layout": ""})
        confidence: float = 1.0

    def _pr(bboxes):
        return SimpleNamespace(
            page=1,
            pairs=[(_Cand(content_bboxes=[b]), [_Cand(content_bboxes=[b])]) for b in bboxes],
            orphan_captions=[], orphan_contents=[],
        )

    # 评审场景：2 候选 2 记录，IoU 贪心只匹配 1 条
    recs = [
        SimpleNamespace(kind="figure", page=1, final_bbox=[5, 0, 105, 100]),
        SimpleNamespace(kind="figure", page=1, final_bbox=[0, 0, 80, 100]),
    ]
    mapping = _match_records_to_candidates(recs, {1: _pr([[0, 0, 100, 100], [65, 0, 165, 100]])})
    assert len(mapping) == 2, f"应匹配 2 条，实际 {len(mapping)}"

    # 链式冲突：3 记录 3 候选
    recs_chain = [
        SimpleNamespace(kind="figure", page=1, final_bbox=b)
        for b in ([0, 0, 100, 100], [10, 0, 110, 100], [20, 0, 120, 100])
    ]
    mapping_chain = _match_records_to_candidates(
        recs_chain,
        {1: _pr([[0, 0, 100, 100], [10, 0, 110, 100], [20, 0, 120, 100]])},
    )
    assert len(mapping_chain) == 3, f"链式冲突应全配，实际 {len(mapping_chain)}"

    # 同框折叠：bbox 相同的两个候选只能被一条记录占用
    recs_dup = [
        SimpleNamespace(kind="figure", page=1, final_bbox=[5, 0, 95, 100]),
        SimpleNamespace(kind="figure", page=1, final_bbox=[5, 0, 95, 100]),
    ]
    mapping_dup = _match_records_to_candidates(
        recs_dup, {1: _pr([[0, 0, 100, 100], [0, 0, 100, 100]])}
    )
    assert len(mapping_dup) == 1, f"同框候选只应配 1 条，实际 {len(mapping_dup)}"

    # 跨页同框互不冲突
    pr2 = SimpleNamespace(
        page=2,
        pairs=[(_Cand(page=2, content_bboxes=[[0, 0, 100, 100]]), [_Cand(page=2, content_bboxes=[[0, 0, 100, 100]])])],
        orphan_captions=[], orphan_contents=[],
    )
    recs_x = [
        SimpleNamespace(kind="figure", page=1, final_bbox=[5, 0, 95, 100]),
        SimpleNamespace(kind="figure", page=2, final_bbox=[5, 0, 95, 100]),
    ]
    mapping_x = _match_records_to_candidates(recs_x, {1: _pr([[0, 0, 100, 100]]), 2: pr2})
    assert len(mapping_x) == 2, f"跨页应各配各的，实际 {len(mapping_x)}"


def test_truncation_flags_text_cut_even_with_objects_kept() -> None:
    """对象全保留不能屏蔽候选覆盖率判据。

    候选里对象之外的文字（表格单元、图内标签）同样是候选内容：
    final 保留对象却裁掉 18% 文字带时必须报截断，
    否则该裁剪以 accepted_with_margin 静默放行。
    """
    cand = [0, 0, 100, 100]
    final = [0, 0, 100, 82]
    objs = [[10, 10, 90, 70]]

    flagged, reason = detect_truncation(final, cand, objs)
    assert flagged, "对象保留但候选文字被裁应报截断"
    assert "candidate_coverage" in reason

    # 正常路径不受影响
    assert not detect_truncation([0, 0, 100, 100], cand, objs)[0]
    assert not detect_truncation([0, 0, 100, 95], cand, objs)[0]  # 容差内
    assert detect_truncation([0, 0, 100, 50], cand, objs)[0]  # 对象被切仍报


def test_multi_frame_keeps_figure_whose_caption_is_layout_only() -> None:
    """题注池缺项不得让相邻独立图被并进上一张图的多框。

    外部候选来自有 legacy record 的题注；只在 Layout 检测到题注的图
    不在池里，归属判断看不到它自己的题注，就会把它的框并进上一张图
    （两张图合成一张截图，第二张图彻底丢失）。
    """
    fig1 = RegionBBox(72, 100, 520, 300, kind="figure", raw_class="picture")
    fig2 = RegionBBox(72, 320, 520, 520, kind="figure", raw_class="picture")
    cap1 = RegionBBox(72, 60, 400, 80, kind="caption", raw_class="figure-caption")
    cap2 = RegionBBox(72, 540, 400, 560, kind="caption", raw_class="figure-caption")
    page = PageRegion(
        page=1,
        regions=[fig1, fig2, cap1, cap2],
        figure_regions=[fig1, fig2],
        caption_regions=[cap1, cap2],
    )
    layout = LayoutResult(
        pdf_path="x.pdf", pdf_hash="h", backend="test",
        backend_version="1", pages={1: page},
    )

    # 外部候选只含 fig1 的题注（fig2 的题注只有 Layout 看到了）
    results = pair_layout_regions(layout, [(1, "Figure 1. A", [72, 60, 400, 80], "figure")])
    pairs = results[1].pairs
    assert len(pairs) == 1, f"fig1 只应有一条配对，实际 {len(pairs)}"
    cand = pairs[0][0]
    frames = [list(f) for f in cand.content_bboxes]
    assert frames == [[72, 100, 520, 300]], f"不得吞并相邻独立图：{frames}"
    orphans = [list(o.content_bboxes[0]) for o in results[1].orphan_contents if o.content_bboxes]
    assert [72, 320, 520, 520] in orphans, f"fig2 应作为孤儿内容保留：{orphans}"


def test_matching_uses_caption_identity_over_content_iou() -> None:
    """图注身份优先于内容框 IoU，避免两图互换绑定。

    相邻两图的 legacy 截图框漂移后，内容框 IoU 会互相倒挂：正确配对的
    IoU 低于阈值、错误配对的 IoU 更高，纯几何匹配会把两张图绑反——
    A3 随后用对方的候选框重渲染，等于截图串图。图注框是同一条图注，
    是不受漂移影响的身份证据。
    """
    cap1 = [72, 60, 400, 80]
    cap2 = [72, 540, 400, 560]

    @dataclass
    class _Cand:
        kind: str = "figure"
        page: int = 1
        content_bboxes: List[List[float]] = field(default_factory=list)
        caption_bbox: Optional[List[float]] = None

    def _entry(caption_bbox, content_bbox):
        c = _Cand(content_bboxes=[content_bbox], caption_bbox=caption_bbox)
        return (c, [c])

    pairing = {1: SimpleNamespace(page=1, pairs=[
        _entry(cap1, [72, 100, 520, 300]),   # 图1
        _entry(cap2, [72, 320, 520, 520]),   # 图2
    ])}
    records = [
        SimpleNamespace(kind="figure", page=1, ident="1", final_bbox=[72, 250, 520, 460],
                        caption_bbox=cap1),
        SimpleNamespace(kind="figure", page=1, ident="2", final_bbox=[72, 150, 520, 380],
                        caption_bbox=cap2),
    ]

    mapping = _match_records_to_candidates(records, pairing)
    assert len(mapping) == 2, f"两条记录都应匹配，实际 {len(mapping)}"
    assert mapping[0]["bbox"] == [72, 100, 520, 300], (
        f"记录 1 绑到了别人的候选框：{mapping[0]['bbox']}"
    )
    assert mapping[1]["bbox"] == [72, 320, 520, 520], (
        f"记录 2 绑到了别人的候选框：{mapping[1]['bbox']}"
    )


def test_optimal_assignment_stays_exact_above_twelve_frames() -> None:
    """13 个 frame 也必须保持最大匹配，不能退化成贪心丢掉可行边。"""
    rec_ids = list(range(13))
    frames = [("frame", i) for i in range(13)]
    edge_weight = {
        0: {frames[0]: (0.0, 1.0), frames[1]: (0.0, 0.9)},
        1: {frames[0]: (0.0, 0.8)},
    }
    for i in range(2, 13):
        edge_weight[i] = {frames[i]: (0.0, 0.7)}

    result = _optimal_assignment(rec_ids, frames, edge_weight)
    assert len(result) == 13, f"贪心降级只匹配了 {len(result)}/13"
    assert result[0] == frames[1]
    assert result[1] == frames[0]


def test_layout_caption_fallback_is_per_page() -> None:
    """外部候选为空页必须回退到 Layout 自带题注区域（按页判断）。"""
    cap = [72, 60, 400, 80]
    pages = {}
    for page_no in (1, 2):
        fig = RegionBBox(72, 100, 520, 300, kind="figure", raw_class="picture")
        c = RegionBBox(*cap, kind="caption", raw_class="figure-caption")
        pages[page_no] = PageRegion(
            page=page_no, regions=[fig, c],
            figure_regions=[fig], caption_regions=[c],
        )
    layout = LayoutResult(
        pdf_path="x.pdf", pdf_hash="h", backend="test",
        backend_version="1", pages=pages,
    )

    # 外部候选只覆盖第 2 页 → 第 1 页应回退，而不是产生空 caps
    results = pair_layout_regions(layout, [(2, "Figure 2. X", cap, "figure")])
    assert len(results.get(1, SimpleNamespace(pairs=[])).pairs) == 1, "第 1 页应回退到 Layout 题注"
    assert len(results.get(2, SimpleNamespace(pairs=[])).pairs) == 1, "第 2 页应使用外部候选"


def test_refinement_skips_no_refine_idents(tmp_path, monkeypatch) -> None:
    """A3 必须遵守 --no-refine 排除列表。

    legacy 阶段已按 --no-refine 跳过裁剪微调，A3 再按 Layout 候选覆盖同一
    id，等于无视用户显式排除（no_refine 同时作用于 figure 与 table）。
    """
    from lib.quality import QualityAssessment

    @dataclass
    class _Cand:
        kind: str = "figure"
        page: int = 1
        content_bboxes: List[List[float]] = field(default_factory=list)
        caption_bbox: Optional[List[float]] = None

    def _rec(ident: str, bbox, page: int = 1):
        return AttachmentRecord(
            kind="figure", ident=ident, page=page, caption=f"Figure {ident}",
            out_path=f"fig{ident}.png", final_bbox=list(bbox), caption_bbox=[10, 2, 200, 8],
            status=STATUS_ACCEPTED, review_required=False,
        )

    records = [_rec("1", [10, 20, 200, 200]), _rec("2", [10, 220, 200, 400])]

    def _entry(bbox):
        c = _Cand(content_bboxes=[list(bbox)])
        return (c, [c])

    pairing = {1: SimpleNamespace(page=1, pairs=[
        _entry([10, 20, 200, 200]), _entry([10, 220, 200, 400]),
    ])}

    class _FakeRefiner:
        def refine(self, ctx):
            qa = QualityAssessment(confidence=0.95, status=STATUS_ACCEPTED, warnings=[])
            return RefinementResult(
                bbox=list(ctx.candidate_bbox), step_name="fake", quality=qa, notes="fake",
            )

    monkeypatch.setattr("lib.refiners.FigureRefiner", _FakeRefiner)
    monkeypatch.setattr("lib.refiners.TableRefiner", _FakeRefiner)

    pdf_path = tmp_path / "t.pdf"
    doc = fitz.open()
    doc.new_page(width=300, height=500)
    doc.save(pdf_path)
    doc.close()

    report = run_refinement_pipeline(
        records=records,
        pairing_results=pairing,
        pdf_path=str(pdf_path),
        out_dir=str(tmp_path),
        dpi=72,
        skip_idents={"2"},
    )

    assert report.matched == 1, f"排除的 id 不应参与匹配，实际 matched={report.matched}"
    skipped = [r for r in report.records if r.ident == "2"]
    assert skipped and "no-refine" in skipped[0].reason, (
        f"排除的 id 应在报告中留痕：{[r.reason for r in report.records]}"
    )
    assert skipped[0].applied is False
    assert [r.ident for r in report.records if r.applied] == ["1"], (
        f"只有未排除的 id 可被精修：{[(r.ident, r.applied) for r in report.records]}"
    )


def test_matching_maximizes_iou_sum_within_cardinality() -> None:
    """最大基数内还须最大化 IoU 总和（评审#4 第 1 条）。

    Kuhn 增广只保证匹配数；增广找到的第一条可行路径不一定是总分最高的
    分配。实测反例：2 记录 2 候选，当前分配总 IoU 0.808，另一同基数
    分配 1.084。旧实现按边排序探试，会锁死在 0.808 的分配上；3 周旋转
    的改进（另一反例）是任何 2-opt 交换都够不到的局部最优，必须精确求解。
    """
    recs_bbox = [[87.0, 0, 178, 100], [131.0, 0, 219, 100]]
    cands_bbox = [[111.0, 0, 188, 100], [150.0, 0, 187, 100]]

    @dataclass
    class _Cand:
        kind: str = "figure"
        page: int = 1
        content_bboxes: List[List[float]] = field(default_factory=list)
        caption_bbox: Optional[List[float]] = None

    recs = [
        SimpleNamespace(kind="figure", page=1, final_bbox=b) for b in recs_bbox
    ]
    pairing = {1: SimpleNamespace(page=1, pairs=[
        (_Cand(content_bboxes=[b]), [_Cand(content_bboxes=[b])]) for b in cands_bbox
    ])}

    mapping = _match_records_to_candidates(recs, pairing)
    assert len(mapping) == 2

    def _iou(a, b):
        ix0, iy0 = max(a[0], b[0]), max(a[1], b[1])
        ix1, iy1 = min(a[2], b[2]), min(a[3], b[3])
        inter = max(0.0, ix1 - ix0) * max(0.0, iy1 - iy0)
        ua = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
        return inter / ua if ua > 0 else 0.0

    total = sum(_iou(recs_bbox[i], mapping[i]["bbox"]) for i in mapping)
    # 最优分配：rec0->[111,0,188,100](0.663) + rec1->[150,0,187,100](0.420) = 1.084
    assert total > 1.0, (
        f"IoU 总和应取最优分配（约 1.084），实际 {total:.3f}——"
        f"匹配锁死在次优分配上：{[mapping[i]['bbox'] for i in sorted(mapping)]}"
    )
    assert mapping[0]["bbox"] == [111.0, 0, 188.0, 100], mapping[0]["bbox"]
    assert mapping[1]["bbox"] == [150.0, 0, 187.0, 100], mapping[1]["bbox"]

    # 3 周旋转反例：2-opt 够不到的局部最优（评审实测 got 2.862 / best 2.892）
    recs3 = [[180.0, 0, 278, 100], [185.0, 0, 278, 100], [198.0, 0, 260, 100], [390.0, 0, 454, 100]]
    cands3 = [[183.0, 0, 304, 100], [208.0, 0, 279, 100], [149.0, 0, 253, 100], [392.0, 0, 460, 100]]
    recs_objs = [SimpleNamespace(kind="figure", page=1, final_bbox=b) for b in recs3]
    pairing3 = {1: SimpleNamespace(page=1, pairs=[
        (_Cand(content_bboxes=[b]), [_Cand(content_bboxes=[b])]) for b in cands3
    ])}
    m3 = _match_records_to_candidates(recs_objs, pairing3)
    assert len(m3) == 4, f"应全配，实际 {len(m3)}"
    total3 = sum(_iou(recs3[i], m3[i]["bbox"]) for i in m3)
    assert total3 > 2.88, (
        f"3 周旋转场景应取最优（2.892），实际 {total3:.4f}——"
        f"2-opt 局部最优陷阱：{[m3[i]['bbox'][0] for i in sorted(m3)]}"
    )


def test_untyped_caption_not_shared_across_kinds_on_mixed_page() -> None:
    """混合类型页的通用题注不得同时配 figure 与 table（评审#4 第 2 条）。

    raw_class="caption" 的题注在 figure/table 并存的页面上会被两个分组
    同时认领——同一条题注产出两张配对，等于「一条图注配两张图」。
    无法判别归属时保留为孤儿（原 review 要求），单类型页不受影响。
    """
    fig = RegionBBox(50, 100, 300, 300, kind="figure", raw_class="picture")
    tbl = RegionBBox(50, 350, 500, 550, kind="table", raw_class="table")
    cap = RegionBBox(50, 310, 300, 330, kind="caption", raw_class="caption")
    page = PageRegion.from_regions(1, [fig, tbl, cap])
    layout = LayoutResult(
        pdf_path="x.pdf", pdf_hash="h", backend="pymupdf4llm",
        backend_version="1", pages={1: page},
    )

    results = pair_layout_regions(layout)
    r = results.get(1)
    if r is not None:
        for cand, _ in r.pairs:
            assert cand.caption_bbox != [50.0, 310.0, 300.0, 330.0], (
                "混合页的通用题注不得参与任何类型配对："
                f"{(cand.kind, cand.caption_bbox)}"
            )

    # 单类型页（只有 table）行为不变：通用题注仍参与配对
    tbl_only = RegionBBox(50, 100, 500, 300, kind="table", raw_class="table")
    cap2 = RegionBBox(50, 310, 300, 330, kind="caption", raw_class="caption")
    page2 = PageRegion.from_regions(2, [tbl_only, cap2])
    layout2 = LayoutResult(
        pdf_path="x.pdf", pdf_hash="h", backend="pymupdf4llm",
        backend_version="1", pages={2: page2},
    )
    results2 = pair_layout_regions(layout2)
    p2 = results2.get(2)
    assert p2 is not None and len(p2.pairs) == 1, (
        "单类型页的通用题注应照常配对（否则单类型文档题注全变孤儿）"
    )


def test_confirmed_edge_not_evicted_by_geometric_match() -> None:
    """confirmed（图注身份一致）配对不可被普通 IoU 边挤占（P1 / BUG-112）。

    旧版 Kuhn 增广中，后处理的记录递归增广会把已 confirmed 的记录挤到
    自己的次优几何边上：R0 题注明确对应 C0，但 R1 的几何边挤占 C0 后，
    R0 被迫改配 C1，A3 随后按错误区域重渲染 = 截图串图。
    """
    cap0 = [0, 110, 100, 130]
    cap1 = [85, 110, 185, 130]

    @dataclass
    class _Cand:
        kind: str = "figure"
        page: int = 1
        content_bboxes: List[List[float]] = field(default_factory=list)
        caption_bbox: Optional[List[float]] = None

    def _entry(caption_bbox, content_bbox):
        c = _Cand(content_bboxes=[list(content_bbox)], caption_bbox=caption_bbox)
        return (c, [c])

    pairing = {1: SimpleNamespace(page=1, pairs=[
        _entry(cap0, [0, 0, 100, 100]),    # C0：R0 的题注
        _entry(cap1, [85, 0, 185, 100]),   # C1：几何上更贴近 R0 的截图框
    ])}
    records = [
        # R0 题注=cap0（confirmed->C0，内容 IoU 仅 0.111），
        # 但几何上 R0 与 C1 IoU=0.905 更高
        SimpleNamespace(kind="figure", page=1, ident="R0",
                        final_bbox=[80, 0, 180, 100], caption_bbox=cap0),
        # R1 无题注，唯一几何边指向 C0（IoU=0.75）
        SimpleNamespace(kind="figure", page=1, ident="R1",
                        final_bbox=[10, 0, 110, 100], caption_bbox=None),
    ]

    mapping = _match_records_to_candidates(records, pairing)
    assert mapping.get(0, {}).get("bbox") == [0, 0, 100, 100], (
        f"confirmed 配对被普通边挤占：R0 -> {mapping.get(0, {}).get('bbox')}"
    )


def test_matching_prefers_maximum_cardinality_over_single_high_iou() -> None:
    """匹配基数优先于单条高 IoU：可配 2 条时不得为高分单条放弃另一条。

    纯「IoU 总和最大」目标会选中 1 条 IoU=1.0 的分配而放弃可行但总分
    更低的 2 条分配（0.25+0.35=0.60 < 1.0），让 R1 彻底失去精修机会。
    正确目标是字典序：身份边数 > 匹配基数 > IoU 总和。
    """
    @dataclass
    class _Cand:
        kind: str = "figure"
        page: int = 1
        content_bboxes: List[List[float]] = field(default_factory=list)
        caption_bbox: Optional[List[float]] = None

    def _entry(content_bbox):
        c = _Cand(content_bboxes=[list(content_bbox)])
        return (c, [c])

    pairing = {1: SimpleNamespace(page=1, pairs=[
        _entry([0, 0, 100, 100]),    # C0
        _entry([60, 0, 160, 100]),   # C1
    ])}
    records = [
        # R0: C0 IoU=1.0、C1 IoU=0.25
        SimpleNamespace(kind="figure", page=1, ident="R0",
                        final_bbox=[0, 0, 100, 100], caption_bbox=None),
        # R1: C0 IoU=0.35、C1 无几何边
        SimpleNamespace(kind="figure", page=1, ident="R1",
                        final_bbox=[0, 0, 100, 35], caption_bbox=None),
    ]

    mapping = _match_records_to_candidates(records, pairing)
    assert len(mapping) == 2, (
        f"应最大基数匹配 2 条，实际 {len(mapping)} 条："
        f"{[mapping[i]['bbox'] for i in sorted(mapping)]}"
    )
