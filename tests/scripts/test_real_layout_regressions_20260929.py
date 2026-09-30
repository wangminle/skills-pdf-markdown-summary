"""由 PARADISE / SASSI 真实排版缩减得到的布局回归。"""
from pathlib import Path
import re
import sys
import fitz
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "skills/pdf-markdown-summary/scripts"))
from lib.table_refine import limit_table_clip_to_caption_column, trim_table_clip_far_side_body
from lib.acceptance import looks_like_table_text


def test_segmented_full_width_rule_preserves_sparse_numeric_columns():
    page = fitz.Rect(0, 0, 595, 842)
    clip = fitz.Rect(26, 93, 569, 613)
    caption = fitz.Rect(72, 71, 289, 87)
    lines = [(fitz.Rect(340, 120 + i * 18, 365, 136 + i * 18), 12, str(i)) for i in range(3)]
    drawings = [{"rect": fitz.Rect(66.3, 100.2, 278.5, 100.4)},
                {"rect": fitz.Rect(278.9, 100.2, 544.9, 100.4)}]
    actual = limit_table_clip_to_caption_column(clip, caption, page, lines, drawings)
    assert actual == clip


def _question_rows():
    questions = ["Did you complete the task?", "Was the system easy to understand?",
      "Did the system understand what you said?", "Was it easy to find the message you wanted?",
      "Was the pace of interaction with the system appropriate?",
      "Did you know what you could say at each point of the dialogue?",
      "How often was the system sluggish and slow to reply to you?",
      "Did the system work the way you expected it to?",
      "How did the voice interface compare to a manual interface?",
      "Do you think you would use the system regularly?"]
    return [(fitz.Rect(72, 115+i*16, 403, 131+i*16), 12, q) for i,q in enumerate(questions)]


def test_questionnaire_rows_are_not_trimmed_as_body():
    clip = fitz.Rect(26, 107, 569, 281)
    actual = trim_table_clip_far_side_body(clip, fitz.Rect(72, 71, 471, 101), _question_rows(), "below")
    assert actual.y1 >= 275


def test_questionnaire_rows_can_keep_compact_crop():
    assert looks_like_table_text(fitz.Rect(26, 107, 569, 281), _question_rows())


def test_cross_kind_caption_limits_figure_and_table(tmp_path):
    from lib.extract_figures import extract_figures
    from lib.extract_tables import extract_tables
    pdf = tmp_path / "mixed.pdf"
    doc = fitz.open()
    p = doc.new_page(width=612, height=792)
    p.draw_rect(fitz.Rect(72, 50, 290, 95))
    p.insert_text((72, 112), "Table 1: Attribute matrix", fontsize=10)
    p.draw_rect(fitz.Rect(72, 145, 290, 330))
    p.insert_text((72, 350), "Figure 1: Dialogue interaction", fontsize=10)
    p.draw_rect(fitz.Rect(72, 390, 290, 445))
    p.insert_text((72, 462), "Table 2: Attribute values", fontsize=10)
    doc.save(pdf); doc.close()
    out = tmp_path / "images"; out.mkdir()
    figures = extract_figures(str(pdf), str(out), dpi=72, global_anchor="above", refine_safe=False)
    tables = extract_tables(str(pdf), str(out), dpi=72, global_anchor_table="above", refine_safe=False)
    assert figures[0].final_bbox[1] > 112
    assert next(t for t in tables if t.ident == "2").final_bbox[1] > 350


def test_confirmed_table_width_survives_generic_x_refinement():
    from lib.clip_limit import refine_clip_x_range
    actual = refine_clip_x_range(
        fitz.Rect(26, 93, 569, 733), fitz.Rect(72, 71, 289, 87), "below",
        [], [], fitz.Rect(0, 0, 595, 842), infer_columns=False,
    )
    assert actual.x1 >= 545


def test_width_restore_requires_content_outside_compact_table():
    from lib.table_refine import restore_table_clip_width
    clip = fitz.Rect(61, 95, 248, 297)
    base = fitz.Rect(26, 93, 569, 613)
    rows = [(fitz.Rect(72, 110+i*18, 240, 126+i*18), 12, f"Scale item {i}") for i in range(8)]
    assert restore_table_clip_width(clip, base, table_band_changed=True, text_lines=rows) == clip


