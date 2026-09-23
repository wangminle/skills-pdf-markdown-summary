"""20260922 代码审查修复的回归用例（P1/P2/P3 各条一一对应）。

这些用例都是纯单元级：构造最小几何 / 数据，验证被修复的判据本身，
不依赖 benchmark 产物。
"""
from pathlib import Path
import sys

import fitz
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'skills/pdf-markdown-summary/scripts'))
sys.path.insert(0, str(ROOT / 'tests/eval'))


# ---------------------------------------------------------------- P1-1 text_trim

def _line(x0, y0, x1, y1, text, size=10.0):
    return (fitz.Rect(x0, y0, x1, y1), size, text)


def test_adjacent_trim_fires_below_caption():
    """direction='below'：图注在上方，紧贴图注的整行正文应被裁掉。

    修复前近端距离写成 caption.y0 - line.y1，恒为负，邻接判定永不成立。
    """
    from lib.text_trim import trim_clip_head_by_text

    caption = fitz.Rect(60, 80, 500, 92)
    clip = fitz.Rect(50, 98, 550, 400)
    body = _line(60, 100, 540, 112, 'a full width body paragraph line')
    out = trim_clip_head_by_text(
        clip, fitz.Rect(0, 0, 595, 842), caption, 'below', [body], gap=6.0
    )
    assert out.y0 >= body[0].y1


def test_adjacent_trim_fires_above_caption():
    """direction='above'：图注在下方，紧贴图注的整行正文应被裁掉。"""
    from lib.text_trim import trim_clip_head_by_text

    caption = fitz.Rect(60, 420, 500, 432)
    clip = fitz.Rect(50, 100, 550, 410)
    body = _line(60, 396, 540, 408, 'a full width body paragraph line')
    out = trim_clip_head_by_text(
        clip, fitz.Rect(0, 0, 595, 842), caption, 'above', [body], gap=6.0
    )
    assert out.y1 <= body[0].y0


def test_phase_b_trims_figures_but_is_skipped_for_tables():
    """Phase B（近端 24~300pt 正文）对 Figure 生效，对表格由表格保护跳过。

    行全部落在近端下半区、且离图注 >24pt，只会触发 Phase B，不触发 Phase A/C。
    """
    from lib.text_trim import trim_clip_head_by_text_v2

    page = fitz.Rect(0, 0, 595, 842)
    caption = fitz.Rect(60, 430, 500, 442)
    clip = fitz.Rect(50, 150, 550, 425)
    rows = [_line(60, 290 + 14 * i, 540, 302 + 14 * i, f'row {i} cell cell cell')
            for i in range(8)]

    as_figure = trim_clip_head_by_text_v2(
        clip, page, caption, 'above', rows, skip_adjacent_sweep=False
    )
    as_table = trim_clip_head_by_text_v2(
        clip, page, caption, 'above', rows, skip_adjacent_sweep=True
    )
    assert as_figure.y1 < rows[0][0].y0
    assert as_table.y1 == clip.y1


def test_degenerate_trim_never_returns_page_wide_band():
    """Phase B/C 叠加到不可用时只能退回中间结果，不能返回 caption±600 的整页带。"""
    from lib.text_trim import trim_clip_head_by_text_v2

    page = fitz.Rect(0, 0, 595, 842)
    caption = fitz.Rect(60, 740, 500, 752)
    clip = fitz.Rect(26, 472, 569, 735)
    lines = [_line(60, 474 + 13 * i, 540, 485 + 13 * i, f'body sentence number {i}.')
             for i in range(20)]
    out = trim_clip_head_by_text_v2(clip, page, caption, 'above', lines)
    assert out.x0 >= clip.x0 - 0.01 and out.x1 <= clip.x1 + 0.01
    assert out.y0 >= clip.y0 - 0.01 and out.y1 <= clip.y1 + 0.01


# ---------------------------------------------------------------- P1-2 表侧截断

def test_side_cut_text_is_truncation_but_grazing_neighbor_is_not():
    from lib.assess import text_crosses_clip_boundary

    crop = [70.9, 114.2, 541.3, 416.6]
    side_cut = [[500.0, 130.0, 560.0, 141.0]]
    grazing_above = [[72.0, 99.3, 369.1, 120.0]]
    assert text_crosses_clip_boundary(crop, side_cut, min_inside_height_ratio=0.5)
    assert not text_crosses_clip_boundary(crop, grazing_above, min_inside_height_ratio=0.5)


# ------------------------------------------------- 对象截断：路径外框 vs 可见墨迹

