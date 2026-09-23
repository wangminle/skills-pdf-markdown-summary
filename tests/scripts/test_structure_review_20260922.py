"""真实 PDF 的独立内容完整性验收；坐标/文字来自原页人工复核，非提取结果生成。"""
from pathlib import Path
import json
import sys

import fitz
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'skills/pdf-markdown-summary/scripts'))
from lib.assess import objects_truncated_on_far_side, reconcile_inventory, ExpectedCaption
from lib.models import AttachmentRecord
from test_extraction_golden import GoldenSpec, ensure_extracted_index, _resolve_golden_paths


@pytest.fixture(scope='module')
def extracted():
    cache = {}
    def load(stem):
        if stem not in cache:
            spec = GoldenSpec(stem + '.pdf', 0, 0)
            ok, message = ensure_extracted_index(spec)
            assert ok, message
            cache[stem] = json.loads(_resolve_golden_paths(spec)[2].read_text())['items']
        return cache[stem]
    return load


def _figure(items, ident):
    return next(x for x in items if x['type'] == 'figure' and x['id'] == str(ident))


def _assert_text_inside(stem, item, text):
    with fitz.open(ROOT / 'tests/basic-benchmark' / (stem + '.pdf')) as doc:
        rects = doc[item['page']-1].search_for(text)
    assert rects, f'原页未找到验收文字 {text}'
    crop = fitz.Rect(item['final_bbox']) + (-1, -1, 1, 1)
    assert all(crop.contains(r) for r in rects), (text, item['final_bbox'], rects)


def test_kimi_f1_keeps_right_bar_and_scores(extracted):
    stem = '2607.24653v2-Kimi-K3'
    item = _figure(extracted(stem), 1)
    # 人工复核：右上子图的分数86.6在x=501.5..509.3，不能只保留半根柱。
    assert item['final_bbox'][2] >= 509.3
    assert item['final_bbox'][0] <= 95.0


@pytest.mark.parametrize('ident,text', [
    (12, 'physical cache block (6144 tokens)'),
    (14, 'Speedup vs. FLA Triton Baseline'),
    (14, 'Claude Fable 5 +57.1%'),
])
def test_kimi_keeps_internal_text(extracted, ident, text):
    stem = '2607.24653v2-Kimi-K3'
    _assert_text_inside(stem, _figure(extracted(stem), ident), text)


def test_kimi_f14_excludes_running_header(extracted):
    item = _figure(extracted('2607.24653v2-Kimi-K3'), 14)
    # 原页运行页眉位于 y=24.9..36.9，图形主体从 y=59.9 开始。
    assert item['final_bbox'][1] >= 50.0


@pytest.mark.parametrize('text', ['all orders', 'small orders'])
def test_kearns_keeps_subplot_titles(extracted, text):
    stem = 'KearnsNevmyvakaHFTRiskBooks'
    item = _figure(extracted(stem), 7)
    _assert_text_inside(stem, item, text)
    assert item['final_bbox'][1] <= 87.0  # 包含独立的指数4及倍率标记


def test_gemini_table_11_includes_all_four_pages(extracted):
    parts = [x for x in extracted('gemini_v2_5_report') if x['type']=='table' and x['id']=='11']
    assert {x['page'] for x in parts} == {60, 61, 62, 63}
    for item in parts:
        assert item['continued'] == (item['page'] != 60)
        assert item['file']
    _assert_text_inside('gemini_v2_5_report', next(x for x in parts if x['page']==60), 'LiveCodeBench')


@pytest.mark.parametrize('bbox', [[0,0,100,60], [0,0,60,100]])
def test_large_partial_object_is_truncated(bbox):
    assert objects_truncated_on_far_side(bbox, [0,0,100,100], [[0,0,100,100]], 'below')


def test_inventory_empty_placeholder_does_not_satisfy_expected():
    expected = [ExpectedCaption('figure','1',1,'Figure 1: Demo',100,None)]
    record = AttachmentRecord('figure','1',1,'Figure 1: Demo','',status='rejected')
    assert reconcile_inventory(expected,[record]).missing == expected


def test_horizontal_recovery_ignores_vertical_page_watermark():
    from lib.clip_limit import refine_clip_x_range
    clip = fitz.Rect(20,200,580,600)
    result = refine_clip_x_range(
        clip, fitz.Rect(200,605,400,615), 'above', [], [fitz.Rect(100,250,470,580)],
        fitz.Rect(0,0,600,800), x_margin=10,
        text_lines=[(fitz.Rect(25,210,40,550),18,'arXiv:example'),
                    (fitz.Rect(460,270,515,280),9,'86.6')],
    )
    assert result.x0 >= 80
    assert result.x1 >= 515


def test_far_side_noise_ignores_logo_above_header_separator():
    from lib.figure_post import trim_far_side_noise_before_content
    clip = fitz.Rect(20, 0, 580, 250)
    candidate = fitz.Rect(60, 18, 550, 245)
    result = trim_far_side_noise_before_content(
        clip,
        candidate,
        'above',
        [
            fitz.Rect(225, 25, 236, 36),  # tiny running-header logo
        ],
        [
            fitz.Rect(130, 64, 477, 218),  # figure body
        ],
        [
            (fitz.Rect(239, 25, 385, 37), 10, 'Kimi K3: Open Frontier Intelligence'),
            (fitz.Rect(461, 26, 540, 37), 9, 'TECHNICAL REPORT'),
        ],
        pad=8,
    )
    assert result.y0 == pytest.approx(56.0)