def test_width_restore_recovers_cells_even_above_old_ratio():
    from lib.table_refine import restore_table_clip_width
    clip = fitz.Rect(70, 100, 320, 200)
    base = fitz.Rect(26, 100, 569, 200)
    rows = [(fitz.Rect(x, y, x + 35, y + 12), 10, "0.42")
            for y in (110, 130, 150) for x in (80, 280, 440)]
    actual = restore_table_clip_width(clip, base, table_band_changed=True, text_lines=rows)
    assert actual.x1 >= 475


def test_direction_does_not_join_prose_from_two_columns():
    from lib.direction import score_local_direction
    caption = fitz.Rect(50, 150, 280, 178)
    lines = []
    for y in (75, 95, 115):
        lines.extend([(fitz.Rect(50, y, 125, y + 12), 10, "Model"),
                      (fitz.Rect(170, y + 5, 220, y + 17), 10, "0.95")])
    for y in range(195, 380, 14):
        for x in (50, 320):
            lines.append((fitz.Rect(x, y, x + 230, y + 12), 10,
                          "The results are discussed in the next section"))
    direction, confidence = score_local_direction(
        caption, fitz.Rect(0, 0, 612, 792), [], [],
        is_table=True, text_lines=lines,
    )
    assert direction == "above" and confidence >= 0.5


def test_scan_background_is_not_a_local_object():
    from lib.extract_helpers import collect_image_rects
    data = {"blocks": [
        {"type": 0, "lines": [{"spans": [{"text": "OCR words"}]}]},
        {"type": 1, "bbox": (20, 20, 592, 772)},
        {"type": 1, "bbox": (80, 100, 240, 250)},
    ]}
    assert collect_image_rects(data, fitz.Rect(0, 0, 612, 792)) == [
        fitz.Rect(80, 100, 240, 250)]


def test_neighbor_caption_index_includes_continuation():
    from lib.caption_detection import build_caption_index
    with fitz.open() as doc:
        page = doc.new_page()
        page.insert_text((72, 100), "Table 1: Attributes in the timetable\ndomain", fontsize=10)
        index = build_caption_index(doc)
        candidate = index.candidates["table_1"][0]
        assert candidate.rect.y1 > 110
        assert candidate.text.endswith("domain")


def test_tall_factor_matrix_preserves_last_row(tmp_path):
    from lib.extract_tables import extract_tables
    pdf = tmp_path / "factors.pdf"
    with fitz.open() as doc:
        p = doc.new_page(width=595, height=842)
        p.insert_text((72, 80), "Table 4: Factor analysis", fontsize=12)
        p.draw_line((66, 100), (545, 100))
        for y in range(120, 725, 20):
            p.insert_text((72, y), "Statement about the system", fontsize=10)
            for x in (310, 350, 390, 430, 470, 510):
                p.insert_text((x, y), ".72", fontsize=10)
        p.insert_text((72, 740), "Percentage of Variance", fontsize=10)
        p.insert_text((510, 740), "12.8", fontsize=10)
        p.draw_line((66, 745), (545, 745))
        doc.save(pdf)
    records = extract_tables(str(pdf), str(tmp_path / "images"), dpi=72,
                             global_anchor_table="below")
    assert records[0].final_bbox[3] >= 745
    assert records[0].final_bbox[2] >= 545
    limited = extract_tables(str(pdf), str(tmp_path / "limited"), dpi=72,
                             global_anchor_table="below", no_refine_tables=["4"])
    assert "table_band_open" in limited[0].warnings
    assert limited[0].status != "accepted"


def test_scan_preflight_warns_about_ocr_text(tmp_path):
    from lib.text_extract import pre_validate_pdf
    pdf = tmp_path / "scan.pdf"
    with fitz.open() as doc:
        p = doc.new_page(width=612, height=792)
        pix = fitz.Pixmap(fitz.csGRAY, fitz.IRect(0, 0, 612, 792), False)
        pix.clear_with(255)
        p.insert_image(p.rect, pixmap=pix)
        p.insert_text((50, 100), "OCR text with uncertain spelling and recognition accuracy " * 2,
                      fontsize=9, render_mode=3)
        doc.save(pdf)
    result = pre_validate_pdf(str(pdf))
    assert result.has_text_layer
    assert any("OCR" in warning for warning in result.warnings)


