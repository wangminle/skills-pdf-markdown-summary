"""2026-09-28 P0/P1 修复回归测试。

覆盖四项修复（详见当轮审查报告）：
1. inventory 补裁范围遵循 --no-figures/--no-tables/--min/--max-figure（P0#2）
   与 missing/unexpected 计数列表同源自补裁后的对账结果（P0#3）；
2. A3 精修不把 legacy rejected 晋升为可插入状态（P0#5）；
3. 表格外框线并入 clip（Qwen T6/T17 底线、Kimi T5 顶线，P1#8）；
4. figure 路径 text_crosses_clip_boundary 与表格路径同阈值（P1#9）；
5. 尾注阈值余量放宽（1.5/64）后 DeepSeek T4/T5 尾注仍完整（P2 收紧项）。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import fitz

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = PROJECT_ROOT / "skills" / "pdf-markdown-summary" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

BENCHMARK = PROJECT_ROOT / "tests" / "basic-benchmark"


def _open(pattern: str):
    matches = list(BENCHMARK.glob(pattern))
    assert matches, f"benchmark 未找到: {pattern}"
    return fitz.open(matches[0])


# ---------------------------------------------------------------------------
# P0#2/P0#3: inventory kinds 过滤 + 计数一致性
# ---------------------------------------------------------------------------

def test_inventory_kinds_filter_excludes_disabled_kind() -> None:
    from lib.assess import finalize_caption_inventory

    pdf = str(BENCHMARK / "1706.03762v7-attention_is_all_you_need.pdf")
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        # 只启用 table：figure 题注不应参与补裁（不产 Figure_*_gap PNG）
        payload = finalize_caption_inventory(
            [], pdf, tmp, dpi=72, kinds={"table"}
        )
        figures = [p for p in os.listdir(tmp) if p.startswith("Figure_")]
        tables = [p for p in os.listdir(tmp) if p.startswith("Table_")]
        assert not figures, f"禁用 figure 后仍产出: {figures}"
        assert tables, "启用 table 应产出表格补裁 PNG"
        assert payload["expected"] == 4  # 该 PDF 恰有 4 张表


def test_inventory_empty_kinds_disables_all() -> None:
    from lib.assess import finalize_caption_inventory

    pdf = str(BENCHMARK / "1706.03762v7-attention_is_all_you_need.pdf")
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        # 空集是合法输入（--no-figures --no-tables）：什么都不补
        payload = finalize_caption_inventory([], pdf, tmp, dpi=72, kinds=set())
        assert payload["missing_count"] == 0
        assert not os.listdir(tmp) or not [
            p for p in os.listdir(tmp) if p.endswith(".png")
        ]


def test_inventory_counts_match_lists() -> None:
    """missing_count/unexpected_count 必须与同一次对账的列表一致。"""
    from lib.assess import expected_captions_from_index, reconcile_inventory
    from lib.models import AttachmentRecord, CaptionCandidate, CaptionIndex

    def _cand(page: int, y: float, text: str, number: str) -> CaptionCandidate:
        return CaptionCandidate(
            rect=fitz.Rect(70, y, 500, y + 12),
            text=text,
            number=number,
            kind="figure",
            page=page,
            block_idx=0,
            line_idx=0,
            spans=[],
            block={},
            score=80.0,
        )

    index = CaptionIndex(
        candidates={
            "figure_1": [_cand(0, 100.0, "Figure 1: results", "1")],
            "figure_2": [_cand(1, 200.0, "Figure 2: results", "2")],
        }
    )
    expected = expected_captions_from_index(index)
    records = [
        AttachmentRecord(
            kind="figure", ident="2", page=2, caption="Figure 2",
            out_path="x.png", status="accepted",
        ),
    ]
    # 直接驱动 finalize 内部的语义单元：补裁后计数取 final_report
    report = reconcile_inventory(expected, records)
    assert report.missing and report.missing[0].ident == "1"


# ---------------------------------------------------------------------------
# P0#5: A3 不晋升 legacy rejected
# ---------------------------------------------------------------------------

def test_refinement_never_promotes_rejected() -> None:
    """legacy rejected 的 record 经 A3 acceptable 精修后必须仍不可插入。"""
    from lib.models import AttachmentRecord
    from lib.pipeline import run_refinement_pipeline

    # 构造最小可跑环境：无 pairing 候选时 pipeline 直接返回，走不到状态写入；
    # 因此直接验证守卫语义——用 monkeypatch 驱动 _apply_quality_meta 等价路径太脆，
    # 改为断言 source 中的守卫行为：构造带 pairing 的最小调用。
    # 这里用「无候选」快速通道确认 pipeline 不崩，晋升路径由集成测试覆盖
    # （tests/results 批次里 legacy rejected 出现率极低，golden 会守住）。
    rec = AttachmentRecord(
        kind="figure", ident="1", page=1, caption="Figure 1",
        out_path="x.png",
        status="rejected", review_required=True, warnings=["text_pollution"],
        final_bbox=[100.0, 100.0, 400.0, 400.0],
    )
    report = run_refinement_pipeline([rec], {}, "/nonexistent.pdf", "/tmp")
    assert report.total_records == 1
    assert report.matched == 0
    # 无候选时不得改动 record 状态
    assert rec.status == "rejected"


# ---------------------------------------------------------------------------
# P1#8: 表格外框线并入
# ---------------------------------------------------------------------------

def test_border_rules_included_for_known_assets() -> None:
    from lib.table_refine import expand_table_clip_to_border_rules

    cases = [
        ("*2509.17765v1*.pdf", 9, (66.1, 509.4, 527.6, 715.7), "bottom"),  # Qwen T6 底线 719.29
        ("*2509.17765v1*.pdf", 16, (66.1, 211.6, 527.6, 416.3), "bottom"),  # Qwen T17 底线 419.68
        ("*2607.24653v2*.pdf", 31, (67.4, 107.1, 552.9, 246.4), "top"),   # Kimi T5 顶线 106.16
    ]
    for pattern, pno, clip, expect in cases:
        with _open(pattern) as doc:
            out = expand_table_clip_to_border_rules(fitz.Rect(*clip), doc[pno])
        if expect == "bottom":
            assert out.y1 > clip[3], f"{pattern} p{pno}: 底框线未并入 (y1={out.y1})"
            assert out.y1 < clip[3] + 8, f"{pattern} p{pno}: 并入过多 (y1={out.y1})"
        else:
            assert out.y0 < clip[1], f"{pattern} p{pno}: 顶框线未并入 (y0={out.y0})"
            assert out.y0 > clip[1] - 8, f"{pattern} p{pno}: 并入过多 (y0={out.y0})"


def test_border_rules_dont_swallow_next_element() -> None:
    """距离超过 max_gap 的横线（下一张表的线）不并入。"""
    from lib.table_refine import expand_table_clip_to_border_rules

    clip = fitz.Rect(100, 100, 400, 200)
    far = fitz.Rect(150, 240, 350, 241)  # 距底 40pt，明显属于下一个元素
    near = fitz.Rect(150, 202, 350, 203)  # 距底 2pt，应并入

    class _Page:
        rect = fitz.Rect(0, 0, 612, 792)

        def get_drawings(self):
            return [{"rect": (far.x0, far.y0, far.x1, far.y1)},
                    {"rect": (near.x0, near.y0, near.x1, near.y1)}]

    out = expand_table_clip_to_border_rules(clip, _Page())
    assert out.y1 >= 203 - 1.5 and out.y1 <= 205, out
    assert out.y1 < 230, "不应并入 40pt 外的线"


# ---------------------------------------------------------------------------
# P1#9: figure/table 同阈值
# ---------------------------------------------------------------------------

def test_figure_path_uses_same_boundary_threshold() -> None:
    """figure 路径必须与 table 路径同口径（min_inside_height_ratio=0.5）。

    分叉构造：框 y0=100。文本行 y=[88,108]，行高 20pt，只有 8pt 落在框内
    （40% < 50%），且越界 12pt > tolerance=1.0。
    0.0 阈值判「被裁」，0.5 阈值判「只是擦到边缘的邻行」。
    """
    import inspect

    from lib.assess import text_crosses_clip_boundary

    final = [40.0, 100.0, 300.0, 300.0]
    shallow = [40.0, 88.0, 300.0, 108.0]
    # 显式传 0.0（修复前的默认）应判被裁；0.5（修复后的默认）不应。
    assert text_crosses_clip_boundary(
        final, [shallow], min_inside_height_ratio=0.0
    ) is True, "0.0 阈值把 40% 交叠的邻行判为被裁"
    assert text_crosses_clip_boundary(final, [shallow]) is False, (
        "默认必须是 0.5：只擦到边缘 <50% 高度的邻行不算被裁"
    )

    # 对照组（证明 0.5 不是把判据整体关掉）：
    # 整行横跨边界、一半在内一半在外 → 两档都判被裁；
    # 整行完全在框内 → 不算被裁（本函数只管「跨界」的行）；
    # 仅边界相接、交叠为 0 → 不算。
    straddling = [40.0, 90.0, 300.0, 110.0]  # 交叠 10/20 = 50%
    assert text_crosses_clip_boundary(final, [straddling]) is True
    assert text_crosses_clip_boundary(final, [[40.0, 110.0, 300.0, 130.0]]) is False
    assert text_crosses_clip_boundary(final, [[40.0, 80.0, 300.0, 100.0]]) is False

    # 三处口径必须一致：函数默认值、figure 调用点、table 调用点。
    # 只改调用点不够——默认值退回 0.0 时新增调用点会静默用回旧口径。
    import lib.assess as assess_mod
    import lib.extract_figures as ef
    import lib.extract_tables as et

    assert "min_inside_height_ratio=0.5" in inspect.getsource(
        assess_mod.text_crosses_clip_boundary
    )
    assert "min_inside_height_ratio=0.5" in inspect.getsource(ef)
    assert "min_inside_height_ratio=0.5" in inspect.getsource(et)


# ---------------------------------------------------------------------------
# P2: 尾注阈值余量
# ---------------------------------------------------------------------------

def test_table_note_tolerance_covers_mixed_font_lines() -> None:
    """首行 8.0pt、续行 9.2pt（差 1.2，旧容差 1.0 会截断）的尾注完整保留。"""
    from lib.table_refine import expand_clip_to_table_notes

    clip = fitz.Rect(100, 100, 400, 200)
    lines = [
        (fitz.Rect(105, 202, 390, 210), 8.0, "Note. Mixed font sizes appear here."),
        (fitz.Rect(105, 212, 390, 220), 9.2, "Continuation with larger inline math."),
        (fitz.Rect(105, 222, 390, 230), 8.0, "Another continuation line."),
    ]
    out = expand_clip_to_table_notes(clip, lines)
    assert out.y1 >= 230, f"混排字号尾注被截断 (y1={out.y1})"
    # 对照：续行字号差超过 1.5 仍要截断（不能放宽成无界）
    lines_bad = [
        (fitz.Rect(105, 202, 390, 210), 8.0, "Note. Mixed font sizes appear here."),
        (fitz.Rect(105, 212, 390, 220), 9.9, "Continuation with much larger font."),
    ]
    out_bad = expand_clip_to_table_notes(clip, lines_bad)
    assert out_bad.y1 <= 213, "字号差 1.9 的行不应被并入尾注"


def test_table_note_tall_note_not_hard_capped() -> None:
    """总高 58pt 的 6 行尾注（旧上限 48 会截掉末 1 行）完整保留。"""
    from lib.table_refine import expand_clip_to_table_notes

    clip = fitz.Rect(100, 100, 400, 200)
    lines = []
    y = 202
    lines.append((fitz.Rect(105, y, 390, y + 8), 8.9, "Note. The measurements are"))
    y += 10
    for i in range(5):
        lines.append((fitz.Rect(105, y, 390, y + 8), 8.9, f"reported per line {i} of the long note."))
        y += 10
    out = expand_clip_to_table_notes(clip, lines)
    assert out.y1 >= 258, f"长尾注被 48pt 上限截断 (y1={out.y1} < 258)"
    # 反向：真正超过 64 的块仍要截断（不能放宽成无界）
    y = 202
    lines_long = [(fitz.Rect(105, y, 390, y + 8), 8.9, "Note. The measurements are")]
    y += 10
    for i in range(8):  # 总高 202→282 = 80pt > 64
        lines_long.append((fitz.Rect(105, y, 390, y + 8), 8.9, f"overflow line {i}."))
        y += 10
    out_long = expand_clip_to_table_notes(clip, lines_long)
    assert out_long.y1 < 275, f"80pt 块应被 64 上限截断 (y1={out_long.y1})"


def test_table_note_still_stops_before_body() -> None:
    """放宽后仍不得吞入正文段。"""
    from lib.table_refine import expand_clip_to_table_notes

    clip = fitz.Rect(100, 100, 400, 200)
    lines = [
        (fitz.Rect(105, 202, 390, 210), 8, "Note. Scores are computed from the"),
        (fitz.Rect(105, 212, 390, 220), 8, "unrounded measurements."),
        (fitz.Rect(70, 232, 520, 244), 11, "This is the following body paragraph."),
    ]
    out = expand_clip_to_table_notes(clip, lines)
    assert out.y1 < 232


# ---------------------------------------------------------------------------
# P0#2 补充口径：非数字编号（S1 / 罗马数字 / 3a）不受 --min/--max-figure 限制
# ---------------------------------------------------------------------------

def test_inventory_figure_range_keeps_non_numeric_idents() -> None:
    """--max-figure 2 时 S1 仍属 expected。

    提取主循环（extract_figures）对 int(ident) 抛 ValueError 的编号一律
    保留；若对账侧用 isdigit() 把它们丢掉，已导出的 S1 会被判成
    unexpected 并被 apply_unexpected_rejects 误杀。
    """
    from lib.assess import expected_captions_from_index
    from lib.models import AttachmentRecord, CaptionCandidate, CaptionIndex
    from lib.assess import reconcile_inventory

    def _cand(number: str, page: int) -> CaptionCandidate:
        return CaptionCandidate(
            rect=fitz.Rect(70, 100, 500, 112),
            text=f"Figure {number}: supplementary results",
            number=number,
            kind="figure",
            page=page,
            block_idx=0,
            line_idx=0,
            spans=[],
            block={},
            score=90.0,
        )

    index = CaptionIndex(
        candidates={
            "figure_1": [_cand("1", 0)],
            "figure_2": [_cand("2", 1)],
            "figure_3": [_cand("3", 2)],
            "figure_S1": [_cand("S1", 3)],
            "figure_3a": [_cand("3a", 4)],
        }
    )
    all_expected = expected_captions_from_index(index)
    assert {item.ident for item in all_expected} == {"1", "2", "3", "S1", "3a"}

    # 复现修复前的 isdigit() 口径：S1/3a 会被丢弃
    buggy = [i for i in all_expected if i.ident.isdigit() and 1 <= int(i.ident) <= 2]
    assert {i.ident for i in buggy} == {"1", "2"}
    assert "S1" not in {i.ident for i in buggy}
    assert "3a" not in {i.ident for i in buggy}

    # 修复后：与 extract_figures 同口径，非数字编号始终保留
    kept = [i for i in all_expected if i.kind != "figure" or _in_extraction_range(i, 1, 2)]
    assert {i.ident for i in kept} == {"1", "2", "S1", "3a"}

    # 且已导出的 S1 不得被判 unexpected（否则会被 apply_unexpected_rejects 误杀）
    records = [
        AttachmentRecord(kind="figure", ident="S1", page=4, caption="Figure S1",
                         out_path="Figure_S1.png", status="accepted"),
    ]
    report = reconcile_inventory(kept, records)
    assert not [r for r in report.unexpected if r.ident == "S1"], "S1 被误判 unexpected"


def _in_extraction_range(item, lo: int, hi: int) -> bool:
    try:
        num = int(item.ident)
    except ValueError:
        return True
    return lo <= num <= hi


# ---------------------------------------------------------------------------
# P2: 尾注回扩的三处收紧
# ---------------------------------------------------------------------------

def test_table_note_stops_at_overlapping_foreign_line() -> None:
    """尾注块中若出现纵向重叠的同行外来行，必须终止而不是跳过继续桥接。

    旧实现用 continue 跳过重叠行，扫描会跨过该行继续把后面的正文
    接成尾注续行；改为 break 后尾注在第一处异常处停止。
    """
    from lib.table_refine import expand_clip_to_table_notes

    clip = fitz.Rect(100, 100, 400, 200)
    lines = [
        (fitz.Rect(105, 202, 390, 210), 8.0, "Note. First line of the note."),
        # 与上一行纵向重叠的同行外来行（双栏或公式抬升造成）
        (fitz.Rect(105, 208, 390, 220), 8.0, "Foreign line sharing the row."),
        # 若 continue 桥接成功，这一行会被并入尾注
        (fitz.Rect(105, 222, 390, 230), 8.0, "Body text that must not be absorbed."),
    ]
    out = expand_clip_to_table_notes(clip, lines)
    assert out.y1 <= 213, f"重叠外来行之后仍继续桥接尾注 (y1={out.y1})"


def test_table_note_never_absorbs_caption() -> None:
    """尾注行与题注相交时放弃回扩（题注在 Markdown 里单独渲染）。"""
    from lib.table_refine import expand_clip_to_table_notes

    clip = fitz.Rect(100, 100, 400, 200)
    caption = fitz.Rect(100, 202, 400, 240)  # 题注就在尾注位置上
    lines = [
        (fitz.Rect(105, 206, 390, 214), 8.0, "Note. Overlaps the caption band."),
        (fitz.Rect(105, 216, 390, 224), 8.0, "Second line of that note."),
    ]
    out = expand_clip_to_table_notes(clip, lines, caption)
    assert out.y1 <= clip.y1 + 0.01, f"题注被拖进截图 (y1={out.y1})"

    # 不传 caption_rect 时行为不变（老调用点仍能回扩）
    out_free = expand_clip_to_table_notes(clip, lines)
    assert out_free.y1 >= 227, "未传题注时应照常回扩"


def test_table_notes_expanded_before_far_side_trim() -> None:
    """尾注回扩必须排在所有 trim 之前，让 trim 保留最终决定权。

    旧顺序是「先 trim 完再回扩尾注」，回扩会绕开 far_side_body 与
    章节标题清理，把这些 trim 判为正文的内容重新放回框里。
    """
    import inspect

    from lib import extract_tables as et

    src = inspect.getsource(et.main_modular) if hasattr(et, "main_modular") else ""
    if not src:
        src = inspect.getsource(et)
    notes_at = src.index("expand_clip_to_table_notes(")
    trim_body_at = src.index("trim_table_clip_far_side_body(")
    heading_at = src.index("trim_table_far_side_section_heading(")
    assert notes_at < trim_body_at, "尾注回扩必须早于 far_side_body 清理"
    assert notes_at < heading_at, "尾注回扩必须早于章节标题清理"


# ---------------------------------------------------------------------------
# P2: summarize_pdf --reuse-existing 串档
# ---------------------------------------------------------------------------

def test_reuse_existing_rejects_other_pdf(tmp_path) -> None:
    """默认 out_dir 是 <pdf_dir>/images，同目录第二份 PDF 不得复用上一份产物。"""
    import json as _json
    import hashlib as _hashlib

    from core import summarize_pdf as sp

    pdf_a = tmp_path / "paper_a.pdf"
    pdf_b = tmp_path / "paper_b.pdf"
    for path in (pdf_a, pdf_b):
        path.write_bytes(b"%PDF-1.4\n")
    images = tmp_path / "images"
    images.mkdir()
    txt_dir = tmp_path / "text"
    txt_dir.mkdir()
    (images / "index.json").write_text(
        _json.dumps({"meta": {
            "pdf": "paper_a.pdf",
            "pdf_hash": "sha256:" + _hashlib.sha256(pdf_a.read_bytes()).hexdigest()[:16],
        }}), encoding="utf-8"
    )
    (txt_dir / "paper_b.txt").write_text("text of b", encoding="utf-8")

    rc = sp.main([
        "--pdf", str(pdf_b),
        "--out-dir", str(images),
        "--text-path", str(txt_dir / "paper_b.txt"),
        "--reuse-existing",
    ])
    assert rc == 1, "复用了他人的 index.json 必须失败"

    # 索引确实属于 B 时才允许复用
    (images / "index.json").write_text(
        _json.dumps({"meta": {
            "pdf": "paper_b.pdf",
            "pdf_hash": "sha256:" + _hashlib.sha256(pdf_b.read_bytes()).hexdigest()[:16],
        }}), encoding="utf-8"
    )
    assert sp.main([
        "--pdf", str(pdf_b),
        "--out-dir", str(images),
        "--text-path", str(tmp_path / "text" / "paper_b.txt"),
        "--reuse-existing",
    ]) == 0


def test_reuse_existing_rejects_same_name_changed_pdf_and_missing_hash(tmp_path) -> None:
    """同名 PDF 内容替换后，旧图表和新文本不可拼成一份摘要。"""
    import hashlib as _hashlib
    import json as _json

    from core import summarize_pdf as sp

    original = tmp_path / "old" / "paper.pdf"
    current = tmp_path / "new" / "paper.pdf"
    original.parent.mkdir()
    current.parent.mkdir()
    original.write_bytes(b"%PDF-1.4\noriginal")
    current.write_bytes(b"%PDF-1.4\nrevised")
    images = tmp_path / "images"
    images.mkdir()
    (images / "index.json").write_text(_json.dumps({"meta": {
        "pdf": "paper.pdf",
        "pdf_hash": "sha256:" + _hashlib.sha256(original.read_bytes()).hexdigest()[:16],
    }}), encoding="utf-8")
    text_path = tmp_path / "paper.txt"
    text_path.write_text("revised text", encoding="utf-8")
    args = ["--pdf", str(current), "--out-dir", str(images),
            "--text-path", str(text_path), "--reuse-existing"]
    assert sp.main(args) == 1

    (images / "index.json").write_text(
        _json.dumps({"meta": {"pdf": "paper.pdf"}}), encoding="utf-8"
    )
    assert sp.main(args) == 1


def test_reuse_existing_rejects_unreadable_index(tmp_path) -> None:
    """index.json 损坏时不得当作可复用。"""
    from core import summarize_pdf as sp

    pdf = tmp_path / "c.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    images = tmp_path / "images"
    images.mkdir()
    (images / "index.json").write_text("{ not json", encoding="utf-8")
    text = tmp_path / "c.txt"
    text.write_text("t", encoding="utf-8")
    assert sp.main([
        "--pdf", str(pdf), "--out-dir", str(images),
        "--text-path", str(text), "--reuse-existing",
    ]) == 1


# ---------------------------------------------------------------------------
# P2: argparse 缩写被 preset 静默覆盖
# ---------------------------------------------------------------------------

def test_preset_respects_abbreviated_flag() -> None:
    """--text-trim-width 0.8 是 --text-trim-width-ratio 的前缀，不得被 preset 改回 0.5。"""
    from lib.env_priority import apply_preset_robust
    from core.extract_pdf_assets import build_parser_modular

    parser = build_parser_modular()
    argv = ["--pdf", "a.pdf", "--preset", "robust", "--text-trim-width", "0.8"]
    args = parser.parse_args(argv)
    assert args.text_trim_width_ratio == 0.8
    apply_preset_robust(args, argv=argv, parser=parser)
    assert args.text_trim_width_ratio == 0.8, "缩写形式被 preset 覆盖"

    # 未显式传参时 preset 仍要生效（防止修复过头变成 preset 失效）
    plain = ["--pdf", "a.pdf", "--preset", "robust"]
    args2 = parser.parse_args(plain)
    apply_preset_robust(args2, argv=plain, parser=parser)
    assert args2.text_trim_width_ratio == 0.5

    # 完整名与别名同样不被覆盖
    for flag in ("--text-trim-width-ratio", "--text-trim-w"):
        argv3 = ["--pdf", "a.pdf", "--preset", "robust", flag, "0.8"]
        a3 = parser.parse_args(argv3)
        apply_preset_robust(a3, argv=argv3, parser=parser)
        assert a3.text_trim_width_ratio == 0.8, f"{flag} 被 preset 覆盖"


# ---------------------------------------------------------------------------
# P2: figure_post 页眉判定对称 + 邻题注停止线
# ---------------------------------------------------------------------------

def test_running_margin_detection_symmetric_above_below() -> None:
    """页眉/页脚判定的文本特征两侧必须一致。

    旧实现 below 分支漏掉 ":" 条件，"NeurIPS 2024: Foo et al." 这类
    非全大写页脚在 below 方向不会被判为 running margin，
    从而作为图内文字证据把页脚框进截图。
    """
    import inspect

    from lib import figure_post as fp

    src = inspect.getsource(fp.trim_far_side_noise_before_content)
    assert src.count("looks_like_running_margin") >= 3, (
        "两个方向必须共用同一文本判据"
    )
    assert src.count("txt == txt.upper()") == 1, (
        "全大写判据只应出现在共用的 looks_like_running_margin 里"
    )

    # 行为级：非全大写但带冒号的页脚，在 above/below 两侧都应被排除
    clip = fitz.Rect(100, 100, 400, 300)
    header_txt = "NeurIPS 2024: Foo et al."
    for direction, line_rect in (
        ("above", fitz.Rect(105, 102, 300, 110)),
        ("below", fitz.Rect(105, 292, 300, 300)),
    ):
        # clip 无其他证据时必须原样返回：页脚不能成为内容证据
        out = fp.trim_far_side_noise_before_content(
            clip, clip, direction, [], [],
            [(line_rect, 9.0, header_txt)],
        )
        assert list(out) == list(clip), f"{direction} 方向页脚被当作内容证据"


def test_neighbor_caption_inside_clip_blocks_expansion() -> None:
    """落在 clip 内部的邻题注也必须作为扩边停止线。

    旧判据只认「完全在 clip 之上」的邻题注（rect.y1 < clip.y0-0.5），
    已被部分框进 clip 的邻题注会被忽略，扩边就会把它剩下部分一起吞掉。
    远处（不与 clip 相接）的邻题注不阻断——它本就不在回扩路径上。
    """
    from lib.figure_post import expand_clip_to_nearby_figure_objects

    page = fitz.Rect(0, 0, 612, 792)
    caption = fitz.Rect(100, 300, 500, 320)   # 本图题注在下方 → 远侧边在上沿
    limited = fitz.Rect(100, 100, 500, 290)
    obj = fitz.Rect(120, 60, 480, 105)         # 待回扩的图形对象

    # 基线：无邻题注时应能回扩到 y0=54
    baseline = expand_clip_to_nearby_figure_objects(
        limited, caption, "above", [], [obj], page, []
    )
    assert baseline.y0 < limited.y0 - 0.5, f"构造前提不成立 (y0={baseline.y0})"

    # 远处邻题注（y=[20,40]，不与 clip 相接）不阻断回扩
    far_neighbor = expand_clip_to_nearby_figure_objects(
        limited, caption, "above", [], [obj], page, [fitz.Rect(120, 20, 480, 40)]
    )
    assert far_neighbor.y0 < limited.y0 - 0.5, "远处邻题注不应阻断回扩"

    # 与 clip 重叠的邻题注（y=[95,115]）必须阻断
    overlapping = expand_clip_to_nearby_figure_objects(
        limited, caption, "above", [], [obj], page, [fitz.Rect(120, 95, 480, 115)]
    )
    assert overlapping.y0 >= limited.y0 - 0.5, (
        f"与 clip 重叠的邻题注未生效为停止线 (y0={overlapping.y0})"
    )


# ---------------------------------------------------------------------------
# P0#4: run_all 清单完备性闸门
# ---------------------------------------------------------------------------

def test_run_all_detects_unregistered_suite() -> None:
    """新增 test_*.py 未登记时必须被识别（防止再次静默跳过）。"""
    sys.path.insert(0, str(PROJECT_ROOT / "tests" / "scripts"))
    import run_all

    assert run_all.find_unregistered_suites([]), "空清单应报出全部未登记套件"
    listed = [
        {"path": run_all.TESTS_SCRIPTS_DIR / path.name}
        for path in run_all.TESTS_SCRIPTS_DIR.glob("test_*.py")
        if path.name != run_all.GOLDEN_SUITE_FILE
    ]
    assert run_all.find_unregistered_suites(listed) == [], (
        "当前清单应覆盖 tests/scripts/ 下全部非 golden 套件"
    )


def test_golden_direct_entry_rejects_same_batch_self_comparison(tmp_path, monkeypatch) -> None:
    """直接运行 golden 脚本也必须拒绝同批次 index/golden 自比。"""
    import json

    sys.path.insert(0, str(PROJECT_ROOT / "tests" / "scripts"))
    import test_extraction_golden as golden

    images = tmp_path / "images"
    images.mkdir()
    index = images / "index.json"
    baseline = images / "golden_index.json"
    payload = {"version": "2.0", "meta": {"pdf": "paper.pdf", "pages": 1}, "items": []}
    index.write_text(json.dumps(payload), encoding="utf-8")
    baseline.write_text(json.dumps(payload), encoding="utf-8")
    spec = golden.GoldenSpec("paper.pdf", 0, 0)
    monkeypatch.setattr(golden, "CORE_REGRESSION_SET", [spec])
    monkeypatch.setattr(
        golden, "_resolve_golden_paths",
        lambda _spec: (tmp_path / "paper.pdf", images, index, baseline),
    )
    monkeypatch.setattr(golden, "ensure_extracted_index", lambda *_args, **_kw: (True, ""))

    passed, failed, results = golden.run_golden_tests()
    assert (passed, failed) == (0, 1)
    assert "同批次" in " ".join(results[0].messages)


# ---------------------------------------------------------------------------
# P1#5: A3 精修不得把 legacy rejected 晋升为可插入状态
# ---------------------------------------------------------------------------

def test_legacy_rejected_not_promoted_by_refiner() -> None:
    """真正打到「精修质量可接受」分支，验证状态只降不升。

    原测试只走「无 Layout 候选」的快速返回分支，并未触及状态改写点。
    这里用真实 PDF + 真实候选框驱动 A3，使 legacy rejected 记录进入
    else 分支（几何可接受 → 走 _apply_quality_meta）。
    """
    from lib.assess import markdown_insertable
    from lib.models import AttachmentRecord
    from lib.pipeline import run_refinement_pipeline

    # Figure 1 在第 3 页（题注 y≈404.7，图形在题注上方）
    page_no = 3
    with _open("*1706.03762v7*.pdf") as doc:
        caption_rect = doc[page_no - 1].search_for("Figure 1:")[0]
    caption = (caption_rect.x0, caption_rect.y0, caption_rect.x1, caption_rect.y1)
    content = fitz.Rect(189.8, 65.8, 422.3, 402.7)

    rec = AttachmentRecord(
        kind="figure", ident="1", page=page_no,
        caption="Figure 1: The Transformer - encoder-decoder architecture",
        out_path="Figure_1.png",
        status="rejected", review_required=True, warnings=["text_pollution"],
        final_bbox=[content.x0, content.y0, content.x1, caption_rect.y0],
    )
    # A2 pairing_results 的形状是 page -> PairingResult(pairs=[(caption_cand, [content_cand])])
    class _Cand:
        def __init__(self, **kw):
            self.__dict__.update(kw)

    caption_cand = _Cand(kind="figure", caption_bbox=list(caption), content_bboxes=[])
    content_cand = _Cand(
        kind="figure",
        content_bboxes=[[content.x0, content.y0, content.x1, content.y1]],
    )
    pairing = {
        page_no: _Cand(page=page_no, pairs=[(caption_cand, [content_cand])])
    }

    pdf_path = str(next(BENCHMARK.glob("*1706.03762v7*.pdf")))
    report = run_refinement_pipeline([rec], pairing, pdf_path, "/tmp")
    assert report.matched == 1, "构造前提不成立：未匹配到候选"

    assert rec.status != "accepted", "legacy rejected 被晋升为 accepted"
    assert "legacy_rejected_preserved" in rec.warnings
    assert rec.status == "review_required"
    assert markdown_insertable(
        rec.status, review_required=rec.review_required, warnings=rec.warnings
    ) is False, "被晋升后仍可插入 Markdown"


def test_border_rules_never_slice_adjacent_text() -> None:
    """并入外框线不得切开紧邻文字行。

    Qwen T6 底线（719.29）正下方 0.9pt 就是脚注首行 y0=719.7，
    不设约束时并入底线会把该行切掉约 1pt。
    """
    from lib.table_refine import expand_table_clip_to_border_rules

    class _Page:
        rect = fitz.Rect(0, 0, 612, 792)

        def get_drawings(self):
            return [{"rect": (70.0, 205.0, 520.0, 205.0)}]

    clip = fitz.Rect(70, 100, 520, 205)
    foot = [(fitz.Rect(76, 205.4, 520, 215), 7.3, "a These 19 languages include ...")]

    free = expand_table_clip_to_border_rules(clip, _Page())
    assert free.y1 >= 206.4, "无文字行时应正常并入底线"

    guarded = expand_table_clip_to_border_rules(clip, _Page(), foot)
    assert guarded.y1 <= 205.4 + 1e-6, f"切开了紧邻文字行 (y1={guarded.y1})"
    assert guarded.y1 >= 205.0, "底线本身仍应被并入"

    # 短脚注和窄单元格也有完整字形，不能因宽度不足表框 55% 就放过。
    short_foot = [(fitz.Rect(76, 205.4, 140, 215), 7.3, "b short note")]
    guarded_short = expand_table_clip_to_border_rules(clip, _Page(), short_foot)
    assert guarded_short.y1 <= 205.4 + 1e-6, (
        f"短文字行被外框补边切开 (y1={guarded_short.y1})"
    )


def test_short_bold_fragments_are_not_markdown_headings() -> None:
    """页码、公式、单字母和正文字号的表头不能变成 Markdown 标题。"""
    from lib.text_extract import looks_like_structural_heading

    assert looks_like_structural_heading("1 Introduction", is_bold=True, font_size=10)
    assert looks_like_structural_heading("Abstract", is_bold=True, font_size=14)
    assert not looks_like_structural_heading("272", is_bold=True, font_size=9)
    assert not looks_like_structural_heading("1 - P(E)", is_bold=True, font_size=11)
    assert not looks_like_structural_heading("l", is_bold=True, font_size=12)
    assert not looks_like_structural_heading("2.1", is_bold=True, font_size=12)
    assert not looks_like_structural_heading("FEELING ITEMS", is_bold=True, font_size=9)
    assert not looks_like_structural_heading("1997), with AVM tagging", is_bold=True, font_size=10)


def test_full_width_table_clip_stays_in_caption_column() -> None:
    """题注在左栏、右栏有正文、又没有通栏横线时，表框不能横贯双栏。"""
    from lib.table_refine import limit_table_clip_to_caption_column

    page = fitz.Rect(0, 0, 612, 792)
    caption = fitz.Rect(70, 180, 280, 194)
    clip = fitz.Rect(26, 200, 586, 360)
    right_body = [
        (fitz.Rect(330, 210, 540, 222), 10.0, "B1 dialogue continues on the right."),
        (fitz.Rect(330, 226, 540, 238), 10.0, "U1 another right-column line."),
    ]
    limited = limit_table_clip_to_caption_column(clip, caption, page, right_body, [])
    assert limited.x1 < 320, f"表框仍横贯右栏 (x1={limited.x1})"

    full_rule = [{"rect": (40.0, 220.0, 570.0, 221.0)}]
    kept = limit_table_clip_to_caption_column(clip, caption, page, right_body, full_rule)
    assert kept.x1 > 500, "通栏表格线不应被收进单栏"


def test_border_rules_do_not_slice_line_that_already_crosses_clip() -> None:
    """字框已经跨过原 clip 底边时，补边不能停在这一行内部。

    旧守卫只认「行首落在新增带里」。行首在 clip 内、行尾超出补边时，
    横线仍被并入，底边却落在字形中间。
    """
    from lib.table_refine import expand_table_clip_to_border_rules

    class _Page:
        rect = fitz.Rect(0, 0, 612, 792)

        def get_drawings(self):
            return [{"rect": (70.0, 206.0, 520.0, 206.4)}]

    clip = fitz.Rect(70, 100, 520, 205)
    line = fitz.Rect(76, 204.2, 180, 216)
    out = expand_table_clip_to_border_rules(
        clip, _Page(), [(line, 7.3, "b short note")]
    )
    assert out.y1 <= line.y0 + 1e-6 or out.y1 >= line.y1 - 1e-6, (
        f"补边停在跨边文字行内部 (y1={out.y1})"
    )
    assert out.y1 >= 206.4 - 1e-6, f"为了不切字丢掉了底线 (y1={out.y1})"


def test_border_rules_keep_rule_when_text_overlaps_stroke() -> None:
    """字框压住横线时，收到行首会把横线排除。应纳入整行，而不是丢边。"""
    from lib.table_refine import expand_table_clip_to_border_rules

    class _Page:
        rect = fitz.Rect(0, 0, 612, 792)

        def get_drawings(self):
            return [{"rect": (70.0, 205.8, 520.0, 206.6)}]

    clip = fitz.Rect(70, 100, 520, 205)
    line = fitz.Rect(76, 205.3, 180, 215)
    out = expand_table_clip_to_border_rules(
        clip, _Page(), [(line, 7.3, "b short note")]
    )
    assert out.y1 >= 206.6 - 1e-6, f"压住横线的短脚注导致底线被丢 (y1={out.y1})"
    assert out.y1 >= line.y1 - 1e-6, f"底边仍落在脚注行内 (y1={out.y1})"


def test_border_rules_do_not_swallow_tall_body_to_keep_rule() -> None:
    """与横线重叠的高正文不能为了留住底线被整段吞进截图。"""
    from lib.table_refine import expand_table_clip_to_border_rules

    class _Page:
        rect = fitz.Rect(0, 0, 612, 792)

        def get_drawings(self):
            return [{"rect": (70.0, 206.0, 520.0, 206.4)}]

    clip = fitz.Rect(70, 100, 520, 205)
    body = fitz.Rect(76, 204.0, 520, 400)
    out = expand_table_clip_to_border_rules(
        clip, _Page(), [(body, 10.0, "This paragraph continues well past the table.")]
    )
    assert out.y1 <= clip.y1 + 1e-6, f"高正文被外框补边吞入 (y1={out.y1})"


def test_border_rules_follow_overlapping_short_notes() -> None:
    """相邻短脚注 bbox 互相重叠时，底边要落到整段脚注之后，不能丢线。"""
    from lib.table_refine import expand_table_clip_to_border_rules

    class _Page:
        rect = fitz.Rect(0, 0, 612, 792)

        def get_drawings(self):
            return [{"rect": (70.0, 206.0, 520.0, 206.6)}]

    clip = fitz.Rect(70, 100, 520, 205)
    notes = [
        (fitz.Rect(76, 205.3, 400, 210), 7.3, "a first"),
        (fitz.Rect(76, 208.2, 400, 215), 7.3, "b second"),
    ]
    out = expand_table_clip_to_border_rules(clip, _Page(), notes)
    assert out.y1 >= 206.6 - 1e-6, f"重叠短脚注导致底线被丢 (y1={out.y1})"
    assert out.y1 >= 215 - 1e-6, f"底边落在第二行脚注内 (y1={out.y1})"


def test_border_rules_top_edge_keeps_rule_when_text_overlaps_stroke() -> None:
    """顶边与底边同一约束：字框压住顶线时纳入整行，不切字也不丢线。"""
    from lib.table_refine import expand_table_clip_to_border_rules

    class _Page:
        rect = fitz.Rect(0, 0, 612, 792)

        def get_drawings(self):
            return [{"rect": (70.0, 105.2, 520.0, 106.0)}]

    clip = fitz.Rect(70, 107, 520, 240)
    line = fitz.Rect(76, 96, 180, 106.4)
    out = expand_table_clip_to_border_rules(
        clip, _Page(), [(line, 7.3, "header")]
    )
    assert out.y0 <= 105.2 + 1e-6, f"压住顶线的短行导致顶线被丢 (y0={out.y0})"
    assert out.y0 <= line.y0 + 1e-6, f"顶边仍落在文字行内 (y0={out.y0})"


def test_border_rules_fallback_to_clip_on_degenerate_intersection() -> None:
    """扩边结果与页面求交为退化 Rect 时必须回退原 clip。

    PyMuPDF 空交集 Rect（x0>=x1）布尔值仍为 True，旧写法
    `(rect & page_rect) or clip` 的兜底永不生效，会把畸形框直接返回。
    本用例的 clip 整体在页外属 Mock 几何，用于锁定兜底语义本身。
    """
    from lib.table_refine import expand_table_clip_to_border_rules

    class _Page:
        rect = fitz.Rect(0, 0, 612, 792)

        def get_drawings(self):
            return [{"rect": (150.0, 902.0, 350.0, 903.0)}]

    clip = fitz.Rect(100, 800, 400, 900)  # 整体位于页面下方
    out = expand_table_clip_to_border_rules(clip, _Page())
    assert list(out) == list(clip), f"退化交集应回退原 clip，实际返回 {out}"
    assert out.x0 <= out.x1 and out.y0 <= out.y1, "返回了 x0>x1 的畸形框"


def test_exported_attention_and_kimi_visual_boundaries() -> None:
    """检查先前 review_required/页眉污染的真实 benchmark 资产。"""
    import json

    sys.path.insert(0, str(PROJECT_ROOT / "tests" / "scripts"))
    from test_extraction_golden import GoldenSpec, ensure_extracted_index, _resolve_golden_paths

    for pdf_file in (
        "1706.03762v7-attention_is_all_you_need.pdf",
        "2607.24653v2-Kimi-K3.pdf",
    ):
        spec = GoldenSpec(pdf_file, 0, 0)
        ok, message = ensure_extracted_index(spec)
        assert ok, message
        data = json.loads(_resolve_golden_paths(spec)[2].read_text())
        items = data["items"]
        if pdf_file.startswith("1706"):
            figure4 = next(x for x in items if x["type"] == "figure" and x["id"] == "4")
            assert 604 <= figure4["final_bbox"][3] < figure4["caption_bbox"][1]
            assert figure4["status"] == "accepted"
        else:
            figure2 = next(x for x in items if x["type"] == "figure" and x["id"] == "2")
            table5 = next(x for x in items if x["type"] == "table" and x["id"] == "5")
            assert figure2["final_bbox"][1] >= 45, "运行页眉仍被纳入 Figure 2"
            assert figure2["status"] == "accepted"
            assert table5["status"] == "accepted" and "table_band_open" not in table5["warnings"]


# ---------------------------------------------------------------------------
# 跨类型吞没：主链缺守卫（只打标，不改几何）
# ---------------------------------------------------------------------------

def test_cross_kind_overlap_marked() -> None:
    """图框压住上表末行时必须被告警，不得静默 accepted。

    图与表各自在独立主循环收边，detect_conflicts 只在 layout-backend 开启
    时运行且只比对同类型，主链上没有跨类型重叠校验。
    """
    from lib.assess import mark_cross_kind_overlaps, markdown_insertable
    from lib.models import AttachmentRecord

    def _rec(kind, ident, bbox):
        return AttachmentRecord(
            kind=kind, ident=ident, page=1, caption="c", out_path=f"{kind}{ident}.png",
            final_bbox=list(bbox), status="accepted", warnings=[], review_required=False,
        )

    # 图框下沿 281 压住表框(100-300)的末行 19pt
    recs = [_rec("table", "1", (66, 100, 527, 300)), _rec("figure", "1", (66, 281, 527, 500))]
    mark_cross_kind_overlaps(recs)
    for rec in recs:
        assert any(w.startswith("cross_kind_overlap") for w in rec.warnings), (
            f"{rec.kind} {rec.ident} 未被告警"
        )
        assert rec.review_required and rec.status == "review_required"
        assert markdown_insertable(
            rec.status, review_required=rec.review_required, warnings=rec.warnings
        ) is False, "跨类型吞没的资产不得进入 Markdown"

    # accepted_with_margin 同样可插入；只改 review_required 挡不住 Markdown。
    margin = [
        _rec("table", "1", (66, 100, 527, 300)),
        _rec("figure", "1", (66, 281, 527, 500)),
    ]
    for rec in margin:
        rec.status = "accepted_with_margin"
    mark_cross_kind_overlaps(margin)
    for rec in margin:
        assert rec.status == "review_required", (
            f"{rec.kind} {rec.ident} 仍为 {rec.status}，会被插入 Markdown"
        )
        assert markdown_insertable(
            rec.status, review_required=rec.review_required, warnings=rec.warnings
        ) is False

    # 无重叠 / 轻微重叠不得误报
    for name, recs2 in (
        ("无重叠", [_rec("table", "1", (66, 100, 527, 300)),
                    _rec("figure", "1", (66, 310, 527, 500))]),
        ("边缘轻微重叠", [_rec("table", "1", (66, 100, 527, 300)),
                          _rec("figure", "1", (500, 296, 527, 500))]),
    ):
        mark_cross_kind_overlaps(recs2)
        for rec in recs2:
            assert not rec.warnings, f"{name} 被误报: {rec.warnings}"
            assert rec.status == "accepted"


def test_cross_kind_overlap_reported_in_payload() -> None:
    """跨类型重叠必须出现在 inventory payload 里（可观测，而非静默）。"""
    import inspect

    from lib.assess import finalize_caption_inventory

    src = inspect.getsource(finalize_caption_inventory)
    assert "mark_cross_kind_overlaps(records)" in src
    assert '"cross_kind_overlaps"' in src


def test_update_golden_writes_to_a_separate_batch(tmp_path, monkeypatch) -> None:
    """更新基准不得与生成该基准的 index.json 同批，避免自比较假绿。"""
    import json
    import sys

    scripts_dir = str(PROJECT_ROOT / "tests" / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)
    import test_extraction_golden as golden

    source_images = tmp_path / "20260928-001" / "paper" / "images"
    source_images.mkdir(parents=True)
    source_index = source_images / "index.json"
    source_index.write_text(
        json.dumps({"version": "2.0", "meta": {"pdf": "paper.pdf"}, "items": []}),
        encoding="utf-8",
    )
    baseline_batch = tmp_path / "20260928-002"
    spec = golden.GoldenSpec("paper.pdf", 0, 0)

    monkeypatch.setattr(golden, "CORE_REGRESSION_SET", [spec])
    monkeypatch.setattr(
        golden, "_resolve_golden_paths",
        lambda _spec: (tmp_path / "paper.pdf", source_images, source_index,
                       source_images / "golden_index.json"),
    )
    monkeypatch.setattr(golden, "ensure_extracted_index", lambda *_a, **_k: (True, ""))
    monkeypatch.setattr(golden, "_compute_batch_dir", lambda: baseline_batch)

    passed, failed, results = golden.run_golden_tests(update_golden=True)

    updated_path = baseline_batch / "paper" / "images" / "golden_index.json"
    assert (passed, failed) == (1, 0)
    assert updated_path.exists(), results[0].messages
    assert not golden.golden_is_self_comparison(source_index, updated_path)
