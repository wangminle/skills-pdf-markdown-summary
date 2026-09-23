#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""主链验收状态、完整性信号与题注对账。"""

from __future__ import annotations

import os
import sys

import fitz

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPTS_DIR = os.path.join(PROJECT_ROOT, "skills", "pdf-markdown-summary", "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from lib.assess import (
    AssessmentInput,
    apply_unexpected_rejects,
    assess_extraction,
    expected_captions_from_index,
    markdown_insertable,
    mark_duplicate_png_records,
    reconcile_inventory,
    select_index_candidate,
)
from lib.caption_detection import is_caption_anchor_candidate
from lib.models import AttachmentRecord, CaptionCandidate, CaptionIndex
from lib.quality import (
    STATUS_ACCEPTED,
    STATUS_ACCEPTED_WITH_MARGIN,
    STATUS_REJECTED,
    STATUS_REVIEW_REQUIRED,
)


def _candidate(kind: str, number: str, text: str, page: int = 0, score: float = 60.0) -> CaptionCandidate:
    return CaptionCandidate(
        rect=fitz.Rect(70.0, 100.0, 500.0, 112.0),
        text=text,
        number=number,
        kind=kind,
        page=page,
        block_idx=0,
        line_idx=0,
        spans=[{"text": text, "flags": 0, "size": 10.0}],
        block={"lines": [{"spans": [{"text": text}]}]},
        score=score,
    )


def _record(kind: str, ident: str, page: int, caption: str, status: str = STATUS_ACCEPTED) -> AttachmentRecord:
    return AttachmentRecord(
        kind=kind,
        ident=ident,
        page=page,
        caption=caption,
        out_path=f"{kind}_{ident}.png",
        status=status,
    )


def test_extra_whitespace_stays_accepted() -> None:
    result = assess_extraction(AssessmentInput(kind="figure", ident="1", extra_whitespace=True))
    assert result.status == STATUS_ACCEPTED
    assert result.review_required is False
    assert result.status != STATUS_ACCEPTED_WITH_MARGIN
    assert "small_relative_crop" not in result.warnings


def test_body_citation_is_rejected() -> None:
    result = assess_extraction(
        AssessmentInput(
            kind="table",
            ident="6",
            caption="Table 6. Also, we evaluate different modes",
            is_body_citation=True,
        )
    )
    assert result.status == STATUS_REJECTED
    assert "body_citation" in result.warnings


def test_title_or_paragraph_in_crop_is_rejected() -> None:
    result = assess_extraction(
        AssessmentInput(kind="figure", ident="1", text_pollution=True)
    )
    assert result.status == STATUS_REJECTED
    assert "text_pollution" in result.warnings


def test_object_truncation_is_review_required() -> None:
    result = assess_extraction(
        AssessmentInput(kind="figure", ident="13", object_truncation=True)
    )
    assert result.status == STATUS_REVIEW_REQUIRED
    assert "object_truncation" in result.warnings


def test_table_band_open_is_review_required() -> None:
    result = assess_extraction(
        AssessmentInput(kind="table", ident="2", table_band_open=True)
    )
    assert result.status == STATUS_REVIEW_REQUIRED
    assert "table_band_open" in result.warnings


def test_weak_anchor_is_review_required() -> None:
    result = assess_extraction(
        AssessmentInput(kind="figure", ident="9", caption_score=19.0, weak_anchor=True)
    )
    assert result.status == STATUS_REVIEW_REQUIRED
    assert "weak_anchor" in result.warnings


def test_expected_captions_keep_explicit_and_drop_body_citation() -> None:
    index = CaptionIndex(
        candidates={
            "figure_9": [
                _candidate(
                    "figure",
                    "9",
                    "Figure 9 | Results on autonomous cyber offense suite. These benchmarks are based on CTF.",
                    page=30,
                    score=19.0,
                )
            ],
            "table_6": [
                _candidate(
                    "table",
                    "6",
                    "Table 6. Also, we evaluate different modes of DeepSeek-V4-Flash",
                    page=36,
                    score=40.0,
                ),
                _candidate(
                    "table",
                    "6",
                    "Table 6 | Comparison between DeepSeek-V4-Pro-Max and closed/open source models.",
                    page=37,
                    score=64.0,
                ),
            ],
        }
    )
    expected = expected_captions_from_index(index)
    keys = {(item.kind, item.ident, item.page) for item in expected}
    assert ("figure", "9", 31) in keys
    assert ("table", "6", 38) in keys
    assert ("table", "6", 37) not in keys