def test_column_table_rules_exclude_adjacent_figure():
    clip = fitz.Rect(26, 0, 586, 227)
    caption = fitz.Rect(315, 233, 559, 267)
    drawings = [{"rect": fitz.Rect(316, y, 558, y)} for y in (72, 85, 110, 222)]
    actual = limit_table_clip_to_caption_column(
        clip, caption, fitz.Rect(0, 0, 612, 792), [], drawings)
    assert actual.x0 >= 306


def test_grouped_rules_do_not_cut_cross_column_cells():
    # 通栏表的左右列组各带上下横线；右列数值单元格与左列标签同行对齐，
    # 局部横线不得覆盖跨栏延续单元格证据把右列切掉。
    lines = []
    for i in range(3):
        y = 210 + i * 18
        lines.extend([
            (fitz.Rect(40, y, 250, y + 12), 9, f"Metric {i}"),
            (fitz.Rect(320, y, 560, y + 12), 9, "0.47 0.56"),
        ])
    drawings = [
        {"rect": fitz.Rect(x, y, x + w, y)}
        for y in (203, 280) for x, w in ((40, 210), (320, 240))
    ]
    actual = limit_table_clip_to_caption_column(
        fitz.Rect(30, 200, 570, 290), fitz.Rect(70, 180, 280, 194),
        fitz.Rect(0, 0, 612, 792), lines, drawings,
    )
    assert actual.x1 >= 560, f"分组横线把通栏表右列切掉 (x1={actual.x1})"


def test_far_side_trim_keeps_ink_band_on_scan_pages():
    from lib.figure_post import trim_far_side_noise_before_content
    # 扫描页无任何图形对象，唯一文字证据是首个 OCR 标签（y69.4）；
    # autocrop 顶边 y43 与标签之间是被裁掉的根节点边框墨迹，不得当噪声裁掉。
    clip = fitz.Rect(311, 0, 528.7, 262.3)
    candidate = fitz.Rect(311, 43, 528.7, 262.3)
    lines = [(fitz.Rect(330, 69.4, 480, 81.5), 9, "~:E.AC, DR, D")]

    def probe(_rect):
        return True  # 带内有可见墨迹（文字行由探针遮罩）

    kept = trim_far_side_noise_before_content(
        clip, candidate, "above", [], [], lines, ink_probe=probe)
    assert kept.y0 == 43, f"带内墨迹被当噪声裁掉 (y0={kept.y0})"

    # 探针确认带内无墨迹（真白边/页眉）时仍正常裁剪
    trimmed = trim_far_side_noise_before_content(
        clip, candidate, "above", [], [], lines,
        ink_probe=lambda _rect: False)
    assert trimmed.y0 == pytest.approx(61.4), f"白边未按文字证据裁剪 (y0={trimmed.y0})"


def _block_with_lines(texts, x0=100, y0=90, line_h=11.5, w=400):
    lines = []
    y = y0
    for t in texts:
        lines.append({
            "bbox": [x0, y, x0 + w, y + line_h - 1.5],
            "spans": [{"text": t, "size": 9.5, "bbox": [x0, y, x0 + w, y + line_h - 1.5]}],
        })
        y += line_h
    return {"type": 0, "bbox": [x0, y0, x0 + w, y], "lines": lines}


def test_body_citation_sentence_not_merged_into_tall_caption():
    import re
    from lib.caption_detection import merge_caption_lines
    pattern = re.compile(r"^\s*(?:Table|Tab\.?)\s+([A-Za-z]?\d+)", re.I)
    block = _block_with_lines([
        "Table 8 shows that RL plays a crucial role in FunAudio-ASR",
        "o RL training. Table 8 shows the comparison of models w/ or",
        "w/o RL on five public test sets. The RL model achieves",
        "better accuracy and recall across most test sets. In",
        "certain domains, such as philosophy, the RL model may",
    ])
    merged = merge_caption_lines(block, 0, pattern)
    assert merged is None, (
        "正文引用句（Table 8 shows that...）不得合并成假题注"
    )


