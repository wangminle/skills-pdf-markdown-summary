# -*- coding: utf-8 -*-
"""2026-10-01 复核四项待办的回归测试（TDD 先行）。

- BUG-130：跨文本块题注续行未合并（PARADISE Figure 6 真实几何缩减）
- BUG-131：插入表截图后正文仍保留框内散行（SASSI Table 4 真实几何缩减）
- ADJ-015：逐资产 Markdown 嵌入状态字段与控制台 embedded/extracted 汇总
- DOC-067：--asset-dir 帮助与 SKILL 的 Markdown 目录基准说明
- BUG-134/135：图片路径与替代文本的实际 Markdown 解析
- BUG-136：多行描述动词真题注与正文引用共用判据
"""
import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "skills" / "pdf-markdown-summary" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

FIGURE_PATTERN = re.compile(r"^\s*(?:Figure|Fig\.?)\s+([A-Za-z]?\d+)", re.I)


def _line(text, x0, y0, x1, y1, size=8.8):
    return {
        "bbox": [x0, y0, x1, y1],
        "spans": [{"text": text, "size": size, "bbox": [x0, y0, x1, y1]}],
    }


def _block(lines, btype=0):
    x0 = min(l["bbox"][0] for l in lines)
    y0 = min(l["bbox"][1] for l in lines)
    x1 = max(l["bbox"][2] for l in lines)
    y1 = max(l["bbox"][3] for l in lines)
    return {"type": btype, "bbox": [x0, y0, x1, y1], "lines": lines}


def _paradise_fig6_blocks():
    """PARADISE p8 块15/16/17 的真实几何（20261001-002 复核数据）。"""
    caption = _block([_line(
        "Figure 6: A circuit domain dialogue (Smith and Gordon, ",
        321.6, 436.7, 543.7, 450.5,
    )])
    continuation = _block([_line(
        "1997), with AVM tagging ", 322.8, 448.6, 423.9, 461.3,
    )])
    body = _block([
        _line("Smith and Gordon collected 144 dialogues for this task, ",
              331.7, 472.4, 543.9, 485.0),
        _line("in which agent initiative was varied by using different ",
              322.1, 483.0, 542.4, 495.6),
    ])
    return caption, continuation, body


class TestCrossBlockCaptionMerge:
    """BUG-130：题注跨块续行应在共享题注层合并，索引/提取/alt 一致完整。"""

    def test_paradise_fig6_continuation_merges(self):
        from lib.caption_detection import merge_caption_lines
        caption, continuation, body = _paradise_fig6_blocks()
        merged = merge_caption_lines(
            caption, 0, FIGURE_PATTERN,
            following_blocks=[continuation, body],
        )
        assert merged is not None
        assert "1997), with AVM tagging" in merged.text
        assert merged.line_count == 2
        assert merged.rect.y1 == pytest.approx(461.3, abs=0.01)

    def test_body_block_not_swallowed_after_continuation(self):
        from lib.caption_detection import merge_caption_lines
        caption, continuation, body = _paradise_fig6_blocks()
        merged = merge_caption_lines(
            caption, 0, FIGURE_PATTERN,
            following_blocks=[continuation, body],
        )
        assert "Smith and Gordon collected" not in merged.text

    def test_no_trailing_signal_does_not_cross(self):
        from lib.caption_detection import merge_caption_lines
        caption = _block([_line("Figure 6: A circuit domain dialogue ",
                                321.6, 436.7, 543.7, 450.5)])
        nxt = _block([_line("Dialogues were collected for this task, ",
                            322.1, 452.5, 542.4, 465.1)])
        merged = merge_caption_lines(
            caption, 0, FIGURE_PATTERN, following_blocks=[nxt],
        )
        assert "Dialogues were collected" not in merged.text

    def test_indented_next_block_does_not_cross(self):
        from lib.caption_detection import merge_caption_lines
        caption = _block([_line("Figure 6: A circuit domain dialogue,",
                                321.6, 436.7, 543.7, 450.5)])
        indented = _block([_line("the dialogues were tagged.",
                                 331.7, 452.5, 542.4, 465.1)])
        merged = merge_caption_lines(
            caption, 0, FIGURE_PATTERN, following_blocks=[indented],
        )
        assert "the dialogues were tagged" not in merged.text

    def test_new_caption_block_does_not_cross(self):
        from lib.caption_detection import merge_caption_lines
        caption = _block([_line("Figure 6: A circuit domain dialogue,",
                                321.6, 436.7, 543.7, 450.5)])
        new_caption = _block([_line("Figure 7: Another example",
                                    321.6, 452.5, 542.4, 465.1)])
        merged = merge_caption_lines(
            caption, 0, FIGURE_PATTERN, following_blocks=[new_caption],
        )
        assert "Figure 7" not in merged.text

    def test_non_text_block_between_does_not_cross(self):
        from lib.caption_detection import merge_caption_lines
        caption = _block([_line("Figure 6: A circuit domain dialogue,",
                                321.6, 436.7, 543.7, 450.5)])
        image_block = {"type": 1, "bbox": [100, 452, 200, 470]}
        continuation = _block([_line("1997), with AVM tagging",
                                     322.1, 472.0, 423.9, 484.0)])
        merged = merge_caption_lines(
            caption, 0, FIGURE_PATTERN,
            following_blocks=[image_block, continuation],
        )
        assert "1997)" not in merged.text

    def test_chain_across_two_following_blocks(self):
        from lib.caption_detection import merge_caption_lines
        caption = _block([_line("Figure 9: Performance of Uni-Parser,",
                                100, 100, 400, 112)])
        mid = _block([_line("compared with strong baselines and",
                            101, 113, 400, 125)])
        tail = _block([_line("open-source systems.", 100.5, 126.5, 300, 138.5)])
        merged = merge_caption_lines(
            caption, 0, FIGURE_PATTERN,
            following_blocks=[mid, tail],
        )
        assert "open-source systems." in merged.text
        assert merged.line_count == 3

    def test_without_following_blocks_behavior_unchanged(self):
        from lib.caption_detection import merge_caption_lines
        caption, continuation, _ = _paradise_fig6_blocks()
        merged = merge_caption_lines(caption, 0, FIGURE_PATTERN)
        assert "1997)" not in merged.text


