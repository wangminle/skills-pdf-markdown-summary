"""表格尾注应保留，紧随其后的正文不应被带入。"""
from pathlib import Path
import sys
import fitz
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'skills/pdf-markdown-summary/scripts'))


def test_deepseek_table5_note_is_kept_without_following_list():
    from lib.table_refine import expand_clip_to_table_notes,trim_table_clip_far_side_body
    from lib.extract_helpers import collect_text_lines
    root=Path(__file__).resolve().parents[2]
    with fitz.open(root/'tests/basic-benchmark/DeepSeek_V41_Tech_Report.pdf') as doc:
        lines=collect_text_lines(doc[47].get_text('dict'))
    clip=fitz.Rect(143.8,103.8,451.5,156.4);caption=fitz.Rect(116.2,85.5,478.8,97.6)
    out=expand_clip_to_table_notes(clip,lines)
    note=next(r for r,_,t in lines if t.startswith('Note. Average'))
    assert out.contains(note) and out.y1<180
    assert trim_table_clip_far_side_body(out,caption,lines,'below')==out


def test_table_note_continuation_stops_before_body():
    from lib.table_refine import expand_clip_to_table_notes
    clip=fitz.Rect(100,100,400,200)
    lines=[(fitz.Rect(105,202,390,210),8,'Note. Scores are computed from the'),
           (fitz.Rect(105,212,390,220),8,'unrounded measurements.'),
           (fitz.Rect(70,232,520,244),11,'This is the following body paragraph.')]
    out=expand_clip_to_table_notes(clip,lines)
    assert 220<=out.y1<232


def test_distant_or_unaligned_note_is_not_attached():
    from lib.table_refine import expand_clip_to_table_notes
    clip=fitz.Rect(100,100,400,200)
    for rect in [fitz.Rect(105,235,390,243),fitz.Rect(420,202,590,210)]:
        assert expand_clip_to_table_notes(clip,[(rect,8,'Note. Unrelated note.')])==clip


def test_exported_deepseek_table5_contains_note():
    import json
    from test_extraction_golden import GoldenSpec,ensure_extracted_index,_resolve_golden_paths
    spec=GoldenSpec('DeepSeek_V41_Tech_Report.pdf',0,0)
    ok,message=ensure_extracted_index(spec)
    assert ok,message
    data=json.loads(_resolve_golden_paths(spec)[2].read_text())
    item=next(x for x in data['items'] if x['type']=='table' and x['id']=='5')
    assert 165.6 <= item['final_bbox'][3] < 180
    assert item['status']=='accepted'


def test_deepseek_table4_mixed_font_note_is_complete():
    from lib.table_refine import expand_clip_to_table_notes,trim_table_clip_far_side_body
    from lib.extract_helpers import collect_text_lines
    root=Path(__file__).resolve().parents[2]
    with fitz.open(root/'tests/basic-benchmark/DeepSeek_V41_Tech_Report.pdf') as doc:
        lines=collect_text_lines(doc[34].get_text('dict'))
    clip=fitz.Rect(66.1,334,529.3,393.7)
    out=expand_clip_to_table_notes(clip,lines)
    assert 444.6<=out.y1<453
    assert trim_table_clip_far_side_body(out,fitz.Rect(70,300,525,325),lines,'below')==out


def test_exported_qwen_lettered_notes_include_a_b_c_to_last_line():
    """Qwen T6/T17 的 a/b/c 尾注必须随表格图片完整导出。"""
    import json
    from test_extraction_golden import GoldenSpec, ensure_extracted_index, _resolve_golden_paths

    spec=GoldenSpec('2509.17765v1-Qwen3-Omni Technical Report.pdf',0,0)
    ok,message=ensure_extracted_index(spec)
    assert ok,message
    data=json.loads(_resolve_golden_paths(spec)[2].read_text())
    for ident,page,min_bottom,max_bottom in (
        ('6',10,773,785),
        ('17',17,472,485),
    ):
        item=next(x for x in data['items'] if x['type']=='table' and x['id']==ident and x['page']==page)
        assert min_bottom<=item['final_bbox'][3]<max_bottom, (ident,item['final_bbox'])
        assert item['status']=='accepted' and not item['warnings']
