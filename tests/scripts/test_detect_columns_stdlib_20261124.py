#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""WP-2.1：栏检测无 NumPy 与直方图边界回归。"""

import builtins
import logging
import os
import sys
from types import SimpleNamespace

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPTS_DIR = os.path.join(PROJECT_ROOT, "skills", "pdf-markdown-summary", "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from lib.layout_model import detect_columns, detect_vacant_regions


@pytest.fixture
def without_numpy(monkeypatch):
    real_import = builtins.__import__

    def blocked_import(name, *args, **kwargs):
        if name == "numpy" or name.startswith("numpy."):
            raise ImportError("NumPy blocked by regression test")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked_import)
    with pytest.raises(ImportError, match="NumPy blocked"):
        __import__("numpy")


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
    assert column_gap == pytest.approx(16.65)
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
    assert column_gap == pytest.approx(20.0)
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


def test_vacant_region_dependency_warning_emitted_once_per_document(without_numpy, caplog):
    doc = [
        SimpleNamespace(rect=SimpleNamespace(width=100.0, height=100.0))
        for _ in range(3)
    ]

    with caplog.at_level(logging.WARNING, logger="lib.layout_model"):
        result = detect_vacant_regions({}, doc)

    assert result == {0: [], 1: [], 2: []}
    messages = [record.message for record in caplog.records if "NumPy/SciPy not available" in record.message]
    assert len(messages) == 1