def test_tall_genuine_caption_still_merges():
    import re
    from lib.caption_detection import merge_caption_lines
    pattern = re.compile(r"^\s*(?:Figure|Fig\.?)\s+([A-Za-z]?\d+)", re.I)
    block = _block_with_lines([
        "Figure 12: Fine-grained prefix caching within a physical cache block. A",
        "6144-token physical cache block is divided into multiple prefix-hash",
        "blocks, each storing a hash of its tokens. During inference, the",
        "model first locates the matching prefix-hash blocks and computes",
    ])
    merged = merge_caption_lines(block, 0, pattern)
    assert merged is not None and merged.line_count == 4, (
        "无引用动词的四行长题注（Kimi F12 类）必须保留合并"
    )


def test_two_line_caption_still_merges():
    import re
    from lib.caption_detection import merge_caption_lines
    pattern = re.compile(r"^\s*(?:Table|Tab\.?)\s+([A-Za-z]?\d+)", re.I)
    block = _block_with_lines([
        "Table 8: Comparison between the models w/ or w/o reinforce-",
        "ment learning.",
    ])
    merged = merge_caption_lines(block, 0, pattern)
    assert merged is not None and merged.line_count == 2


def test_snap_reclaims_glyph_box_tail_below_clip():
    from lib.clip_limit import snap_clip_to_contained_text_lines
    clip = fitz.Rect(321.0, 49.9, 504.8, 434.7)
    caption = fitz.Rect(321.6, 436.7, 543.7, 450.5)
    lines = [
        (fitz.Rect(322, 60, 480, 75), 12, "U1: ..."),
        (fitz.Rect(330.0, 426.6, 480.0, 436.0), 12, "U5: Please reserve me a seat"),
    ]
    # 题注在裁剪框下方 = 内容在题注上方，主链方向语义为 above
    actual = snap_clip_to_contained_text_lines(clip, lines, caption, "above")
    assert actual.y1 >= 436.0
    assert actual.y1 <= caption.y0
    assert actual.y0 == clip.y0


def test_snap_far_side_can_grow_but_caption_side_clamped_above():
    from lib.clip_limit import snap_clip_to_contained_text_lines
    # above：内容在题注上方（题注在框下方）。远端（顶部）不受题注限制，
    # 靠近题注的底部外扩不得超过题注 y0。
    clip = fitz.Rect(50, 100, 300, 200)
    caption = fitz.Rect(50, 202, 300, 222)
    lines = [
        (fitz.Rect(60, 96, 200, 104), 10, "figure top label"),
        (fitz.Rect(60, 192, 200, 204), 10, "figure label"),
    ]
    actual = snap_clip_to_contained_text_lines(clip, lines, caption, "above")
    assert actual.y0 == 96
    assert actual.y1 == 202


def test_snap_far_side_can_grow_but_caption_side_clamped_below():
    from lib.clip_limit import snap_clip_to_contained_text_lines
    # below：内容在题注下方（题注在框上方）。远端（底部）不受题注限制，
    # 靠近题注的顶部外扩不得超过题注 y1。
    clip = fitz.Rect(50, 100, 300, 200)
    caption = fitz.Rect(50, 70, 300, 98)
    lines = [
        (fitz.Rect(60, 96, 200, 104), 10, "figure top label"),
        (fitz.Rect(60, 190, 200, 202), 10, "figure label"),
    ]
    actual = snap_clip_to_contained_text_lines(clip, lines, caption, "below")
    assert actual.y0 == 98
    assert actual.y1 == 202


def test_snap_ignores_mostly_outside_neighbor_lines():
    from lib.clip_limit import snap_clip_to_contained_text_lines
    clip = fitz.Rect(321.0, 49.9, 504.8, 434.7)
    caption = fitz.Rect(321.6, 436.7, 543.7, 450.5)
    neighbor = (fitz.Rect(322, 436.0, 480, 445.0), 12, "body under crop")
    actual = snap_clip_to_contained_text_lines(clip, [neighbor], caption, "above")
    assert actual == clip


