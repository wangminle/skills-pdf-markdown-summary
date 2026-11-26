# -*- coding: utf-8 -*-
"""版式模型双栏判定与文本层同源回归（2026-11-26，V0.6.15 阶段 1.2）。

背景：版式模型的 detect_columns 只看段落起点的双峰，单栏文档里并排的表格、
左右分列的内容同样会形成双峰。误判成双栏后，lib/clip_limit.py 的策略 1 会把
图框夹到题注所在的那半页，通栏图被切掉一半。文本层的判定带有满宽主导页、
并排表格页、框线表格单元格等守卫，所以让版式模型的双栏结论必须得到文本层
文档级判定的确认（layout_model.detect_columns 的 dual_confirmed）。

同时补上并排表格页判据的一个洞：起点在左栏、右缘却越过右栏起点的行横跨
两栏，计入左列会把栏间留白拉成负数（text_extract._min_column_gap）。

守住的性质：
- 直方图判出双栏但文本层不认时回落单栏；文本层确认或没有结论时行为不变；
- 单栏页里的并排表格不再让版式模型判双栏；
- 带框线表格页在资产提取链路里沿用 gather 的文档级判定；
- 通栏图 + 中等宽度题注 + 下方两列内容：图不被切，正文按行输出。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import fitz
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = PROJECT_ROOT / "skills" / "pdf-markdown-summary" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from lib import text_extract  # noqa: E402 - local script path is set above
from lib.layout_model import detect_columns  # noqa: E402

WIDE_BODY_SENTENCE = (
    "The preceding discussion describes a method for checking readings in each recorded experiment."
)
FIGURE_RECT = fitz.Rect(60, 300, 540, 430)
CAPTION = "Figure 1: Full width overview of readings across all recorded groups."


def _paragraph_units() -> dict:
    """两页、每页左右各 16 行的段落单元，起点两个尖峰（54pt 与 321pt）。"""
    units = {}
    for pno in range(2):
        page_units = []
        for index in range(16):
            top = 100 + index * 14
            page_units.append(SimpleNamespace(
                bbox=fitz.Rect(54, top, 254, top + 10), text_type="paragraph", font_size=10.0, column=-1,
            ))
            page_units.append(SimpleNamespace(
                bbox=fitz.Rect(321, top, 521, top + 10), text_type="paragraph", font_size=10.0, column=-1,
            ))
        units[pno] = page_units
    return units


def test_detect_columns_needs_text_layer_confirmation_to_stay_dual() -> None:
    # 前提：没有文本层结论时，直方图本身判双栏（历史行为保持不变）
    assert detect_columns(_paragraph_units(), 612.0)[:2] == (2, pytest.approx(67.0))

    confirmed = detect_columns(_paragraph_units(), 612.0, dual_confirmed=True)
    assert confirmed[0] == 2 and confirmed[1] > 0
    assert {unit.column for units in confirmed[2].values() for unit in units} == {0, 1}

    rejected = detect_columns(_paragraph_units(), 612.0, dual_confirmed=False)
    assert rejected[0] == 1 and rejected[1] == 0.0
    assert {unit.column for units in rejected[2].values() for unit in units} == {-1}


def _make_side_by_side_table_page(path: Path) -> None:
    """通栏正文 + 同字号的两列长文本，列间留白约 80pt（CHK-094 形态）。"""
    with fitz.open() as doc:
        page = doc.new_page(width=600, height=800)
        for index in range(5):
            page.insert_text((50, 150 + index * 19), f"{WIDE_BODY_SENTENCE} {index}.", fontsize=10)
        for index in range(5):
            page.insert_text((50, 360 + index * 40), f"Descriptive label for the experiment group. {index}", fontsize=10)
            page.insert_text((330, 373 + index * 40), f"Corresponding readings in this column. {index}", fontsize=10)
        doc.save(path)


def test_single_column_page_with_side_by_side_table_stays_single_in_layout_model(tmp_path: Path) -> None:
    pdf = tmp_path / "side-by-side-table.pdf"
    _make_side_by_side_table_page(pdf)

    model = text_extract.extract_text_with_format(str(pdf))

    assert model.num_columns == 1
    assert model.column_gap == 0.0
    assert {unit.column for units in model.text_units.values() for unit in units} == {-1}


def _make_ruled_two_column_table_page(path: Path) -> None:
    """通栏正文 + 窄间距的带框线两列表格（单元格两行）。

    只看几何时这一页像双栏：文本层要先把框线单元格从证据里剔除才判单栏。
    """
    with fitz.open() as doc:
        page = doc.new_page(width=600, height=800)
        for index in range(11):
            page.insert_text((50, 100 + index * 19), WIDE_BODY_SENTENCE, fontsize=10)
        for row in range(5):
            y = 345 + row * 55
            for x, dy, name in ((50, 5, "Label"), (320, -5, "Reading")):
                page.insert_text(
                    (x, y + dy),
                    f"{name} cell {row} contains grouped results and extended\n"
                    "The second line describes grouped results and extended",
                    fontsize=10,
                )
        for y in (329, 391, 446, 501, 556, 610):
            page.draw_line((45, y), (582, y))
        for x in (45, 310, 582):
            page.draw_line((x, 329), (x, 610))
        doc.save(path)


@pytest.mark.parametrize("assets_enabled", [True, False])
def test_layout_columns_use_gather_verdict_in_both_export_paths(tmp_path: Path, assets_enabled: bool) -> None:
    """资产提取与仅导出版式 JSON 两条路径都沿用 gather 的文档级判定，栏数一致。

    仅布局导出没有 gather 时曾按不含框线单元格剔除的判定写成 2 栏，与完整提取的 1 栏矛盾。
    """
    from core.pdf_to_markdown import main

    pdf = tmp_path / "ruled-table.pdf"
    _make_ruled_two_column_table_page(pdf)
    assert text_extract.gather_structured_text(str(pdf)).num_columns == 1
    assert text_extract.extract_text_with_format(str(pdf), text_layer_dual=False).num_columns == 1

    # 仅布局导出没有 gather 的现算判定会得到 2 栏；带框线表格页上原始判定本就是双栏
    assert text_extract.extract_text_with_format(str(pdf)).num_columns == 2

    out_md = tmp_path / "assets" / "paper.md" if assets_enabled else tmp_path / "layout-only" / "paper.md"
    mode = [] if assets_enabled else ["--images", "off", "--layout-model-detail", "summary"]
    assert main(["--pdf", str(pdf), "--out", str(out_md), "--tables", "off", *mode]) == 0

    layout = json.loads((out_md.parent / "images" / "layout_model.json").read_text(encoding="utf-8"))
    assert layout["num_columns"] == 1
    assert layout["column_gap"] == 0.0


def _make_two_column_paper(path: Path) -> None:
    with fitz.open() as doc, fitz.open() as left, fitz.open() as right:
        page = doc.new_page(width=612, height=792)
        page.insert_text((72, 68), "A Unified Architecture for Two-Column Academic Paper Layout Analysis",
                         fontsize=14, fontname="Times-Bold")
        left_page = left.new_page(width=612, height=792)
        right_page = right.new_page(width=612, height=792)
        for index in range(16):
            left_page.insert_text((54, 130 + index * 32), f"Left column sentence {index:02d} discussing method details.",
                                  fontsize=10, fontname="Times-Roman")
            right_page.insert_text((321, 130 + index * 32), f"Right column sentence {index:02d} reporting benchmark results.",
                                   fontsize=10, fontname="Times-Roman")
        page.show_pdf_page(page.rect, left, 0)
        page.show_pdf_page(page.rect, right, 0)
        doc.save(path)


@pytest.mark.parametrize("explicit_verdict", [None, True])
def test_two_column_paper_keeps_two_columns(tmp_path: Path, explicit_verdict) -> None:
    pdf = tmp_path / "two-col.pdf"
    _make_two_column_paper(pdf)
    assert text_extract.gather_structured_text(str(pdf)).is_dual_column is True

    model = text_extract.extract_text_with_format(str(pdf), text_layer_dual=explicit_verdict)

    assert model.num_columns == 2
    assert model.column_gap > 0
    assert {unit.column for units in model.text_units.values() for unit in units} == {0, 1}


def _make_full_width_figure_above_side_by_side_content(path: Path) -> None:
    """通栏正文 + 通栏图 + 中等宽度题注（横跨到右列起点之后）+ 无框线的两列多行内容。"""
    with fitz.open() as doc:
        page = doc.new_page(width=600, height=800)
        for index in range(10):
            page.insert_text((50, 70 + index * 16), f"{WIDE_BODY_SENTENCE} {index}.", fontsize=10)
        page.draw_rect(FIGURE_RECT, color=(0, 0, 0), width=1.2)
        for bar in range(12):
            x = 80 + bar * 38
            page.draw_line((x, 420), (x, 420 - 30 - (bar * 23) % 70), color=(0, 0, 0.6), width=6)
        page.insert_text((60, 452), CAPTION, fontsize=10)
        for index in range(5):
            page.insert_text((50, 508 + index * 51),
                             f"Descriptive experiment group {index}\nA second long line within this cell.", fontsize=10)
            page.insert_text((330, 513 + index * 51),
                             f"Corresponding measurement group {index}\nA second long line within this cell.", fontsize=10)
        doc.save(path)


def test_min_column_gap_ignores_lines_spanning_both_columns() -> None:
    left_x0, left_width, right_x0 = 50.0, 148.9, 330.0
    x0_values = [left_x0] * 10 + [right_x0] * 10
    width_values = [left_width] * 10 + [166.2] * 10
    peaks = (50.9, right_x0)

    assert text_extract._min_column_gap(x0_values, width_values, peaks, 600.0) == pytest.approx(131.1)

    # 题注起点落在左栏位置、右缘 362.3 却越过右列起点 330：不计入左列
    spanning = x0_values + [60.0]
    spanning_widths = width_values + [302.3]
    assert text_extract._min_column_gap(spanning, spanning_widths, peaks, 600.0) == pytest.approx(131.1)


def test_full_width_figure_is_not_cut_by_side_by_side_content(tmp_path: Path) -> None:
    from core.pdf_to_markdown import main

    pdf = tmp_path / "figure-above-side-by-side.pdf"
    _make_full_width_figure_above_side_by_side_content(pdf)

    gathered = text_extract.gather_structured_text(str(pdf))

    # 两列并排的内容按行输出：左、右、左、右……
    cells = [
        paragraph.text.splitlines()[0] for paragraph in gathered.paragraphs
        if paragraph.text.startswith(("Descriptive experiment", "Corresponding measurement"))
    ]
    assert gathered.num_columns == 1
    assert cells == [
        text for index in range(5)
        for text in (f"Descriptive experiment group {index}", f"Corresponding measurement group {index}")
    ]

    out_md = tmp_path / "result" / "paper.md"
    assert main(["--pdf", str(pdf), "--out", str(out_md), "--tables", "off"]) == 0

    index = json.loads((out_md.parent / "images" / "index.json").read_text(encoding="utf-8"))
    figures = [item for item in index["items"] if item.get("type") == "figure"]
    assert len(figures) == 1
    bbox = figures[0].get("final_bbox") or figures[0].get("bbox")
    # 图框横向完整覆盖图（x 60～540）：没有被夹到题注所在的左半页
    assert bbox[0] <= FIGURE_RECT.x0 + 1 and bbox[2] >= FIGURE_RECT.x1 - 1