def _md_doc_with_sassi_p35():
    """SASSI p35 真实段落几何（20261001-002 复核数据）构造的 MarkdownDocument。"""
    from lib.markdown import MarkdownBlock, MarkdownDocument
    paras = [
        ("paragraph", "Table 4: Exploratory Factor Analysis Results",
         (72.0, 70.9, 288.5, 86.9)),
        ("heading", "Component", (382.2, 101.6, 442.3, 118.3)),
        ("paragraph", "1\n2\n3\n4\n5\n6", (298.2, 120.7, 526.2, 137.3)),
        ("paragraph", "The system is accurate\n.799\nThe system is unreliable",
         (72.0, 138.4, 406.8, 499.8)),
        ("paragraph", "-.610", (381.9, 474.0, 406.8, 490.0)),
        ("paragraph", "Percentage of Variance (rotated solution)\n16.46",
         (72.0, 713.8, 540.0, 730.4)),
        ("paragraph", "35", (291.7, 791.2, 303.7, 807.2)),
    ]
    blocks = [
        MarkdownBlock(type=t, text=x, page=35, meta={"bbox": list(b)})
        for t, x, b in paras
    ]
    return MarkdownDocument(title="t", source_pdf="s.pdf", blocks=blocks)


def _sassi_table4_item(**overrides):
    item = {
        "type": "table",
        "id": "4",
        "page": 35,
        "status": "accepted",
        "file": "Table_4_Exploratory_Factor_Analysis_Results.png",
        "caption": "Table 4: Exploratory Factor Analysis Results",
        "final_bbox": [61.5, 95.3, 549.9, 736.6],
        "caption_bbox": [72.0, 70.9, 288.5, 86.9],
    }
    item.update(overrides)
    return item


def _place(document, items, tmp_path):
    from core.pdf_to_markdown import _place_assets_in_document
    index_json = tmp_path / "index.json"
    index_json.write_text("[]", encoding="utf-8")
    (tmp_path / "Table_4_Exploratory_Factor_Analysis_Results.png").write_bytes(b"x")
    out_md = tmp_path / "paper.md"
    out_md.write_text("", encoding="utf-8")
    _place_assets_in_document(
        document,
        {"enabled": True, "items": items, "index_json": str(index_json)},
        str(out_md),
    )
    return document