@pytest.mark.parametrize('marker,header,expected', [
    ('Continued on next page','Metric', [0]),
    ('Unrelated text','Metric', []),
    ('Continued on next page','Different header', []),
])
def test_continuation_requires_marker_and_matching_header(marker,header,expected):
    from lib.table_continuation import preceding_table_parts
    with fitz.open() as doc:
        for n in range(2):
            page = doc.new_page(width=600,height=800)
            for y in [100,125,160,220]:page.draw_line((70,y),(530,y))
            page.insert_text((75,117),header if n==0 else 'Metric',fontsize=10)
            page.insert_text((320,117),'Value',fontsize=10)
            page.insert_text((75,145),'Data row',fontsize=10)
            if n==0:page.insert_text((360,238),marker,fontsize=10)
        rec = AttachmentRecord('table','1',2,'Table 1: Data','x.png',final_bbox=[67,97,533,223])
        assert [n for n,_clip in preceding_table_parts(doc,rec)] == expected


def test_debug_visual_handles_captionless_continuation(tmp_path):
    from lib.debug_visual import save_debug_visualization,create_debug_stage
    with fitz.open() as doc:
        page=doc.new_page(width=200,height=200)
        files=save_debug_visualization(page,str(tmp_path),11,60,
            stages=[create_debug_stage('final',fitz.Rect(20,20,180,180))],caption_rect=None,kind='table')
    assert len(files)==2
    assert 'none' in (tmp_path/files[1]).read_text()


def test_text_cut_at_side_requires_review():
    from lib.assess import text_crosses_clip_boundary
    assert text_crosses_clip_boundary([100,100,400,300], [[380,160,430,171]])
    assert not text_crosses_clip_boundary([100,100,450,300], [[380,160,430,171]])


def test_inventory_strict_mode_checks_file_exists():
    expected=[ExpectedCaption('figure','1',1,'Figure 1: Demo',100,None)]
    record=AttachmentRecord('figure','1',1,'Figure 1: Demo','/nonexistent/pdf-test.png')
    assert reconcile_inventory(expected,[record],verify_files=True).missing == expected


def test_inventory_uses_real_caption_even_if_reference_has_higher_score():
    from test_extraction_status_inventory import _candidate
    from lib.models import CaptionIndex
    from lib.assess import expected_captions_from_index
    index=CaptionIndex(candidates={'table_6':[
        _candidate('table','6','Table 6. Also, we evaluate different modes',0,90),
        _candidate('table','6','Table 6: Evaluation results',0,50),
    ]})
    found=expected_captions_from_index(index)
    assert len(found)==1
    assert found[0].text=='Table 6: Evaluation results'


def test_title_recovery_does_not_follow_neighbor_column():
    from lib.figure_post import expand_clip_to_nearby_figure_title
    result=expand_clip_to_nearby_figure_title(
        fitz.Rect(30,100,570,500),fitz.Rect(50,300,280,490),
        [(fitz.Rect(310,280,560,292),10,'The neighboring column'),
         (fitz.Rect(310,264,560,276),10,'continues on the preceding line')], 'above')
    assert result.y0==300


def test_recovered_table_fragment_is_not_accepted_with_cut_text(tmp_path):
    from lib.table_continuation import recover_table_continuations
    with fitz.open() as doc:
        for n in range(2):
            page=doc.new_page(width=600,height=800)
            for y in [100,125,160,220]:page.draw_line((70,y),(530,y))
            page.insert_text((75,117),'Metric',fontsize=10)
            page.insert_text((320,117),'Value',fontsize=10)
            page.insert_text((515,145),'Overflow value',fontsize=10)
            if n==0:page.insert_text((360,238),'Continued on next page',fontsize=10)
        anchor=AttachmentRecord('table','1',2,'Table 1: Data','x.png',final_bbox=[67,97,533,223])
        records=[anchor]
        recover_table_continuations(doc,records,str(tmp_path),dpi=72)
        part=next(x for x in records if x.page==1)
        assert part.status=='review_required'
        assert 'object_truncation' in part.warnings


def test_title_recovery_does_not_restore_body_sentence():
    from lib.figure_post import expand_clip_to_nearby_figure_title
    result=expand_clip_to_nearby_figure_title(
        fitz.Rect(26,260,586,650), fitz.Rect(70,319,540,646),
        [(fitz.Rect(72,297,490,309),10,'Fable 5, at roughly half of the latter’s cost. Figure 13 summarizes the comparison.')], 'above')
    assert result.y0==319


def test_kimi_f13_keeps_plots_without_body(extracted):
    item=_figure(extracted('2607.24653v2-Kimi-K3'),13)
    assert 315 <= item['final_bbox'][1] <= 322


@pytest.mark.parametrize('ident,min_top', [(9,117),(13,425),(18,548),(22,138)])
def test_gpt_title_recovery_excludes_wrapped_body(extracted,ident,min_top):
    item=_figure(extracted('gpt-5-system-card'),ident)
    assert item['final_bbox'][1] >= min_top