def test_object_truncation_requires_visible_ink_outside():
    """框外无墨迹（被 clip path 裁掉的路径、位图白边）不算截断。"""
    from lib.assess import objects_truncated_on_far_side

    final = [100.0, 100.0, 300.0, 200.0]
    search = [50.0, 50.0, 400.0, 400.0]
    obj = [[100.0, 100.0, 300.0, 260.0]]
    assert objects_truncated_on_far_side(final, search, obj, 'above')
    assert not objects_truncated_on_far_side(
        final, search, obj, 'above', ink_probe=lambda _r: False
    )
    assert objects_truncated_on_far_side(
        final, search, obj, 'above', ink_probe=lambda _r: True
    )


def test_detached_object_far_from_clip_is_another_asset():
    """与裁剪框完全不相交且相距很远的对象是同页另一资产，不是被切掉的内容。"""
    from lib.assess import objects_truncated_on_far_side

    final = [57.7, 515.3, 526.4, 734.3]
    search = [40.0, 60.0, 560.0, 740.0]
    neighbour_figure = [[109.4, 197.7, 485.8, 409.7]]
    adjacent = [[109.4, 470.0, 485.8, 510.0]]
    assert not objects_truncated_on_far_side(final, search, neighbour_figure, 'above')
    assert objects_truncated_on_far_side(final, search, adjacent, 'above')


def test_outside_band_thinner_than_tolerance_is_ignored():
    """只擦过边界 2pt 以内的薄条带不参与墨迹探测。"""
    from lib.assess import _outside_bands

    final = (114.8, 188.9, 497.6, 441.9)
    grazing = (95.4, 187.2, 516.7, 438.3)
    bands = _outside_bands(grazing, final)
    assert all(b[3] - b[1] > 2.0 for b in bands)
    assert not any(b[1] < final[1] for b in bands)


def test_ink_probe_masks_text_and_respects_pixmap_origin():
    """文本遮罩要按位图原点换算，否则边缘一列残留会被当成墨迹。"""
    from lib.pixel_detect import make_ink_probe

    doc = fitz.open()
    page = doc.new_page(width=200, height=200)
    text_rect = fitz.Rect(40.5, 40.5, 160.5, 55.5)
    page.insert_textbox(text_rect, 'masked text here', fontsize=11)
    page.draw_rect(fitz.Rect(40.5, 120.5, 160.5, 160.5), color=(0, 0, 0), fill=(0, 0, 0))

    probe = make_ink_probe(page, [(text_rect, 11.0, 'masked text here')])
    assert not probe((40.0, 38.0, 161.0, 58.0))
    assert probe((40.0, 118.0, 161.0, 162.0))
    doc.close()


# ---------------------------------------------------------------- P2-3 markdown 门

def test_missing_status_falls_back_to_review_signals():
    from lib.assess import markdown_insertable
    from lib.quality import STATUS_ACCEPTED, STATUS_REVIEW_REQUIRED

    assert markdown_insertable(STATUS_ACCEPTED) is True
    assert markdown_insertable(STATUS_REVIEW_REQUIRED) is False
    assert markdown_insertable(None) is True
    assert markdown_insertable(None, review_required=True) is False
    assert markdown_insertable(None, warnings=['object_truncation']) is False


# ---------------------------------------------------------------- P2-4 跨页回退

def test_get_best_for_page_does_not_leak_other_pages():
    from lib.models import CaptionIndex
    from test_extraction_status_inventory import _candidate

    index = CaptionIndex(candidates={'figure_3': [
        _candidate('figure', '3', 'Figure 3: Real caption', 7, 90),
    ]})
    assert index.get_best_for_page('figure', '3', 2) is None
    assert index.get_best_for_page('figure', '3', 2, allow_cross_page=True) is not None
    assert index.get_best_for_page('figure', '3', 7) is not None


# ---------------------------------------------------------------- P2-5 layout 分类

@pytest.mark.parametrize('text,expected', [
    ('Table 4: config comparison across runs', 'caption_table'),
    ('Table 5: significant gains', 'caption_table'),
    ('Figure 2: overview', 'caption_figure'),
    ('Fig. 3 pipeline', 'caption_figure'),
])
def test_caption_kind_uses_leading_label_token(text, expected):
    from lib.layout_model import classify_text_types
    from lib.models import EnhancedTextUnit

    unit = EnhancedTextUnit(
        bbox=fitz.Rect(60, 100, 400, 112), text=text, page=0,
        font_name='X', font_size=10.0, font_weight='regular', font_flags=0,
        color=(0, 0, 0), text_type='unknown', confidence=0.0,
        column=-1, indent=60.0, block_idx=0, line_idx=0,
    )
    classify_text_types({0: [unit]}, 10.0, 'X', 595.0)
    assert unit.text_type == expected


# ---------------------------------------------------------------- P2-7 表格补边