class TestTableBodyTextSuppression:
    """BUG-131：实际插入的表截图应抑制 final_bbox 覆盖的正文散行。"""

    def test_inserted_table_suppresses_covered_text(self, tmp_path):
        doc = _md_doc_with_sassi_p35()
        _place(doc, [_sassi_table4_item()], tmp_path)
        texts = [b.text for b in doc.blocks]
        assert any(b.type == "image" for b in doc.blocks)
        assert not any("The system is accurate" in t for t in texts)
        assert not any(t == "Component" for t in texts)
        assert not any("Percentage of Variance" in t for t in texts)

    def test_caption_and_outside_text_kept(self, tmp_path):
        doc = _md_doc_with_sassi_p35()
        _place(doc, [_sassi_table4_item()], tmp_path)
        texts = [b.text for b in doc.blocks]
        assert any("Table 4: Exploratory Factor Analysis Results" in t
                   for t in texts)
        assert any(t == "35" for t in texts)

    def test_unmatched_inserted_asset_also_suppresses(self, tmp_path):
        doc = _md_doc_with_sassi_p35()
        doc.blocks = [b for b in doc.blocks
                      if "Table 4:" not in b.text]  # 去掉题注 → 资产退回文末
        _place(doc, [_sassi_table4_item()], tmp_path)
        texts = [b.text for b in doc.blocks]
        assert any(b.type == "image" for b in doc.blocks)
        assert not any("The system is accurate" in t for t in texts)

    def test_no_inserted_items_keeps_document(self, tmp_path):
        doc = _md_doc_with_sassi_p35()
        before = [b.text for b in doc.blocks]
        _place(doc, [], tmp_path)
        assert [b.text for b in doc.blocks] == before

    def test_figure_covered_text_suppressed(self, tmp_path):
        from lib.markdown import MarkdownBlock, MarkdownDocument
        blocks = [
            MarkdownBlock(type="paragraph",
                          text="Figure 6: A circuit domain dialogue",
                          page=8, meta={"bbox": [321.6, 436.7, 543.7, 450.5]}),
            MarkdownBlock(type="paragraph",
                          text="The circuit is working correctly. Good-bye.",
                          page=8, meta={"bbox": [357.6, 416.3, 477.4, 425.7]}),
            MarkdownBlock(type="paragraph",
                          text="Smith and Gordon collected 144 dialogues",
                          page=8, meta={"bbox": [331.7, 472.4, 543.9, 485.0]}),
        ]
        doc = MarkdownDocument(title="t", source_pdf="s.pdf", blocks=blocks)
        item = {
            "type": "figure", "id": "6", "page": 8, "status": "accepted",
            "file": "Table_4_Exploratory_Factor_Analysis_Results.png",
            "caption": "Figure 6: A circuit domain dialogue",
            "final_bbox": [328.1, 99.5, 499.6, 425.7],
            "caption_bbox": [321.6, 436.7, 543.7, 450.5],
        }
        _place(doc, [item], tmp_path)
        texts = [b.text for b in doc.blocks]
        assert not any("Good-bye" in t for t in texts)
        assert any("Smith and Gordon collected" in t for t in texts)
        assert any("Figure 6: A circuit domain dialogue" in t for t in texts)

    def test_explicit_caption_line_inside_bbox_kept(self, tmp_path):
        doc = _md_doc_with_sassi_p35()
        from lib.markdown import MarkdownBlock
        doc.blocks.append(MarkdownBlock(
            type="paragraph", text="Table 5: Follow-up results",
            page=35, meta={"bbox": [100.0, 700.0, 300.0, 712.0]}))
        _place(doc, [_sassi_table4_item()], tmp_path)
        assert any("Table 5: Follow-up results" in b.text for b in doc.blocks)

    def test_partial_overlap_kept(self, tmp_path):
        doc = _md_doc_with_sassi_p35()
        from lib.markdown import MarkdownBlock
        doc.blocks.append(MarkdownBlock(
            type="paragraph", text="A paragraph spanning the table edge",
            page=35, meta={"bbox": [72.0, 720.0, 540.0, 760.0]}))
        _place(doc, [_sassi_table4_item()], tmp_path)
        assert any("spanning the table edge" in b.text for b in doc.blocks)


class TestEmbedStatusAndSummary:
    """ADJ-015：逐资产嵌入状态字段 + 控制台/报告 embedded 汇总。"""

    def _asset_result(self, tmp_path, items, omitted=None):
        index_json = tmp_path / "index.json"
        index_json.write_text("[]", encoding="utf-8")
        for it in items:
            (tmp_path / (it.get("file") or "x.png")).write_bytes(b"x")
        (tmp_path / "paper.md").write_text("", encoding="utf-8")
        return {
            "enabled": True, "items": items, "omitted": omitted or [],
            "extracted_count": len(items) + len(omitted or []),
            "index_json": str(index_json),
        }

    def test_place_returns_placement_summary(self, tmp_path):
        doc = _md_doc_with_sassi_p35()
        items = [_sassi_table4_item(),
                 _sassi_table4_item(id="5", caption="Table 5: Other",
                                    file="t5.png",
                                    caption_bbox=[1, 1, 2, 2])]
        result = self._asset_result(tmp_path, items)
        from core.pdf_to_markdown import _place_assets_in_document
        placement = _place_assets_in_document(
            doc, result, str(tmp_path / "paper.md"))
        assert placement is not None
        assert [i["id"] for i in placement["inline"]] == ["4"]
        assert [i["id"] for i in placement["appendix"]] == ["5"]

    def test_per_asset_fields_and_index_writeback(self, tmp_path):
        doc = _md_doc_with_sassi_p35()
        items = [_sassi_table4_item()]
        omitted = [{"type": "table", "id": "9", "page": 36,
                    "status": "review_required", "warnings": []}]
        result = self._asset_result(tmp_path, items, omitted)
        from core.pdf_to_markdown import (
            _place_assets_in_document, _annotate_and_persist_embed_status,
        )
        placement = _place_assets_in_document(
            doc, result, str(tmp_path / "paper.md"))
        _annotate_and_persist_embed_status(result, placement)
        item = items[0]
        assert item["referenced_in_markdown"] is True
        assert item["embed_mode"] == "inline"
        assert item["suppressed_text_blocks"] >= 3

    def test_summary_counts(self, tmp_path):
        from core.pdf_to_markdown import _summarize_embed_status
        result = {
            "enabled": True,
            "items": [
                {"referenced_in_markdown": True, "embed_mode": "inline"},
                {"referenced_in_markdown": True, "embed_mode": "appendix"},
            ],
            "omitted": [{"status": "review_required"},
                        {"status": "rejected"}],
            "extracted_count": 4,
        }
        summary = _summarize_embed_status(result)
        assert summary["embedded"] == 2
        assert summary["inline"] == 1
        assert summary["appendix"] == 1
        assert summary["omitted"] == 2
        assert summary["extracted"] == 4

    def test_writeback_updates_index_json_file(self, tmp_path):
        index_json = tmp_path / "index.json"
        index_json.write_text(__import__("json").dumps({
            "version": "2.0",
            "figures": [],
            "tables": [
                {"type": "table", "id": "4", "page": 35, "file": "a.png"},
                {"type": "table", "id": "9", "page": 36, "file": "b.png"},
            ],
            "items": [
                {"type": "table", "id": "4", "page": 35, "file": "a.png"},
                {"type": "table", "id": "9", "page": 36, "file": "b.png"},
            ],
        }), encoding="utf-8")
        result = {
            "enabled": True,
            "items": [{"type": "table", "id": "4", "page": 35, "file": "a.png",
                       "referenced_in_markdown": True, "embed_mode": "inline",
                       "suppressed_text_blocks": 5}],
            "omitted": [{"type": "table", "id": "9", "page": 36,
                         "file": "b.png", "status": "review_required"}],
            "index_json": str(index_json),
        }
        from core.pdf_to_markdown import _persist_embed_status_to_index
        _persist_embed_status_to_index(result)
        import json as _json
        data = _json.loads(index_json.read_text(encoding="utf-8"))
        t4 = data["items"][0]
        t9 = data["items"][1]
        assert t4["referenced_in_markdown"] is True
        assert t4["embed_mode"] == "inline"
        assert t4["suppressed_text_blocks"] == 5
        assert t9["referenced_in_markdown"] is False
        assert data["tables"][0]["referenced_in_markdown"] is True