def test_snap_ignores_lines_needing_large_growth():
    from lib.clip_limit import snap_clip_to_contained_text_lines
    clip = fitz.Rect(321.0, 49.9, 504.8, 434.7)
    caption = fitz.Rect(321.6, 450.0, 543.7, 464.0)
    tall = (fitz.Rect(322, 425.0, 480, 445.0), 12, "tall row crossing out")
    actual = snap_clip_to_contained_text_lines(clip, [tall], caption, "above")
    assert actual == clip


def test_title_recovery_stops_at_wrapped_body_pair():
    from lib.figure_post import expand_clip_to_nearby_figure_title
    base = fitz.Rect(309.2, 49.9, 586.0, 430.7)
    clip = fitz.Rect(321.0, 114.9, 504.8, 430.9)
    lines = [
        (fitz.Rect(320.2, 53.9, 540.8, 67.7), 10.0, "Gordon, 1997). Figure 6 presents one dialogue from"),
        (fitz.Rect(319.7, 65.8, 353.4, 78.5), 10.0, "domain."),
        (fitz.Rect(330.7, 107.2, 346.8, 116.1), 8.0, "2. U:"),
        (fitz.Rect(331.7, 91.6, 346.3, 100.5), 8.0, "I. C:"),
        (fitz.Rect(488.4, 99.0, 543.2, 108.0), 8.0, "ID,CB,RB,FT, FC,T"),
        (fitz.Rect(488.2, 91.1, 543.0, 100.0), 8.0, "ID,CB,RB,FT, FC,T"),
    ]
    actual = expand_clip_to_nearby_figure_title(base, clip, lines, "above")
    # 图内标签（2. U: / 竖排标签）应收回，正文换行对（Gordon.../domain.）不得收回
    assert actual.y0 <= 91.1, "应收回顶部图内标签"
    assert actual.y0 > 78.5, "不得越过正文换行尾巴"


def test_title_recovery_keeps_kimi_internal_annotation():
    from lib.figure_post import expand_clip_to_nearby_figure_title
    base = fitz.Rect(72.0, 300.0, 540.3, 460.0)
    clip = fitz.Rect(124.4, 354.9, 491.1, 459.5)
    lines = [
        (fitz.Rect(219.1, 339.2, 432.0, 350.0), 8.0,
         "physical cache block (6144 tokens) = 12 prefix-hash blocks"),
        (fitz.Rect(132.0, 361.6, 167.0, 372.4), 8.0, "MLA KV"),
    ]
    actual = expand_clip_to_nearby_figure_title(base, clip, lines, "above")
    assert actual.y0 <= 339.2, "图内小写注释必须收回（Kimi F12）"


def test_recover_label_columns_on_objectless_page():
    from lib.figure_post import recover_clip_label_columns_without_objects
    base = fitz.Rect(309.2, 49.9, 586.0, 430.7)
    clip = fitz.Rect(321.0, 87.1, 504.8, 434.7)
    caption = fitz.Rect(321.6, 436.7, 543.7, 450.5)
    lines = [
        (fitz.Rect(488.4, 99.0, 543.2, 108.0), 8.0, "ID,CB,RB,FT, FC,T"),
        (fitz.Rect(488.2, 91.1, 543.0, 100.0), 8.0, "ID,CB,RB,FT, FC,T"),
        (fitz.Rect(320.2, 300.0, 540.8, 313.0), 10.0, "wide body width line that must not be pulled in x"),
    ]
    actual = recover_clip_label_columns_without_objects(clip, lines, caption, base)
    assert actual.x1 >= 543.0, "右侧应收回竖排标签列"
    assert actual.x1 <= 551.7, "不得越过题注右缘"
    assert actual.x0 == clip.x0 and actual.y0 == clip.y0 and actual.y1 == clip.y1


