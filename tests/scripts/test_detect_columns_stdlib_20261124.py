#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WP-2.1：栏检测无 NumPy 与直方图边界回归。"""

import builtins
import logging
import os
import sys
from types import SimpleNamespace

import fitz
import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPTS_DIR = os.path.join(PROJECT_ROOT, "skills", "pdf-markdown-summary", "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from lib.layout_model import detect_columns, detect_vacant_regions  # noqa: E402 - path is set above
from lib.text_extract import extract_text_with_format  # noqa: E402 - path is set above


@pytest.fixture
def without_numpy(monkeypatch):
    real_import = builtins.__import__
    blocked_calls = []

    def blocked_import(name, *args, **kwargs):
        if name == "numpy" or name.startswith("numpy."):
            blocked_calls.append(name)
            raise ImportError("NumPy blocked by regression test")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked_import)
    with pytest.raises(ImportError, match="NumPy blocked"):
        __import__("numpy")
    yield blocked_calls


def _paragraph(x0, width):
    return SimpleNamespace(
        text_type="paragraph",
        bbox=SimpleNamespace(x0=x0, width=width),
        column=99,
    )


def test_standard_two_columns_without_numpy(without_numpy):
    left = [_paragraph(54.0, 237.0) for _ in range(12)]
    right = [_paragraph(321.0, 237.0) for _ in range(12)]

    num_columns, column_gap, updated = detect_columns({0: left + right}, 595.3)

    assert num_columns == 2
    # BUG-188：峰位置改取桶内样本均值，栏距不再被桶左边界低估一个桶宽
    assert column_gap == pytest.approx(30.0)
    assert {unit.column for unit in updated[0][:12]} == {0}
    assert {unit.column for unit in updated[0][12:]} == {1}


def test_insufficient_paragraph_samples_remain_single_column(without_numpy):
    units = [_paragraph(54.0 if i % 2 == 0 else 321.0, 237.0) for i in range(9)]

    num_columns, column_gap, updated = detect_columns({0: units[:5], 1: units[5:]}, 595.3)

    assert num_columns == 1
    assert column_gap == 0.0
    assert {unit.column for page_units in updated.values() for unit in page_units} == {-1}


def test_histogram_last_bin_includes_right_endpoint(without_numpy):
    units = [_paragraph(0.0, 170.0) for _ in range(12)]
    units.extend([_paragraph(190.0, 170.0), _paragraph(200.0, 170.0)])

    num_columns, column_gap, updated = detect_columns({0: units}, 400.0)

    assert num_columns == 2
    # 末桶含 190.0 与 200.0，峰位置取桶内均值 195.0（BUG-188）
    assert column_gap == pytest.approx(25.0)
    assert [unit.column for unit in updated[0]] == [0] * 12 + [1, 1]


def test_internal_bucket_boundaries_match_numpy_semantics(without_numpy):
    boundary_values = [54.0 + i * 13.35 for i in range(21)]
    counts = [2, 3, 2, 1, 2, 1, 2, 2, 1, 0, 2, 4, 1, 1, 5, 2, 3, 3, 3, 2, 1]
    units = [
        _paragraph(value, 120.0)
        for value, count in zip(boundary_values, counts)
        for _ in range(count)
    ]

    num_columns, column_gap, updated = detect_columns({0: units}, 511.85)

    assert num_columns == 1
    assert column_gap == 0.0
    assert {unit.column for unit in updated[0]} == {-1}


def test_justified_columns_keep_small_column_gap(without_numpy):
    """BUG-188：x0 有 0.5pt 抖动、行宽≈栏宽时，桶左边界会把 10pt 栏距算成负值。"""
    left = [_paragraph(54.0 if index % 2 == 0 else 55.0, 240.0) for index in range(10)]
    right = [_paragraph(304.0 if index % 2 == 0 else 305.0, 240.0) for index in range(10)]

    num_columns, column_gap, _updated = detect_columns({0: left + right}, 595.3)

    assert num_columns == 2
    assert column_gap == pytest.approx(10.0, abs=0.6)


def test_real_two_column_pdf_without_numpy(without_numpy, tmp_path):
    pdf_path = tmp_path / "two-column.pdf"
    with fitz.open() as doc:
        page = doc.new_page(width=595.3, height=842.0)
        for column, x0 in enumerate((54.0, 321.0)):
            for line in range(16):
                page.insert_text(
                    (x0, 72.0 + line * 16.0),
                    f"Column {column} line {line} has ordinary paragraph words.",
                    fontname="Times-Roman",
                    fontsize=10.0,
                )
        doc.save(pdf_path)

    layout = extract_text_with_format(str(pdf_path))

    # 夹具前提：NumPy 确实被屏蔽，否则这条用例没有覆盖无依赖路径
    assert without_numpy
    assert layout.num_columns == 2
    assert 0 < layout.column_gap <= 0.30 * layout.page_size[0]
    left = [unit for unit in layout.text_units[0] if unit.bbox.x0 < 100]
    right = [unit for unit in layout.text_units[0] if unit.bbox.x0 > 300]
    assert len(left) == len(right) == 16
    assert {unit.column for unit in left} == {0}
    assert {unit.column for unit in right} == {1}


def test_vacant_region_dependency_warning_emitted_once_per_document(without_numpy, caplog):
    doc = [
        SimpleNamespace(rect=SimpleNamespace(width=100.0, height=100.0))
        for _ in range(3)
    ]

    imports_before = len(without_numpy)
    with caplog.at_level(logging.WARNING, logger="lib.layout_model"):
        result = detect_vacant_regions({}, doc)

    assert result == {0: [], 1: [], 2: []}
    messages = [record.message for record in caplog.records if "NumPy/SciPy not available" in record.message]
    assert len(messages) == 1
    assert len(without_numpy) == imports_before + 1