class TestAssetDirDocsAndHints:
    """DOC-067：--asset-dir 的 Markdown 目录基准说明与解析路径提示。"""

    def test_help_explains_markdown_dir_base(self):
        import contextlib
        import io
        from core.pdf_to_markdown import parse_args
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), pytest.raises(SystemExit):
            parse_args(["--help"])
        help_text = buf.getvalue()
        assert "Markdown" in help_text
        assert "relative" in help_text.lower()

    def test_console_prints_resolved_asset_dir(self, tmp_path, capsys):
        import fitz
        from core.pdf_to_markdown import main
        pdf = tmp_path / "p.pdf"
        doc = fitz.open()
        page = doc.new_page(width=420, height=320)
        page.insert_text((48, 72), "Hello world", fontsize=12)
        doc.save(pdf)
        doc.close()
        out_md = tmp_path / "out" / "paper.md"
        rc = main(["--pdf", str(pdf), "--out", str(out_md),
                   "--asset-dir", "assets"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "Asset dir:" in out
        assert str(tmp_path / "out" / "assets") in out

    def test_skill_md_documents_asset_dir_base(self):
        skill = (REPO_ROOT / "skills" / "pdf-markdown-summary" / "SKILL.md"
                 ).read_text(encoding="utf-8")
        assert "--asset-dir" in skill
        assert "Markdown" in skill


class TestContinuationSignalWordBoundary:
    """BUG-132：未完信号正则必须有单词边界——ImageNet/test set/data 等
    完整词尾命中 et/a 时不许把下一块正文合并进题注。"""

    def test_regex_rejects_complete_word_endings(self):
        from lib.caption_detection import _CAPTION_CONTINUATION_END_RE as sig
        assert not sig.search("Figure 5: Training curves on ImageNet")
        assert not sig.search("Figure 3: Results on the test set")
        assert not sig.search("Figure 2: Distribution of the data")
        assert not sig.search("Table 1: Layout type used in Uni-Parser-LD")

    def test_regex_keeps_real_continuation_signals(self):
        from lib.caption_detection import _CAPTION_CONTINUATION_END_RE as sig
        assert sig.search("Figure 6: A circuit domain dialogue (Smith and Gordon,")
        assert sig.search("Figure 9: Performance of Uni-Parser, compared with")
        assert sig.search("Table 2: Results for English and")

    def test_imagenet_caption_does_not_swallow_body(self):
        from lib.caption_detection import merge_caption_lines
        caption = _block([_line("Figure 5: Training curves on ImageNet",
                                100, 100, 400, 112)])
        body = _block([_line("We further report results in the next section.",
                             100.5, 113.5, 420, 125.5)])
        merged = merge_caption_lines(
            caption, 0, FIGURE_PATTERN, following_blocks=[body],
        )
        assert "We further report" not in merged.text
        assert merged.line_count == 1

    def test_data_caption_does_not_swallow_body(self):
        from lib.caption_detection import merge_caption_lines
        caption = _block([_line("Figure 2: Distribution of the data",
                                100, 100, 400, 112)])
        body = _block([_line("Statistics were computed across all splits.",
                             100.5, 113.5, 420, 125.5)])
        merged = merge_caption_lines(
            caption, 0, FIGURE_PATTERN, following_blocks=[body],
        )
        assert "Statistics were computed" not in merged.text
        assert merged.line_count == 1


class TestMissingAssetFile:
    """BUG-133：index 引用的 PNG 缺失时，不插死链、不抑制原文、
    不得报告为已嵌入，应按 missing_file 计入遗漏。"""

    def _result(self, tmp_path, items):
        index_json = tmp_path / "index.json"
        index_json.write_text("[]", encoding="utf-8")
        (tmp_path / "paper.md").write_text("", encoding="utf-8")
        return {
            "enabled": True, "items": items, "omitted": [],
            "extracted_count": len(items), "index_json": str(index_json),
        }

    def test_missing_png_not_inserted_and_text_kept(self, tmp_path):
        from core.pdf_to_markdown import _place_assets_in_document
        doc = _md_doc_with_sassi_p35()
        n_blocks = len(doc.blocks)
        # 故意不创建 item["file"] 指向的 PNG
        result = self._result(tmp_path, [_sassi_table4_item()])
        _place_assets_in_document(doc, result, str(tmp_path / "paper.md"))
        assert all(getattr(b, "type", "") != "image" for b in doc.blocks)
        assert len(doc.blocks) == n_blocks
        assert result["items"] == []
        assert [o["status"] for o in result["omitted"]] == ["missing_file"]

    def test_missing_png_not_marked_embedded(self, tmp_path):
        from core.pdf_to_markdown import (
            _annotate_and_persist_embed_status,
            _place_assets_in_document,
            _summarize_embed_status,
        )
        doc = _md_doc_with_sassi_p35()
        item = _sassi_table4_item()
        result = self._result(tmp_path, [item])
        placement = _place_assets_in_document(
            doc, result, str(tmp_path / "paper.md"))
        _annotate_and_persist_embed_status(result, placement)
        assert item["referenced_in_markdown"] is False
        assert item["embed_mode"] is None
        summary = _summarize_embed_status(result)
        assert summary["embedded"] == 0
        assert summary["omitted"] == 1
        assert summary["omitted_reasons"].get("missing_file") == 1

    def test_existing_png_still_placed_inline(self, tmp_path):
        from core.pdf_to_markdown import _place_assets_in_document
        doc = _md_doc_with_sassi_p35()
        item = _sassi_table4_item()
        (tmp_path / item["file"]).write_bytes(b"x")
        result = self._result(tmp_path, [item])
        placement = _place_assets_in_document(
            doc, result, str(tmp_path / "paper.md"))
        assert [i["id"] for i in placement["inline"]] == ["4"]
        assert any(getattr(b, "type", "") == "image" for b in doc.blocks)
        assert result["omitted"] == []


class TestMarkdownImageSerialization:
    """BUG-134/135：用 CommonMark 实际解析，校验文件地址及 alt 原值。"""

    @pytest.mark.parametrize("path", [
        "../image assets/Figure_1.png",
        "assets/figure#draft?.png",
        "assets/accuracy%20.png",
        "../图表 图片/图1.png",
        "assets/figure(1.png",
        "assets/figure)1.png",
        "assets/Figure_1.png",
    ])
    def test_image_address_resolves_to_original_filename(self, path):
        from urllib.parse import unquote, urlsplit
        from markdown_it import MarkdownIt
        from lib.markdown import MarkdownBlock, render_block

        rendered = render_block(MarkdownBlock(type="image", path=path,
                                               caption="Figure 1: Results"))
        images = [child for token in MarkdownIt().parse(rendered)
                  for child in (token.children or []) if child.type == "image"]
        assert len(images) == 1
        address = urlsplit(images[0].attrGet("src"))
        assert not address.query and not address.fragment
        assert unquote(address.path) == path

    @pytest.mark.parametrize("caption", [
        "Figure 1: Probability mass in (0, 1]",
        "Figure 1: An unmatched [ label",
        r"Figure 1: A literal \] and \[ delimiter",
        "Figure 1: Results [0, 1]",
    ])
    def test_alt_preserves_literal_delimiters(self, caption):
        from markdown_it import MarkdownIt
        from lib.markdown import MarkdownBlock, render_block

        rendered = render_block(MarkdownBlock(type="image", path="assets/f.png",
                                               caption=caption))
        images = [child for token in MarkdownIt().parse(rendered)
                  for child in (token.children or []) if child.type == "image"]
        assert len(images) == 1
        assert images[0].attrGet("src") == "assets/f.png"
        # 4.2.0 的 HTML renderer 漏掉 text_special；解析树仍保留正确字面值。
        # 直接核验 CommonMark 解码后的 alt 子节点，避免把该依赖缺陷当作业务错误。
        parsed_alt = "".join(child.content for child in images[0].children or []
                             if child.type in ("text", "text_special"))
        assert parsed_alt == caption

    def test_inserted_screenshot_renders_with_space_path_and_interval_alt(self, tmp_path):
        from urllib.parse import unquote
        from markdown_it import MarkdownIt
        from core.pdf_to_markdown import (
            _place_assets_in_document, _annotate_and_persist_embed_status,
            _summarize_embed_status,
        )
        from lib.markdown import render_markdown

        assets = tmp_path / "image assets"
        assets.mkdir()
        item = _sassi_table4_item(caption="Table 4: Probability in (0, 1]")
        (assets / item["file"]).write_bytes(b"png-file-present")
        result = {"enabled": True, "items": [item], "omitted": [],
                  "index_json": str(assets / "index.json")}
        document = _md_doc_with_sassi_p35()
        placement = _place_assets_in_document(document, result, str(tmp_path / "paper.md"))
        _annotate_and_persist_embed_status(result, placement)
        images = [child for token in MarkdownIt().parse(render_markdown(document))
                  for child in (token.children or []) if child.type == "image"]
        assert len(images) == _summarize_embed_status(result)["embedded"] == 1
        assert (tmp_path / unquote(images[0].attrGet("src"))).is_file()
        assert item["suppressed_text_blocks"] > 0


class TestVerbCaptionMerge:
    """BUG-136：真题注保留续行，shows that/how 正文仍不得成为长题注。"""

    @pytest.mark.parametrize("head", [
        "Figure 1 shows the architecture of the proposed",
        "Table 1 presents the results of the proposed",
    ])
    def test_genuine_verb_caption_keeps_second_line(self, head):
        from lib.caption_detection import merge_caption_lines
        from lib.idents import FIGURE_LINE_RE, TABLE_LINE_RE

        block = _block([_line(head, 70, 189.25, 282, 202.99, size=10),
                        _line("encoder and decoder used for all experiments.",
                              70, 202.25, 282, 215.99, size=10)])
        pattern = FIGURE_LINE_RE if head.startswith("Figure") else TABLE_LINE_RE
        merged = merge_caption_lines(block, 0, pattern)
        assert merged is not None
        assert merged.text == head + " encoder and decoder used for all experiments."
        assert merged.line_count == 2
        assert merged.rect.y1 == pytest.approx(215.99)

    @pytest.mark.parametrize("head", [
        "Table 8 shows that RL plays a crucial role",
        "Figure 3 demonstrates how our encoder works",
        "Table 4 presents the results. The six factors",
        "Figure 1 indicates that the proposed system improves",
        "Figure 1 suggests that the proposed system improves",
        "Figure 1 describes how the proposed system improves",
    ])
    def test_body_reference_still_rejected(self, head):
        from lib.caption_detection import merge_caption_lines
        from lib.idents import FIGURE_LINE_RE, TABLE_LINE_RE

        block = _block([_line(head, 70, 189.25, 282, 202.99, size=10),
                        _line("are discussed in the next section.",
                              70, 202.25, 282, 215.99, size=10)])
        pattern = FIGURE_LINE_RE if head.startswith("Figure") else TABLE_LINE_RE
        assert merge_caption_lines(block, 0, pattern) is None


class TestCaptionDehyphenation:
    """BUG-137：题注跨行断词连字符应合并（sce-/nario→scenario），
    但 end-to-end、well-known 等真复合词必须保留连字符。"""

    def test_broken_word_joined_without_hyphen(self):
        from lib.caption_detection import merge_caption_lines
        caption = _block([
            _line("Figure 5: Our model uni-", 47.9, 100, 300, 112),
            _line("formly outperforms baselines", 47.9, 113, 300, 125),
        ])
        merged = merge_caption_lines(caption, 0, FIGURE_PATTERN)
        assert "uniformly" in merged.text
        assert "uni- formly" not in merged.text

    def test_scenario_style_broken_word(self):
        from lib.caption_detection import merge_caption_lines
        caption = _block([
            _line("Figure 1: Arbitration sce-", 47.9, 100, 300, 112),
            _line("nario parameters for each device loca-", 47.9, 113, 300, 125),
            _line("tion in the home", 47.9, 126, 300, 138),
        ])
        merged = merge_caption_lines(caption, 0, FIGURE_PATTERN)
        assert "scenario" in merged.text
        assert "location" in merged.text

    def test_end_to_end_compound_keeps_hyphen(self):
        from lib.caption_detection import merge_caption_lines
        caption = _block([
            _line("Figure 2: The end-to-", 47.9, 100, 300, 112),
            _line("end pipeline overview", 47.9, 113, 300, 125),
        ])
        merged = merge_caption_lines(caption, 0, FIGURE_PATTERN)
        assert "end-to-end" in merged.text

    def test_well_known_compound_keeps_hyphen(self):
        from lib.caption_detection import merge_caption_lines
        caption = _block([
            _line("Figure 3: Comparison with well-", 47.9, 100, 300, 112),
            _line("known baselines", 47.9, 113, 300, 125),
        ])
        merged = merge_caption_lines(caption, 0, FIGURE_PATTERN)
        assert "well-known" in merged.text

    def test_uppercase_next_line_keeps_space(self):
        from lib.caption_detection import merge_caption_lines
        caption = _block([
            _line("Figure 4: The Encoder-", 47.9, 100, 300, 112),
            _line("Decoder architecture", 47.9, 113, 300, 125),
        ])
        merged = merge_caption_lines(caption, 0, FIGURE_PATTERN)
        assert "Encoder- Decoder" in merged.text


class TestAutocropXRangeAdoption:
    """BUG-138：autocrop 被高度守卫整体否决时，x 收窄若有原生对象
    支撑仍应保留（Alexa Figure 1 右栏图 x 停在页边距 586 的回归）。
    Phase C 栏位几何只能夹栏的内侧缘，外侧缘只能靠像素证据收窄。"""

    def test_adopts_x_when_object_supported(self):
        import fitz
        from lib.pixel_detect import autocrop_x_range_with_object_support
        clip = fitz.Rect(311, 522, 586, 675)
        autocrop = fitz.Rect(343, 530, 528, 670)
        objects = [fitz.Rect(350.5, 527.6, 521.1, 668.9)]
        adopted = autocrop_x_range_with_object_support(clip, autocrop, objects)
        assert adopted is not None
        assert adopted.x0 == pytest.approx(343)
        assert adopted.x1 == pytest.approx(528)
        assert adopted.y0 == pytest.approx(522)
        assert adopted.y1 == pytest.approx(675)

    def test_rejects_without_objects(self):
        import fitz
        from lib.pixel_detect import autocrop_x_range_with_object_support
        clip = fitz.Rect(311, 522, 586, 675)
        autocrop = fitz.Rect(343, 530, 528, 670)
        assert autocrop_x_range_with_object_support(clip, autocrop, []) is None

    def test_rejects_when_outside_objects_dominate(self):
        import fitz
        from lib.pixel_detect import autocrop_x_range_with_object_support
        clip = fitz.Rect(100, 100, 400, 300)
        autocrop = fitz.Rect(240, 110, 260, 290)
        objects = [fitz.Rect(110, 110, 230, 290), fitz.Rect(245, 110, 255, 290)]
        assert autocrop_x_range_with_object_support(clip, autocrop, objects) is None

    def test_rejects_trivial_narrowing(self):
        import fitz
        from lib.pixel_detect import autocrop_x_range_with_object_support
        clip = fitz.Rect(311, 522, 586, 675)
        autocrop = fitz.Rect(313, 522, 584, 675)
        objects = [fitz.Rect(350.5, 527.6, 521.1, 668.9)]
        assert autocrop_x_range_with_object_support(clip, autocrop, objects) is None

    def test_never_widens_beyond_clip(self):
        import fitz
        from lib.pixel_detect import autocrop_x_range_with_object_support
        clip = fitz.Rect(311, 522, 586, 675)
        autocrop = fitz.Rect(300, 522, 600, 675)
        objects = [fitz.Rect(350.5, 527.6, 521.1, 668.9)]
        assert autocrop_x_range_with_object_support(clip, autocrop, objects) is None

    def test_right_column_figure_x_narrowed_when_autocrop_height_rejected(
            self, tmp_path):
        """Alexa p1 真实几何缩减（009 批 debug legend）：右栏图在上、
        多行题注在页面底部，左栏正文与图带同高，baseline 高 520pt
        触发高度守卫否决 autocrop。修复前 final x 停在 311–586。"""
        import importlib

        import fitz
        figure_module = importlib.import_module("lib.extract_figures")

        pdf_path = tmp_path / "alexa_like.pdf"
        doc = fitz.open()
        page = doc.new_page(width=612, height=792)
        for i, y in enumerate(range(208, 684, 11)):
            page.insert_text((54.4, y), f"left column body line {i:02d} with more filler text to span.",
                             fontsize=9)
        for i, y in enumerate(range(208, 434, 11)):
            page.insert_text((315.2, y), f"right column body line {i:02d} with more filler text.",
                             fontsize=9)
        pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 120, 100))
        pix.clear_with(120)
        page.insert_image(fitz.Rect(350.5, 527.6, 521.1, 668.9), pixmap=pix)
        page.insert_textbox(
            fitz.Rect(315.2, 677.5, 559.0, 725.0),
            "Figure 1: The end to end arbitration model architecture. "
            "We produce feature embeddings for each device.",
            fontsize=9,
        )
        doc.save(pdf_path)
        doc.close()

        records = figure_module.extract_figures(
            str(pdf_path), str(tmp_path / "out"),
            dpi=150, clip_height=520.0, margin_x=26.0,
            autocrop=True, autocrop_mask_text=True, text_trim=True,
        )
        assert len(records) == 1
        x0, _y0, x1, _y1 = records[0].final_bbox
        assert x0 <= 350.5 and x1 >= 521.1, (x0, x1)  # 图像完整覆盖
        assert x0 >= 315.0, x0  # 不吞左栏正文
        assert x1 <= 545.0, x1  # 右侧页边距留白被收窄（修复前为 586）