def test_recover_noop_without_candidates():
    from lib.figure_post import recover_clip_label_columns_without_objects
    base = fitz.Rect(309.2, 49.9, 586.0, 430.7)
    clip = fitz.Rect(321.0, 87.1, 504.8, 434.7)
    caption = fitz.Rect(321.6, 436.7, 543.7, 450.5)
    actual = recover_clip_label_columns_without_objects(clip, [], caption, base)
    assert actual == clip


def test_degenerate_ocr_block_does_not_bound_baseline():
    from types import SimpleNamespace
    from lib.clip_limit import limit_clip_by_text_blocks

    def block(x0, y0, x1, y1, btype, text):
        return SimpleNamespace(
            bbox=fitz.Rect(x0, y0, x1, y1),
            units=[SimpleNamespace(text=text)],
            block_type=btype,
            column=0,
        )

    caption = fitz.Rect(59.0, 275.5, 300.0, 290.0)
    clip = fitz.Rect(26.0, 44.0, 586.0, 269.0)
    blocks = [
        block(88, 88.6, 98, 140.4, "title_h1", "l"),
        block(321, 97.7, 543, 281.4, "paragraph_group",
              "two types of factors are potential relevant contributors to user"),
    ]
    out = limit_clip_by_text_blocks(clip, caption, "above", blocks, gap=6.0)
    assert out.y0 < 100, f"OCR 竖线误读的单字长条不应卡住 baseline：{out}"


# ---------------------------------------------------------------------------
# P2-3: 扫描页方向必须按题注上下两侧的结构墨迹判定，不得写死 above
# ---------------------------------------------------------------------------

def _scan_page_with_graphic(dark_rect, caption_y, width=612, height=792):
    """整页白位图 + 一块深色图形 + 不可见 OCR 题注文字。

    图形只存在于位图里：矢量对象集合为空，整页位图又被页面载体过滤，
    页面因此与真实扫描件一样「对象全无」，方向只能靠像素证据判断。
    """
    with fitz.open() as staging:
        sp = staging.new_page(width=width, height=height)
        sp.draw_rect(fitz.Rect(*dark_rect), color=None, fill=(0, 0, 0))
        pix = sp.get_pixmap(dpi=72, colorspace=fitz.csGRAY, alpha=False)
    doc = fitz.open()
    page = doc.new_page(width=width, height=height)
    page.insert_image(page.rect, pixmap=pix)
    page.insert_text((72, caption_y), "Figure 1: A scanned diagram",
                     fontsize=10, render_mode=3)
    return doc


def test_top_caption_scan_crop_contains_graphic():
    """图形在题注下方时方向必须是 below：写死 above 会把空白裁成 accepted 截图。"""
    from lib.direction import compute_global_anchor
    pattern = re.compile(r"^\s*(?:figure|fig\.?)\s*\d+", re.I)
    doc = _scan_page_with_graphic((150, 400, 460, 620), caption_y=200)
    try:
        assert compute_global_anchor(doc, pattern, is_table=False) == "below"
    finally:
        doc.close()


def test_bottom_caption_scan_crop_still_reads_above():
    """图形在题注上方时仍判 above：新证据不得把常规版面翻面。"""
    from lib.direction import compute_global_anchor
    pattern = re.compile(r"^\s*(?:figure|fig\.?)\s*\d+", re.I)
    doc = _scan_page_with_graphic((150, 120, 460, 340), caption_y=560)
    try:
        assert compute_global_anchor(doc, pattern, is_table=False) == "above"
    finally:
        doc.close()


# ---------------------------------------------------------------------------
# P2-1: 通用列推断的开关必须由「另一侧确有表内单元格」的证据把关
#
# table_spans_both_columns 是本轮新增的判据，用于区分两类长相相同的版面：
#   * 无边框通栏表 —— 右侧单元格与题注侧表内行同高，收窄会把右半张表切掉；
#   * 双栏正文 —— 右栏是与左栏无关的整句，收窄才是正确行为。
# 判 True 时调用方置 infer_columns=False（跳过通用列推断）。
# ---------------------------------------------------------------------------

def _cross_column_lines(far_texts, left_text="0.92"):
    """题注在左栏、右栏为 far_texts 的逐行对。"""
    lines = []
    for i, far in enumerate(far_texts):
        y0 = 120 + i * 22
        lines.append((fitz.Rect(72, y0, 250, y0 + 16), 12, left_text))
        lines.append((fitz.Rect(340, y0, 560, y0 + 16), 12, far))
    return lines


