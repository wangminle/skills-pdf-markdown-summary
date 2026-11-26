# -*- coding: utf-8 -*-
"""双栏论文的通栏图与栏沟裁剪回归（2026-11-26，Holdout 发现）。

背景：lib/clip_limit.py 的 refine_clip_x_range 策略 1 按题注中心偏向页面中线哪一侧，
把裁剪框夹到左栏或右栏。真实双栏论文（Holdout 的 BERT / ResNet / SQuAD）上有两个问题：
- 跨两栏的通栏图，题注中心比中线偏右 1pt 就被夹成右半幅，18 张图里 14 张因此被判截断；
- 栏沟不在页面正中时，按栏距估算的栏沟偏到邻栏文字上，外扩余量把邻栏正文带进裁剪图。

守住的性质：
- 题注同时伸进左右两栏（通栏图表）时不按栏收窄；
- 栏沟两缘取本页实际正文行：左栏宽图里偏右的标签被标成右栏也不会把栏沟估偏；
- 单栏图的裁剪框不越过栏沟伸进邻栏文字；
- 栏沟取值不被外凸的图内标签或越界行带偏，离谱的取值不采用；左右栏以实测栏沟中点为界。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import fitz

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = PROJECT_ROOT / "skills" / "pdf-markdown-summary" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from lib import clip_limit as clip_module  # noqa: E402 - local script path is set above
from lib.models import DocumentLayoutModel  # noqa: E402

PAGE = fitz.Rect(0, 0, 612, 792)
LEFT_X0, RIGHT_X0 = 54.0, 321.0


def _fitted(text: str, limit: float, fontsize: float = 10.0) -> str:
    """把示例行裁到不超过 limit 宽（Times-Roman），保证行宽落在「窄行」范围内。"""
    while len(text) > 8 and fitz.get_text_length(text, fontname="tiro", fontsize=fontsize) > limit:
        text = text[:-1]
    return text


LEFT_LINE = _fitted("Left column sentence discussing the method details of this paper.", 248.0)
RIGHT_LINE = _fitted("Right column sentence reporting the benchmark results of the paper.", 236.0)


def _two_column_rows(page: "fitz.Page", top: float, count: int) -> None:
    for index in range(count):
        page.insert_text((LEFT_X0, top + index * 14), LEFT_LINE, fontsize=10, fontname="Times-Roman")
        page.insert_text((RIGHT_X0, top + index * 14), RIGHT_LINE, fontsize=10, fontname="Times-Roman")


def _make_paper_with_full_width_figure(path: Path) -> Path:
    """页面顶部的通栏浮动图，下方是双栏正文（LaTeX 双栏版式里 figure* 的常规位置）。

    左右栏行宽约 248pt / 236pt：栏沟约在 302～321，偏在页面中线左侧。题注左起 x=74、
    右端伸过页面中线，中心比中线偏右约 5pt。
    """
    with fitz.open() as doc:
        page = doc.new_page(width=612, height=792)
        page.draw_rect(fitz.Rect(72, 80, 540, 240), color=(0, 0, 0), width=1.2)
        for bar in range(10):
            x = 90 + bar * 48
            page.draw_line((x, 232), (x, 232 - 30 - (bar * 37) % 100), color=(0, 0, 0.6), width=6)
        page.insert_text(
            (74, 262),
            "Figure 1: Full width overview of the method, starting on the left and reaching past the page center.",
            fontsize=10, fontname="Times-Roman",
        )
        _two_column_rows(page, 300, 12)
        doc.save(path)
    return path


def test_actual_gutter_is_not_moved_by_labels_sticking_out_of_the_column() -> None:
    # 左栏正文 6 行（54～302）；图内刻度标签比栏左缘还靠左 10pt，1 个或 3 个都不该影响栏沟
    for labels in (1, 3, 7):
        units = _page_units()[0] + [_unit(44.0, 68.0, 0) for _ in range(labels)]
        assert clip_module._actual_column_gutter(_layout_model(text_units={0: units}), 0, 612.0) == (302.0, 321.0)


def test_actual_gutter_ignores_one_overfull_line() -> None:
    units = _page_units()[0] + [_unit(LEFT_X0, 340.0, 0), _unit(RIGHT_X0, 562.0, 1)]
    assert clip_module._actual_column_gutter(_layout_model(text_units={0: units}), 0, 612.0) == (302.0, 321.0)


def test_gutter_far_from_estimate_is_not_used() -> None:
    # 整个左栏是一张图：左栏只有 3 个图内标签（60～130），取到的「左栏右缘」130 离估算的 293.5 太远。
    # 采用它会把左栏图夹成 156 宽；不采用则回退估算，图（54～292）完整保留
    units = [_unit(60.0, 130.0, 0) for _ in range(3)] + [_unit(RIGHT_X0, 557.0, 1) for _ in range(6)]
    model = _layout_model(text_units={0: units})

    refined = clip_module.refine_clip_x_range(
        fitz.Rect(20, 330, 330, 450), fitz.Rect(54, 462, 240, 474), "below",
        [fitz.Rect(54, 330, 292, 450)], [], PAGE, layout_model=model, page_num=0, x_margin=26.0,
    )

    assert refined.x0 <= 54 and refined.x1 >= 292, refined


def test_right_column_caption_is_placed_by_actual_gutter_midpoint() -> None:
    # 版心偏左：左栏 30～260、右栏 280～510，栏沟中点 270，页面中线 306。右栏短题注 280～320 的中心
    # 是 300，比页面中线偏左，按中线判会错归左栏，右栏图（285～505）被夹成右缘 278
    units = [_unit(30.0, 260.0, 0) for _ in range(6)] + [_unit(280.0, 510.0, 1) for _ in range(6)]
    model = _layout_model(gap=20.0, text_units={0: units})

    refined = clip_module.refine_clip_x_range(
        fitz.Rect(20, 300, 580, 450), fitz.Rect(280, 462, 320, 474), "below",
        [fitz.Rect(285, 300, 505, 450)], [], PAGE, layout_model=model, page_num=0, x_margin=26.0,
    )

    assert 262 <= refined.x0 <= 285 and refined.x1 >= 505, refined


def _layout_model(gap: float = 25.0, text_units=None) -> DocumentLayoutModel:
    return DocumentLayoutModel(
        page_size=(612.0, 792.0), num_columns=2, margin_left=0.0, margin_right=612.0,
        margin_top=0.0, margin_bottom=792.0, column_gap=gap, typical_font_size=10.0,
        typical_line_height=12.0, typical_line_gap=2.0,
        text_units=text_units if text_units is not None else {0: []}, text_blocks={0: []}, vacant_regions={0: []},
    )


def _unit(x0: float, x1: float, column: int) -> SimpleNamespace:
    return SimpleNamespace(bbox=fitz.Rect(x0, 90, x1, 100), column=column, text="line",
                           text_type="paragraph", font_size=10.0)


def _page_units() -> dict:
    """本页文本单元：左右栏正文各 6 行；左栏宽图里偏右的标签按双峰中线被标成右栏。"""
    units = [_unit(LEFT_X0, 302.0, 0) for _ in range(6)] + [_unit(RIGHT_X0, 557.0, 1) for _ in range(6)]
    units += [_unit(212.4, 254.6, 1), _unit(223.1, 251.1, 1), _unit(226.2, 251.1, 1)]
    return {0: units}


def test_actual_gutter_ignores_figure_labels_labeled_as_right_column() -> None:
    # 按栏距估算：栏沟 293.5～318.5；实际正文行给出 302～321
    assert clip_module._actual_column_gutter(_layout_model(text_units=_page_units()), 0, 612.0) == (302.0, 321.0)


def test_actual_gutter_needs_body_lines_on_both_sides() -> None:
    only_left = {0: [_unit(LEFT_X0, 302.0, 0) for _ in range(6)]}
    overlapping = {0: [_unit(LEFT_X0, 340.0, 0) for _ in range(6)] + [_unit(RIGHT_X0, 557.0, 1) for _ in range(6)]}

    assert clip_module._actual_column_gutter(_layout_model(), 0, 612.0) is None                              # 没有文本单元
    assert clip_module._actual_column_gutter(_layout_model(text_units={1: _page_units()[0]}), 0, 612.0) is None  # 不是本页
    assert clip_module._actual_column_gutter(_layout_model(text_units=only_left), 0, 612.0) is None            # 只有一栏
    assert clip_module._actual_column_gutter(_layout_model(text_units=overlapping), 0, 612.0) is None          # 两栏文字重叠


def test_spanning_caption_is_not_clamped_to_one_column() -> None:
    # 题注 74～549：中心 311.5，比页面中线 306 偏右 5.5pt。旧行为：夹到右栏，x0 被抬到 292.5
    caption = fitz.Rect(74, 482, 549, 494)
    clip = fitz.Rect(40, 320, 580, 470)

    refined = clip_module.refine_clip_x_range(clip, caption, "below", [fitz.Rect(72, 320, 540, 460)], [], PAGE,
                                  layout_model=_layout_model(text_units=_page_units()), page_num=0, x_margin=26.0)

    assert refined.x0 < 80 and refined.x1 > 535, refined


def test_single_column_figure_stops_before_neighbor_column_text() -> None:
    units = _page_units()
    left_clip = fitz.Rect(20, 330, 330, 450)
    right_clip = fitz.Rect(290, 330, 590, 450)

    # 左栏图：右缘停在右栏文字（321 起）之前；按栏距估算加 26pt 余量会到 319.5 以外
    left = clip_module.refine_clip_x_range(left_clip, fitz.Rect(54, 462, 240, 474), "below",
                               [fitz.Rect(54, 330, 292, 450)], [], PAGE,
                               layout_model=_layout_model(text_units=units), page_num=0, x_margin=26.0)
    # 右栏图：左缘停在左栏文字（302 止）之后；旧行为抬到 318.5 - 26 = 292.5，压进左栏文字
    right = clip_module.refine_clip_x_range(right_clip, fitz.Rect(321, 462, 500, 474), "below",
                                [fitz.Rect(321, 330, 557, 450)], [], PAGE,
                                layout_model=_layout_model(text_units=units), page_num=0, x_margin=26.0)

    assert left.x0 <= 54 and 292 <= left.x1 <= 319, left
    assert 304 <= right.x0 <= 321 and right.x1 >= 557, right


def _extract_only_figure(path: Path, out_md: Path) -> dict:
    """跑正式转换，确认文档确实被判成双栏，再返回唯一的那张图。"""
    from core.pdf_to_markdown import main

    assert main(["--pdf", str(path), "--out", str(out_md)]) == 0
    gathered = json.loads((out_md.parent / "text" / "gathered_text.json").read_text(encoding="utf-8"))
    layout = json.loads((out_md.parent / "images" / "layout_model.json").read_text(encoding="utf-8"))
    assert gathered["num_columns"] == 2 and layout["num_columns"] == 2
    index = json.loads((out_md.parent / "images" / "index.json").read_text(encoding="utf-8"))
    figures = [item for item in index["items"] if item["type"] == "figure"]
    assert len(figures) == 1
    return figures[0]


def test_full_width_figure_with_spanning_caption_is_kept_whole(tmp_path: Path) -> None:
    pdf = _make_paper_with_full_width_figure(tmp_path / "full-width.pdf")

    figure = _extract_only_figure(pdf, tmp_path / "full" / "paper.md")

    # 修复前：题注中心偏右，图被夹到右栏，x1 只有 315.9，判 review_required
    assert figure["status"] == "accepted", figure["warnings"]
    x0, y0, x1, y1 = figure["final_bbox"]
    assert x0 <= 80 and x1 >= 535, figure["final_bbox"]
    assert 70 <= y0 and y1 <= 300, figure["final_bbox"]   # 不把题注下方的双栏正文圈进来
