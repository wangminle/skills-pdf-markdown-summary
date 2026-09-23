"""剩余审查问题：边界、续页、失败重试及输出清理。"""
import json
from pathlib import Path
from types import SimpleNamespace
import sys
import fitz
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'skills/pdf-markdown-summary/scripts'))


def test_prune_preserves_new_and_replaced_files(tmp_path):
    from lib.output import snapshot_prunable_images, prune_unindexed_images
    stale=tmp_path/'Figure_old.png';stale.write_bytes(b'old')
    replaced=tmp_path/'Table_replaced.png';replaced.write_bytes(b'old')
    before=snapshot_prunable_images(str(tmp_path))
    fresh=tmp_path/'Figure_new.png';fresh.write_bytes(b'new')
    replaced.write_bytes(b'changed after snapshot')
    index=tmp_path/'index.json';index.write_text(json.dumps({'items':[]}))
    assert prune_unindexed_images(out_dir=str(tmp_path),index_json_path=str(index),preexisting=before)==1
    assert fresh.exists() and replaced.exists() and not stale.exists()


def test_prune_without_snapshot_is_non_destructive(tmp_path):
    from lib.output import prune_unindexed_images
    p=tmp_path/'Figure_new.png';p.write_bytes(b'new')
    index=tmp_path/'index.json';index.write_text('{"items":[]}')
    assert prune_unindexed_images(out_dir=str(tmp_path),index_json_path=str(index))==0
    assert p.exists()


def test_table_padding_stays_inside_max_expand():
    from lib.table_refine import expand_table_clip_to_text_bounds
    clip=fitz.Rect(100,100,300,200)
    line=(fitz.Rect(95,140,500,150),10,'Metric 123')
    result=expand_table_clip_to_text_bounds(clip,fitz.Rect(0,0,600,700),fitz.Rect(100,210,300,220),[line],'above',max_expand=8)
    assert result.x1<=308 and result.x0>=92


def test_short_title_support_is_mirrored():
    from lib.clip_limit import limit_clip_by_text_blocks
    def block(rect,kind,text):return SimpleNamespace(bbox=fitz.Rect(rect),block_type=kind,units=[SimpleNamespace(text=text)])
    # In the above direction candidates are sorted in descending page order.
    clip=fitz.Rect(0,100,600,600);caption=fitz.Rect(0,610,600,622)
    blocks=[block((100,400,280,412),'title_1','Accuracy'),block((100,370,280,382),'text','Model A 91 92')]
    out=limit_clip_by_text_blocks(clip,caption,'above',blocks)
    assert out.y0==clip.y0


def test_continuation_ignores_grazing_neighbor(tmp_path,monkeypatch):
    from lib import table_continuation as tc
    from lib.models import AttachmentRecord
    monkeypatch.setattr(tc,'preceding_table_parts',lambda doc,rec:[(0,fitz.Rect(70,100,530,220))])
    monkeypatch.setattr(tc,'collect_text_lines',lambda data:[(fitz.Rect(80,91,300,102),10,'neighbor row')])
    with fitz.open() as doc:
        doc.new_page(width=600,height=800);doc.new_page(width=600,height=800)
        records=[AttachmentRecord('table','1',2,'Table 1: Data','x.png',final_bbox=[70,100,530,220])]
        tc.recover_table_continuations(doc,records,str(tmp_path),dpi=72)
        assert next(r for r in records if r.page==1).status=='accepted'


def test_partial_near_side_remains_truncation():
    from lib.assess import objects_truncated_on_far_side
    assert objects_truncated_on_far_side([0,100,100,200],[0,0,100,300],[[0,80,100,150]],'below')
    assert not objects_truncated_on_far_side([0,100,100,200],[0,0,100,300],[[0,70,100,95]],'below')


@pytest.mark.parametrize('kind',['figure','table'])
def test_render_failure_allows_same_id_on_later_page(tmp_path,monkeypatch,kind):
    from lib.extract_figures import extract_figures
    from lib.extract_tables import extract_tables
    pdf=tmp_path/'retry.pdf'
    with fitz.open() as doc:
        for _ in range(2):
            page=doc.new_page(width=600,height=800)
            page.draw_rect(fitz.Rect(100,100,500,220),color=(0,0,0))
            page.insert_text((100,250),f'{kind.title()} 1: Results',fontsize=10)
        doc.save(pdf)
    original=fitz.Pixmap.save;attempts=[]
    def save(pix,path,*a,**kw):
        attempts.append(path)
        if len(attempts)==1:raise OSError('simulated render failure')
        return original(pix,path,*a,**kw)
    monkeypatch.setattr(fitz.Pixmap,'save',save)
    run=extract_figures if kind=='figure' else extract_tables
    records=run(str(pdf),str(tmp_path),dpi=72,allow_continued=False,autocrop=False,text_trim=False,smart_caption_detection=False)
    assert len(records)==1 and records[0].page==2 and not records[0].continued


@pytest.mark.parametrize('direction',['above','below'])
def test_table_band_assessment_stays_in_baseline(direction):
    from lib.table_refine import table_remainder_is_open
    crop=fitz.Rect(50,400,550,500);baseline=fitz.Rect(50,350,550,550)
    distant=[(fitz.Rect(80,y,200,y+10),10,'x = 123') for y in ([150,170,190] if direction=='above' else [650,670,690])]
    assert not table_remainder_is_open(crop,baseline,distant,direction)
    near=[(fitz.Rect(80,y,200,y+8),10,'A 123') for y in ([354,367,380] if direction=='above' else [505,520,535])]
    assert table_remainder_is_open(crop,baseline,near,direction)


def test_prune_invalid_index_preserves_snapshot(tmp_path):
    from lib.output import snapshot_prunable_images,prune_unindexed_images
    image=tmp_path/'Figure_old.png';image.write_bytes(b'old')
    before=snapshot_prunable_images(str(tmp_path));index=tmp_path/'index.json';index.write_text('{broken')
    assert prune_unindexed_images(out_dir=str(tmp_path),index_json_path=str(index),preexisting=before)==0
    assert image.exists()


def test_prune_keeps_referenced_snapshot_file(tmp_path):
    from lib.output import snapshot_prunable_images,prune_unindexed_images
    image=tmp_path/'Figure_old.png';image.write_bytes(b'old')
    before=snapshot_prunable_images(str(tmp_path));index=tmp_path/'index.json';index.write_text(json.dumps({'items':[{'file':image.name}]}))
    assert prune_unindexed_images(out_dir=str(tmp_path),index_json_path=str(index),preexisting=before)==0
    assert image.exists()