def test_full_width_table_with_wrapped_cells_blocks_generic_column_inference():
    """右侧短单元格与题注侧表内行同高：判为通栏表，必须关掉通用列推断。"""
    from lib.table_refine import table_spans_both_columns
    page = fitz.Rect(0, 0, 595, 842)
    clip = fitz.Rect(26, 93, 569, 613)
    caption = fitz.Rect(72, 71, 289, 87)
    lines = _cross_column_lines(("0.92", "0.87", "0.81", "0.76"))
    assert table_spans_both_columns(clip, caption, page, lines) is True


def test_two_column_body_text_still_allows_generic_column_inference():
    """右栏是完整正文句：不得误判成通栏表，通用列推断必须保持开启。"""
    from lib.table_refine import table_spans_both_columns
    page = fitz.Rect(0, 0, 595, 842)
    clip = fitz.Rect(26, 93, 569, 613)
    caption = fitz.Rect(72, 71, 289, 87)
    prose = ("The evaluation shows that the proposed system outperforms the "
             "baseline on every measured task while using fewer parameters.")
    lines = _cross_column_lines((prose,) * 4)
    assert table_spans_both_columns(clip, caption, page, lines) is False


def test_narrow_caption_column_clip_allows_generic_column_inference():
    """题注栏内的窄框不可能横跨两栏，通用列推断不得被关闭。"""
    from lib.table_refine import table_spans_both_columns
    page = fitz.Rect(0, 0, 595, 842)
    clip = fitz.Rect(26, 93, 400, 613)
    caption = fitz.Rect(72, 71, 289, 87)
    assert table_spans_both_columns(clip, caption, page, []) is False


def test_page_centered_caption_never_marks_cross_column_table():
    """居中题注不偏向任何一栏，没有「题注侧」可言，不得判通栏。"""
    from lib.table_refine import table_spans_both_columns
    page = fitz.Rect(0, 0, 595, 842)
    clip = fitz.Rect(26, 93, 569, 613)
    caption = fitz.Rect(250, 71, 345, 87)
    lines = [(fitz.Rect(340, 120 + i * 22, 560, 136 + i * 22), 12, "0.92")
             for i in range(4)]
    assert table_spans_both_columns(clip, caption, page, lines) is False


_PARADISE_P9_CANDIDATES = (
    Path("/Users/fenix-macmini/Documents/Haier/6-HaierVibeCoding/"
         "2-新需求设计/20260924-分布式唤醒主观体验测试方案/1-参考素材/"
         "PARADISE-口语对话系统评价框架.pdf"),
)


def _write_reconstructed_paradise_page9(pdf_path: Path) -> None:
    """按 PARADISE 第 9 页实测坐标重建：左栏 Table 7 + 右栏重叠正文。"""
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    pix = fitz.Pixmap(fitz.csGRAY, fitz.IRect(0, 0, 612, 792), False)
    pix.clear_with(255)
    page.insert_image(page.rect, pixmap=pix)
    page.insert_text((64, 61), "Fault-Type corresponds to Diagnosis.", fontsize=9)
    rows = [
        (111, "attribute", "possible values"),
        (119, "Circuit-ID (ID)", "RSI 11, RS112"),
        (127, "Correct-Circuit-Behavior (CB)", "Flash-1-7"),
        (135, "Current-Circuit-Behavior (RB)", "Flash-7"),
        (143, "Fault-Type (P-q)", "MissingWire84-99"),
        (151, "Fault-Correction (FC)", "yes, no"),
        (159, "Test (T)", "yes, no"),
    ]
    for y, left, right in rows:
        page.insert_text((71, y), left, fontsize=8)
        page.insert_text((167, y), right, fontsize=8)
    page.insert_text((84, 186), "Table 7: Attribute value matrix, circuit domain",
                     fontsize=10)
    page.insert_text((302, 60), "weights on factors related to performance.", fontsize=9)
    prose = [
        (72, "In addition, this approach is broadly integrative, in-"),
        (83, "corporating aspects of transaction success, concept accu-"),
        (94, "racy, multiple cost measures, and user satisfaction."),
        (104, "In our framework, transaction success is reflected in"),
        (115, "corresponding to dialogues with a P(A) of 1."),
        (126, "Our performance measure also captures information"),
        (136, "similar to concept accuracy, where low concept accuracy"),
        (147, "scores translate into either higher costs for acquiring"),
        (158, "information from the user, or lower scores."),
        (170, "One limitation of the PARADISE approach is that the"),
        (181, "task-based success measure does not reflect that some"),
    ]
    for y, line in prose:
        page.insert_text((302, y), line, fontsize=9)
    page.insert_text((66, 214), "Figure 6 is tagged with the attributes from Table 7.",
                     fontsize=9)
    doc.save(pdf_path)
    doc.close()