def test_inventory_marks_missing_and_unexpected() -> None:
    expected = expected_captions_from_index(
        CaptionIndex(
            candidates={
                "figure_9": [
                    _candidate("figure", "9", "Figure 9 | Results on autonomous cyber offense suite.", 30, 19.0)
                ],
                "figure_1": [
                    _candidate("figure", "1", "Figure 1 | Left: benchmark performance", 0, 80.0)
                ],
            }
        )
    )
    records = [
        _record("figure", "1", 1, "Figure 1 | Left: benchmark performance"),
        _record("table", "6", 37, "Table 6. Also, we evaluate different modes"),
    ]
    report = reconcile_inventory(expected, records)
    missing_keys = {(item.kind, item.ident, item.page) for item in report.missing}
    unexpected_keys = {(item.kind, item.ident, item.page) for item in report.unexpected}
    assert ("figure", "9", 31) in missing_keys
    assert ("table", "6", 37) in unexpected_keys
    assert ("figure", "1", 1) not in missing_keys


def test_duplicate_png_marks_both_review_required(tmp_path) -> None:
    png_a = tmp_path / "Figure_11.png"
    png_b = tmp_path / "Figure_12.png"
    payload = b"\x89PNG\r\n\x1a\n" + b"same-bytes"
    png_a.write_bytes(payload)
    png_b.write_bytes(payload)
    records = [
        AttachmentRecord(kind="figure", ident="11", page=43, caption="Figure 11", out_path=str(png_a)),
        AttachmentRecord(kind="figure", ident="12", page=43, caption="Figure 12", out_path=str(png_b)),
    ]
    mark_duplicate_png_records(records)
    assert records[0].status == STATUS_REVIEW_REQUIRED
    assert records[1].status == STATUS_REVIEW_REQUIRED
    assert "duplicate_png" in records[0].warnings


def test_markdown_inserts_accepted_not_review_or_rejected() -> None:
    assert markdown_insertable(STATUS_ACCEPTED) is True
    assert markdown_insertable(STATUS_ACCEPTED_WITH_MARGIN) is True
    assert markdown_insertable(None) is True
    assert markdown_insertable(STATUS_REVIEW_REQUIRED) is False
    assert markdown_insertable(STATUS_REJECTED) is False


def test_bare_figure_label_is_expected() -> None:
    assert is_caption_anchor_candidate("Figure 22") is True
    assert is_caption_anchor_candidate("Table 6. Also, we evaluate different modes") is False
    index = CaptionIndex(
        candidates={
            "figure_22": [_candidate("figure", "22", "Figure 22", page=9, score=40.0)],
        }
    )
    expected = expected_captions_from_index(index)
    keys = {(item.kind, item.ident, item.page) for item in expected}
    assert ("figure", "22", 10) in keys


def test_unexpected_rejects_body_citation_not_bare_caption() -> None:
    records = [
        _record("figure", "22", 10, "Figure 22"),
        _record("figure", "1", 1, "Figure 1 | Left: benchmark performance"),
        _record("table", "6", 37, "Table 6. Also, we evaluate different modes"),
    ]
    report = reconcile_inventory([], records)
    apply_unexpected_rejects(report)
    by_id = {(rec.kind, rec.ident): rec for rec in records}
    assert by_id[("figure", "22")].status == STATUS_ACCEPTED
    assert by_id[("figure", "1")].status == STATUS_ACCEPTED
    assert by_id[("table", "6")].status == STATUS_REJECTED
    assert "unexpected_caption" in by_id[("table", "6")].warnings


def test_select_index_keeps_low_score_explicit() -> None:
    index = CaptionIndex(
        candidates={
            "figure_9": [
                _candidate(
                    "figure",
                    "9",
                    "Figure 9 | Results on autonomous cyber offense suite.",
                    page=30,
                    score=19.0,
                )
            ]
        }
    )
    candidate, weak = select_index_candidate(index, "figure", "9", 30)
    assert candidate is not None
    assert weak is True
    assert candidate.score == 19.0