class TestAutocropTextSafety:
    """BUG-139：对象面积支撑不能代替图内文字完整性。"""

    @pytest.mark.parametrize("label_y", [575, 633])
    def test_native_image_side_label_survives_extraction(self, tmp_path, label_y):
        import fitz
        import json
        from core.extract_pdf_assets import main

        pdf = tmp_path / "native-label.pdf"
        with fitz.open() as doc:
            page = doc.new_page(width=600, height=792)
            pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 180, 100))
            pix.clear_with(100)
            page.insert_image(fitz.Rect(50, 520, 230, 620), pixmap=pix)
            label = "EXPERIMENTAL SETTINGS HIDDEN SIZE 1024 LAYERS 24"
            page.insert_text((245, label_y), label, fontsize=10)
            label_rect = page.search_for(label)[0]
            page.insert_textbox(
                fitz.Rect(40, 680, 570, 730),
                "Figure 1: Demonstration of an architecture with a compact native image and a wide text label",
                fontsize=10,
            )
            doc.save(pdf)
        assert main([
            "--pdf", str(pdf), "--preset", "robust", "--no-tables",
            "--out-dir", str(tmp_path / "images"),
            "--out-text", str(tmp_path / "txt/text.txt"),
        ]) == 0
        items = json.loads((tmp_path / "images/index.json").read_text())["items"]
        assert len(items) == 1
        assert fitz.Rect(items[0]["final_bbox"]).contains(label_rect)

    @pytest.mark.parametrize("bbox", [
        (245, 140, 380, 155),  # 整行在拟采用框右侧
        (180, 140, 270, 155),  # 部分文字在拟采用框右侧
        (110, 140, 165, 155),  # 部分文字在拟采用框左侧
        (245, 192, 380, 207),  # 图旁注释略低于位图底边
        (245, 115, 380, 128),  # 图旁注释略高于位图顶边
        (245, 210, 380, 225),  # 无证据排除的原框内文字也不能静默丢失
    ])
    def test_rejects_lost_labels(self, bbox):
        import fitz
        from lib.pixel_detect import autocrop_x_range_with_object_support
        assert autocrop_x_range_with_object_support(
            fitz.Rect(100, 100, 400, 300), fitz.Rect(150, 125, 230, 180),
            [fitz.Rect(160, 130, 220, 190)],
            text_lines=[(fitz.Rect(bbox), 10, "Graph label")],
            min_width_ratio=0.2,
        ) is None

    @pytest.mark.parametrize("bbox", [
        (10, 140, 90, 155),    # 原框外的另一栏正文
        (245, 310, 380, 325), # 原框纵向范围之外的正文
        (165, 140, 210, 155), # 新框完整保留的图内文字
    ])
    def test_keeps_safe_narrowing(self, bbox):
        import fitz
        from lib.pixel_detect import autocrop_x_range_with_object_support
        adopted = autocrop_x_range_with_object_support(
            fitz.Rect(100, 100, 400, 300), fitz.Rect(150, 125, 230, 180),
            [fitz.Rect(160, 130, 220, 190)],
            text_lines=[(fitz.Rect(bbox), 10, "Text")],
            min_width_ratio=0.2,
        )
        assert adopted is not None
        assert adopted.x0 == 150 and adopted.x1 == 230