def test_table_text_bounds_ignores_figure_caption():
    from lib.table_refine import expand_table_clip_to_text_bounds

    clip = fitz.Rect(100, 200, 400, 300)
    reference = fitz.Rect(60, 150, 500, 360)
    caption = fitz.Rect(100, 310, 400, 322)
    lines = [
        (fitz.Rect(100, 202, 400, 214), 10.0, 'Metric  Value  Value'),
        (fitz.Rect(100, 216, 400, 228), 10.0, 'row a  1.0  2.0'),
        (fitz.Rect(70, 192, 480, 204), 10.0, 'Figure 9: unrelated neighbouring caption'),
    ]
    out = expand_table_clip_to_text_bounds(clip, reference, caption, lines, 'above')
    assert out.x0 >= 99.0


# ---------------------------------------------------------------- P2-8 孤儿页码

def test_orphan_candidates_keep_page_number():
    from lib.pairing import pair_page
    from lib.regions import RegionBBox

    result = pair_page(
        page=12,
        captions=[RegionBBox(60, 100, 400, 112, kind='caption', source='t')],
        contents=[],
        kind='table',
    )
    assert [c.page for c in result.orphan_captions] == [12]


# ---------------------------------------------------------------- P3 组

def test_neighbor_caption_width_floor_is_independent_of_height():
    from lib.clip_limit import limit_clip_by_neighbor_captions

    clip = fitz.Rect(50, 200, 550, 400)
    caption = fitz.Rect(60, 410, 250, 422)
    neighbor = fitz.Rect(310, 410, 500, 422)
    out = limit_clip_by_neighbor_captions(
        clip, caption, 'above', [neighbor], min_height=250.0
    )
    assert out.x1 < clip.x1


def test_acceptance_thresholds_tighten_with_far_coverage():
    from lib.acceptance import adaptive_acceptance_thresholds

    loose = adaptive_acceptance_thresholds(500.0, far_cov=0.0)
    tight = adaptive_acceptance_thresholds(500.0, far_cov=0.7)
    assert tight.height_ratio < loose.height_ratio
    assert tight.object_coverage < loose.object_coverage


def test_draw_rects_marks_alpha_pixmap_in_place():
    from lib.debug_visual import draw_rects_on_pix

    with fitz.open() as doc:
        page = doc.new_page(width=100, height=100)
        pix = page.get_pixmap(alpha=True)
        before = bytes(pix.samples)
        draw_rects_on_pix(pix, [(fitz.Rect(10, 10, 90, 90), (255, 0, 0))], scale=1.0)
        assert bytes(pix.samples) != before


def test_run_id_contains_millisecond_timestamp():
    from lib import output

    import re
    output.set_run_id(None)
    try:
        value = output.get_run_id()
        assert re.fullmatch(r"\d{8}_\d{6}_\d{3}", value)
        assert output.get_run_id() == value  # 同一运行稳定复用
    finally:
        output.set_run_id(None)


def test_eval_gt_keys_are_space_normalized(tmp_path):
    from run_eval import find_gt_files

    doc = tmp_path / 'Qwen3 Omni Technical Report'
    doc.mkdir()
    (doc / 'gt.json').write_text('{}', encoding='utf-8')
    assert list(find_gt_files(tmp_path)) == ['Qwen3_Omni_Technical_Report']


def test_eval_gt_record_missing_ident_raises():
    from keys import normalize_gt_asset

    with pytest.raises(ValueError):
        normalize_gt_asset('doc', {'kind': 'figure', 'caption_page': 1})


def test_eval_boxless_prediction_is_not_counted_twice():
    from metrics import evaluate_document

    gt = [{
        'key': 'doc|figure|1|p1|o1|g-', 'document_id': 'doc', 'kind': 'figure',
        'ident': '1', 'caption_page': 1, 'content_bboxes': [], 'elements': [],
    }]
    preds = [{
        'key': 'doc|figure|1|p1|o1|g-', 'document_id': 'doc', 'kind': 'figure',
        'ident': '1', 'caption_page': 1, 'bboxes': [], 'has_bbox': False,
    }]
    counts = evaluate_document(gt, preds)['metrics']['count_alignment']
    assert counts['n_missing'] == 1
    assert counts['n_extra'] == 0


def test_golden_signatures_keep_duplicate_entries_apart():
    from test_extraction_golden import extract_item_signatures

    data = {'items': [
        {'type': 'table', 'id': '1', 'page': 5, 'continued': True, 'final_bbox': [0, 0, 1, 1]},
        {'type': 'table', 'id': '1', 'page': 5, 'continued': True, 'final_bbox': [2, 2, 3, 3]},
    ]}
    assert len(extract_item_signatures(data, from_golden=True)) == 2