def _paradise_page9_pdf(tmp_path: Path) -> Path:
    dest = tmp_path / "paradise_p9.pdf"
    for src in _PARADISE_P9_CANDIDATES:
        if src.is_file():
            with fitz.open(src) as doc, fitz.open() as out:
                out.insert_pdf(doc, from_page=8, to_page=8)
                out.save(dest)
            return dest
    _write_reconstructed_paradise_page9(dest)
    return dest


def test_paradise_page9_table7_stays_in_left_column(tmp_path):
    """PARADISE 第 9 页 Table 7 不得被宽度恢复扩进右栏正文。"""
    from lib.extract_tables import extract_tables

    pdf = _paradise_page9_pdf(tmp_path)
    records = extract_tables(
        str(pdf), str(tmp_path / "images"), dpi=72, global_anchor_table="above",
    )
    table7 = next((item for item in records if item.ident == "7"), None)
    assert table7 is not None, f"未提取到 Table 7: {[r.ident for r in records]}"
    x0, y0, x1, y1 = table7.final_bbox
    assert x1 < 300, f"Table 7 扩进右栏 x1={x1}"
    assert x0 < 80, f"Table 7 左边界丢失 x0={x0}"
    assert 100 <= y0 <= 130, f"Table 7 顶边偏离真表 y0={y0}"
    assert 155 <= y1 <= 190, f"Table 7 底边偏离真表 y1={y1}"
    with fitz.open(pdf) as doc:
        words = doc[0].get_text("words")
    inside = [
        w[4] for w in words
        if (min(w[2], x1) - max(w[0], x0)) > 1 and (min(w[3], y1) - max(w[1], y0)) > 1
    ]
    polluted = [w for w in inside if w.lower() in {
        "integrative", "limitation", "paradise", "satisfaction",
    }]
    assert not polluted, f"右栏正文混入 Table 7: {polluted}"


def test_paradise_page9_width_restore_ignores_right_column_prose():
    """第 9 页实测几何：即使恢复上限被撑成整页宽，右栏长句也不得当丢失单元格。"""
    from lib.table_refine import restore_table_clip_width

    clip = fitz.Rect(59.6, 108.1, 286.2, 169.3)
    wide_base = fitz.Rect(26.0, 93.0, 569.0, 280.0)
    lines = [
        (fitz.Rect(71.0, 110.6, 206.8, 119.6), 8, "attribute possible values"),
        (fitz.Rect(71.0, 118.4, 214.6, 127.7), 8, "Circuit-ID (ID) RSI 11"),
        (fitz.Rect(71.3, 157.1, 185.8, 166.8), 8, "Test (T) yes, no"),
        (fitz.Rect(301.9, 70.5, 520.4, 83.0), 9,
         "corporating aspects of transaction success, concept accuracy"),
        (fitz.Rect(301.9, 81.1, 494.4, 93.6), 9,
         "racy, multiple cost measures, and user satisfaction."),
        (fitz.Rect(302.4, 157.4, 520.8, 169.9), 9,
         "One limitation of the PARADISE approach is that the"),
    ]
    actual = restore_table_clip_width(
        clip, wide_base, table_band_changed=True, text_lines=lines,
    )
    assert actual.x1 < 300, f"右栏正文被当成丢失单元格 x1={actual.x1}"