class TestCaptionWordEvidence:
    """BUG-140：完整词形证据优先于断词前缀启发式。"""

    @pytest.mark.parametrize("left,right,forms,expected", [
        ("Pro-", "gramBench results", {"programbench"}, "ProgramBench results"),
        ("reasoning-", "intensive tasks", {"reasoning-intensive"}, "reasoning-intensive tasks"),
        ("in-", "formation flow", {"information"}, "information flow"),
        ("re-", "sults overview", {"results"}, "results overview"),
        ("encoder-", "decoder model", {"encoder-decoder", "encoderdecoder"}, "encoder-decoder model"),
        ("end-to-", "end system", {"end-to-end"}, "end-to-end system"),
    ])
    def test_uses_complete_word_form(self, left, right, forms, expected):
        from lib.caption_detection import merge_caption_lines
        block = _block([
            _line("Figure 10: " + left, 60, 100, 300, 112),
            _line(right, 60, 113, 300, 125),
        ])
        caption = merge_caption_lines(block, 0, FIGURE_PATTERN, word_forms=forms)
        assert caption.text == "Figure 10: " + expected

    def test_index_uses_evidence_from_another_page(self):
        import fitz
        from lib.caption_detection import build_caption_index
        with fitz.open() as doc:
            page = doc.new_page()
            page.insert_text((60, 100), "ProgramBench and reasoning-intensive tasks", fontsize=10)
            page = doc.new_page()
            page.insert_text((60, 100), "Figure 10: Pro-", fontsize=10)
            page.insert_text((60, 113), "gramBench results", fontsize=10)
            page.insert_text((60, 300), "Table 12: reasoning-", fontsize=10)
            page.insert_text((60, 313), "intensive tasks", fontsize=10)
            index = build_caption_index(doc)
            assert index.candidates["figure_10"][0].text == "Figure 10: ProgramBench results"
            assert index.candidates["table_12"][0].text == "Table 12: reasoning-intensive tasks"

    @pytest.mark.parametrize("smart", [True, False])
    def test_extracted_caption_and_filename_use_document_spelling(self, tmp_path, smart):
        import fitz
        import importlib
        pdf = tmp_path / "word-evidence.pdf"
        with fitz.open() as doc:
            page = doc.new_page()
            page.insert_text((60, 100), "ProgramBench and reasoning-intensive tasks", fontsize=10)
            page = doc.new_page()
            pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 100, 100))
            pix.clear_with(100)
            for ident, top, first, second in [
                (10, 100, "Pro-", "gramBench results"),
                (12, 400, "reasoning-", "intensive tasks"),
            ]:
                page.insert_image(fitz.Rect(60, top, 260, top + 100), pixmap=pix)
                page.insert_text((60, top + 130), f"Figure {ident}: {first}", fontsize=10)
                page.insert_text((60, top + 143), second, fontsize=10)
            doc.save(pdf)
        records = importlib.import_module("lib.extract_figures").extract_figures(
            str(pdf), str(tmp_path / "images"), smart_caption_detection=smart, dpi=100,
        )
        by_id = {r.ident: r for r in records}
        assert "ProgramBench" in by_id["10"].caption
        assert "ProgramBench" in Path(by_id["10"].out_path).name
        assert "reasoning-intensive" in by_id["12"].caption

    def test_word_collection_does_not_turn_broken_lines_into_evidence(self):
        import fitz
        from lib.caption_detection import collect_caption_word_forms
        with fitz.open() as doc:
            page = doc.new_page()
            page.insert_text((60, 100), "Pro-", fontsize=10)
            page.insert_text((60, 113), "gramBench", fontsize=10)
            page.insert_text((60, 150), "Real reasoning-intensive tasks", fontsize=10)
            forms = collect_caption_word_forms(doc)
            assert "reasoning-intensive" in forms
            assert "programbench" not in forms
            assert "pro-grambench" not in forms
