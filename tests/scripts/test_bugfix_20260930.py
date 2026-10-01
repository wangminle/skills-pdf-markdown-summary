#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
20260930 评审回归：题注识别三处漏洞

复现来源（tests/results/20260930-029 两篇真实 PDF 的误提取）：

1. 上角标脚注编号在文本层与标签词融合成假题注。
   Uni-Parser p4 表体行 "Table² | Multi-modal Text | ..."（² 为 flags&1
   上角标 span）被拼成 "Table2 ..."，匹配 TABLE_LINE_RE 成为假 Table 2
   题注：截断 Table 1 底边、占用编号 "2" 导致 p12 真 Table 2 被
   seen_counts 跳过、并同源产生假 Figure 5。
   修复：组建候选行文本时剔除上角标 span。

2. FIGURE_LINE_RE 缺少附录字母编号分支。
   PaddleOCR-VL 附录的 Figure A1-A29（共 42 行题注）全部不匹配；
   TABLE_LINE_RE 自 P1-08 起就有 (?P<letter_id>[A-Z]\\d+)，图侧漏加。
   修复：FIGURE_LINE_RE 与 extract_figure_ident 镜像表侧实现。

3. 罗马数字分支无边界守卫。
   "Figures in section D.6 detail ..." 的 "in" 首字母被当成罗马数字 I，
   生成假 Figure I 资产（框住整段正文，靠验收 text_pollution 兜底拒绝）。
   修复：roman/s_id 的罗马分支加 (?![A-Za-z]) 负向守卫。
"""

import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPTS_DIR = os.path.join(PROJECT_ROOT, "skills", "pdf-markdown-summary", "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from lib.idents import (
    FIGURE_LINE_RE,
    TABLE_LINE_RE,
    extract_figure_ident,
    extract_table_ident,
    line_text_skip_superscript,
)


# ============================================================================
# 1. 上角标脚注剔除
# ============================================================================

class TestSuperscriptFootnoteStripped:
    """Uni-Parser p4：Table²/Figure⁵ 的数字是 flags&1 上角标 span。"""

    def test_drops_superscript_spans(self):
        spans = [
            {"text": "Table", "flags": 4, "size": 9.0},
            {"text": "2", "flags": 5, "size": 6.0},  # bit0=superscript
        ]
        assert line_text_skip_superscript(spans) == "Table"

    def test_keeps_normal_spans(self):
        spans = [
            {"text": "Table 2:", "flags": 4, "size": 10.0},
            {"text": " Distribution of document sources", "flags": 4, "size": 10.0},
        ]
        assert (
            line_text_skip_superscript(spans)
            == "Table 2: Distribution of document sources"
        )

    def test_missing_flags_default_kept(self):
        spans = [{"text": "Figure 3: Overview"}]
        assert line_text_skip_superscript(spans) == "Figure 3: Overview"

    def test_fake_table_caption_no_longer_matches(self):
        spans = [
            {"text": "Table", "flags": 4},
            {"text": "2", "flags": 5},
        ]
        assert TABLE_LINE_RE.match(line_text_skip_superscript(spans).strip()) is None

    def test_fake_figure_caption_no_longer_matches(self):
        spans = [
            {"text": "Figure", "flags": 4},
            {"text": "5", "flags": 5},
        ]
        assert FIGURE_LINE_RE.match(line_text_skip_superscript(spans).strip()) is None


# ============================================================================
# 2. Figure 附录字母编号（Figure A1-A29）
# ============================================================================

class TestFigureLetterId:
    """PaddleOCR-VL 附录：Figure A2 | ... 形式的真实题注。"""

    def test_figure_letter_id_matches(self):
        m = FIGURE_LINE_RE.match("Figure A2 | End-to-End Inference Performance")
        assert m is not None
        assert extract_figure_ident(m) == "A2"

    def test_figure_letter_id_double_digit(self):
        m = FIGURE_LINE_RE.match("Figure A12 | The Reading Order results")
        assert m is not None
        assert extract_figure_ident(m) == "A12"

    def test_table_letter_id_still_works(self):
        m = TABLE_LINE_RE.match("Table A1 | Supported Languages")
        assert m is not None
        assert extract_table_ident(m) == "A1"

    def test_numeric_and_roman_unaffected(self):
        assert extract_figure_ident(FIGURE_LINE_RE.match("Figure 3: Overview")) == "3"
        assert extract_figure_ident(FIGURE_LINE_RE.match("Figure IV. Results")) == "IV"
        m = FIGURE_LINE_RE.match("Figure 3a: Sub-caption")
        assert m is not None
        assert extract_figure_ident(m) == "3"


# ============================================================================
# 3. 罗马数字边界守卫
# ============================================================================

class TestRomanBoundaryGuard:
    """'Figures in ...' / 'Tables in ...' 不得匹配出罗马数字 I。"""

    def test_figures_in_section_rejected(self):
        text = "Figures in section D.6 detail the formula recognition performance."
        assert FIGURE_LINE_RE.match(text) is None

    def test_tables_in_appendix_rejected(self):
        assert TABLE_LINE_RE.match("Tables in the appendix summarize results.") is None

    def test_figure_very_rejected(self):
        # "very" 首字母 v 是合法罗马字符，守卫后同样不得匹配
        assert FIGURE_LINE_RE.match("Figure very large shows") is None

    def test_real_roman_captions_kept(self):
        assert extract_figure_ident(FIGURE_LINE_RE.match("Figure IV. Results")) == "IV"
        assert extract_table_ident(TABLE_LINE_RE.match("Table II: Comparison")) == "II"
        m = FIGURE_LINE_RE.match("Figure IX | Overall performance")
        assert m is not None
        assert extract_figure_ident(m) == "IX"


# ============================================================================
# 4. 复数区间引用（letter_id 放开后新可匹配的句式）
# ============================================================================

class TestPluralRangeReference:
    """PaddleOCR-VL p32："Figures A9-A11 in section D.2 illustrate ..." 是正文
    引用，不得成为 Figure A9 的题注（否则占用编号，真 A9 被 seen_counts 跳过）。
    """

    def test_hyphen_range_no_spaces_is_reference(self):
        from lib.caption_detection import is_likely_reference_context
        text = "Figures A9-A11 in section D.2 illustrate the superior ability."
        assert is_likely_reference_context(text) is True

    def test_and_range_is_reference(self):
        from lib.caption_detection import is_likely_reference_context
        assert is_likely_reference_context("Figures A12 and A13 in section D.3 demonstrate.") is True

    def test_numeric_range_still_reference(self):
        from lib.caption_detection import is_likely_reference_context
        assert is_likely_reference_context("Figures 3 and 4 show the results.") is True

    def test_real_letter_caption_not_reference(self):
        from lib.caption_detection import is_likely_reference_context
        text = "Figure A9 | The Layout Detection results for various types of documents."
        assert is_likely_reference_context(text) is False


# ============================================================================
# 5. 数字标记尾注（Uni-Parser Table 1 的 ¹-⁵ 脚注）
# ============================================================================

class TestDigitMarkerTableNotes:
    """尾注行首是 1-2 位数字标记（"2 Grouped with ..."）时，_table_note_rects
    必须识别，否则 trim_table_clip_far_side_body 会把 ">50字+句点" 的尾注行
    当正文，把表框底边切进尾注中间（Uni-Parser Table 1 final y1=531.8 截断
    尾注³ 的成因）。"""

    def _make_lines(self, y0=505.0):
        import fitz
        texts = [
            "1 Grouped with formula ID.",
            "2 Grouped with table caption and table footnote.",
            "3 Grouped with image caption.",
            "4 Grouped with molecule identifier and Markush description.",
            "5 Grouped with figure legend and figure caption.",
        ]
        lines = []
        y = y0
        for t in texts:
            lines.append((fitz.Rect(120.0, y, 120.0 + len(t) * 4.4, y + 9.0), 9.0, t))
            y += 10.0
        return lines

    def test_digit_notes_recognized(self):
        import fitz
        from lib.table_refine import _table_note_rects
        clip = fitz.Rect(114.0, 243.0, 498.0, 563.0)
        notes = _table_note_rects(clip, self._make_lines())
        assert len(notes) == 5

    def test_digit_notes_not_trimmed_as_body(self):
        import fitz
        from lib.table_refine import trim_table_clip_far_side_body
        clip = fitz.Rect(114.0, 243.0, 498.0, 563.0)
        caption = fitz.Rect(217.0, 228.0, 394.0, 240.0)
        lines = self._make_lines()
        lines.append((fitz.Rect(114.0, 580.0, 498.0, 591.0), 10.0,
                      "Considering the wide variety of authoring and rendering styles "
                      "across layouts and modalities, we employ a large-scale dataset."))
        trimmed = trim_table_clip_far_side_body(clip, caption, lines, "below")
        assert trimmed.y1 >= 558.0  # 尾注⁵ 底边仍在框内


# ============================================================================
# 6. BUG-126：数字脚注反例——编号小节、跳号、单标记带正文不得识别为尾注
# ============================================================================

class TestDigitNoteFalsePositives:
    """_DIGIT_NOTE_START_RE 会匹配任意 1-2 位数字开头的行：编号小节标题
    "7 Experimental details"、跳号序列 1→8、单标记 "1 Introduction" 带正文
    都曾被当成尾注块，expand_clip_to_table_notes 据此把截图底边扩进正文
    （实测 y1 200→225）。尾注块必须从 1（或字母 a）开始、标记严格递增，
    数字块至少要有 1→2 两个顺序标记才成立。"""

    @staticmethod
    def _lines(*texts, y0=200.0, step=10.0, size=9.0, clip_x=(114.0, 498.0)):
        import fitz
        lines = []
        y = y0
        for t in texts:
            lines.append((fitz.Rect(clip_x[0], y, min(clip_x[0] + len(t) * 4.4, clip_x[1]),
                                   y + 9.0), size, t))
            y += step
        return lines

    def test_numbered_section_heading_not_note(self):
        import fitz
        from lib.table_refine import _table_note_rects
        clip = fitz.Rect(114.0, 60.0, 498.0, 200.0)
        lines = self._lines(
            "7 Experimental details",
            "We trained the model with the following setup and hyperparameters.",
            "All runs used the same random seeds across benchmarks.")
        assert _table_note_rects(clip, lines) == []

    def test_expand_does_not_grow_over_section(self):
        import fitz
        from lib.table_refine import expand_clip_to_table_notes
        clip = fitz.Rect(114.0, 60.0, 498.0, 200.0)
        lines = self._lines("7 Experimental details",
                            "Body paragraph that belongs to the section, not the table.")
        grown = expand_clip_to_table_notes(clip, lines)
        assert grown.y1 == 200.0  # 修复前会被扩到 ~225

    def test_marker_jump_1_to_8_rejected(self):
        import fitz
        from lib.table_refine import _table_note_rects
        clip = fitz.Rect(114.0, 60.0, 498.0, 200.0)
        lines = self._lines("1 First candidate line.",
                            "8 Eighth item, not a sequential note.")
        assert _table_note_rects(clip, lines) == []

    def test_single_marker_with_body_rejected(self):
        import fitz
        from lib.table_refine import _table_note_rects
        clip = fitz.Rect(114.0, 60.0, 498.0, 200.0)
        lines = self._lines(
            "1 Introduction",
            "This paragraph is body text that follows the numbered heading.",
            "It continues with more sentences that must not be swallowed.")
        assert _table_note_rects(clip, lines) == []

    def test_letter_block_must_start_at_a(self):
        import fitz
        from lib.table_refine import _table_note_rects
        clip = fitz.Rect(114.0, 60.0, 498.0, 200.0)
        lines = self._lines("b Second letter note without a visible a.",
                            "c Third letter note.")
        assert _table_note_rects(clip, lines) == []

    def test_minimal_two_digit_notes_still_accepted(self):
        import fitz
        from lib.table_refine import _table_note_rects
        clip = fitz.Rect(114.0, 60.0, 498.0, 200.0)
        lines = self._lines("1 Grouped with formula ID.",
                            "2 Grouped with table caption.")
        assert len(_table_note_rects(clip, lines)) == 2


# ============================================================================
# 7. BUG-127/128：单条数字脚注保留、英文冠词 a 续行不误判为标记
# ============================================================================

class TestSingleDigitNoteAndArticleContinuation:
    """BUG-126 的 ≥2 标记硬规则把合法的「只有 ¹ 一条」脚注整体丢弃
    （BUG-127）；字母标记正则 ^[a-z] 把续行开头的冠词 "a"（"a random
    subset…"）当成脚注编号，递增检查因此截断后续内容（BUG-128）。
    修正口径：单标记块最多带 1 条续行；标记分数字/字母两个命名空间，
    异类起始行一律按续行处理。"""

    @staticmethod
    def _lines(*texts, y0=200.0, step=10.0, size=9.0, clip_x=(114.0, 498.0)):
        import fitz
        lines = []
        y = y0
        for t in texts:
            lines.append((fitz.Rect(clip_x[0], y, min(clip_x[0] + len(t) * 4.4, clip_x[1]),
                                   y + 9.0), size, t))
            y += step
        return lines

    def test_single_digit_note_kept(self):
        import fitz
        from lib.table_refine import _table_note_rects
        clip = fitz.Rect(114.0, 60.0, 498.0, 200.0)
        notes = _table_note_rects(clip, self._lines("1 Grouped with formula ID."))
        assert len(notes) == 1

    def test_single_digit_note_with_one_wrap_kept(self):
        import fitz
        from lib.table_refine import _table_note_rects
        clip = fitz.Rect(114.0, 60.0, 498.0, 200.0)
        notes = _table_note_rects(clip, self._lines(
            "1 Grouped with table caption and table",
            "footnote."))
        assert len(notes) == 2

    def test_single_digit_note_with_two_body_lines_rejected(self):
        import fitz
        from lib.table_refine import _table_note_rects
        clip = fitz.Rect(114.0, 60.0, 498.0, 200.0)
        notes = _table_note_rects(clip, self._lines(
            "1 Introduction",
            "Body paragraph line one that follows the heading.",
            "Body paragraph line two that must not be swallowed."))
        assert notes == []

    def test_article_a_continuation_not_marker(self):
        import fitz
        from lib.table_refine import _table_note_rects
        clip = fitz.Rect(114.0, 60.0, 498.0, 200.0)
        notes = _table_note_rects(clip, self._lines(
            "1 Evaluated on a random subset of",
            "a random subset was also used for",  # 冠词 a 开头，不是标记
            "2 Grouped with figure legend."))
        assert len(notes) == 3  # BUG-128 修复前在冠词行被截断为 1

    def test_digit_marker_still_breaks_in_letter_block(self):
        import fitz
        from lib.table_refine import _table_note_rects
        clip = fitz.Rect(114.0, 60.0, 498.0, 200.0)
        notes = _table_note_rects(clip, self._lines(
            "a These 19 languages are supported.",
            "3 Not a letter marker, treated as continuation."))
        # 数字起始行在字母块中按普通续行处理（BUG-128 命名空间规则），
        # 不触发递增检查、不截断。
        assert len(notes) == 2


# ============================================================================
# 8. BUG-129：字母块内的冠词 a 续行、Note: 开头块的续行不得被当作脚注标记
# ============================================================================

class TestNoteBlockMarkerNamespaces:
    """BUG-128 只处理了「数字块里的冠词 a」与「字母块里的数字行」，漏了两类
    同样会整块丢脚注的输入（HEAD 均接受 3 行，BUG-127/128 修复后为 0 行）：
    1. 字母块里的冠词 a 续行（"a Results … / a random subset … / b …"）：
       97 != 97+1 触发跳号 break，单标记块再被整体拒绝；
    2. "Note:" 开头的块：首行不是标记，但续行里 "a random…" / "95 percent…"
       被当成第一个标记，随后的第 3 行命中单标记续行限额，整块判空。
    修正口径：字母块里非递增的 a 是冠词续行；首行不是标记的块，续行一律
    按普通文字处理。"""

    _lines = staticmethod(TestSingleDigitNoteAndArticleContinuation._lines)

    @staticmethod
    def _clip():
        import fitz
        return fitz.Rect(114.0, 60.0, 498.0, 200.0)

    def _count(self, *texts, step=11.0):
        from lib.table_refine import _table_note_rects
        return len(_table_note_rects(self._clip(), self._lines(*texts, y0=202.0, step=step)))

    def test_letter_block_article_a_continuation_kept(self):
        assert self._count(
            "a Results are computed on",
            "a random subset of the evaluation dataset.",
            "b Standard errors are reported.") == 3

    def test_letter_block_article_a_after_first_note(self):
        assert self._count(
            "a First note that continues",
            "a bit onto the second line.",
            "b Second note.") == 3

    def test_letter_block_article_a_after_b(self):
        assert self._count(
            "a First note.",
            "b Second note that continues onto",
            "a second line of the same note.",
            "c Third note.") == 4

    def test_letter_sequence_a_b_c_still_accepted(self):
        assert self._count("a First.", "b Second.", "c Third.") == 3

    def test_letter_marker_jump_still_rejected(self):
        """a→c 跳号不是冠词，仍按断序处理：块在此截断（只剩 1 条 → 判空）。"""
        assert self._count("a First note.", "c Skipped letter note.") == 0

    def test_note_prefix_article_a_wrap_kept(self):
        assert self._count(
            "Note: Results are computed on",
            "a random subset of the dataset",
            "and averaged over runs.") == 3

    def test_note_prefix_digit_start_wrap_kept(self):
        assert self._count(
            "Note: Values are reported with",
            "95 percent confidence intervals",
            "computed by bootstrap.") == 3

    def test_note_prefix_plain_continuation_unchanged(self):
        assert self._count(
            "Note: Values are reported in percent",
            "unless stated otherwise.") == 2

    def test_note_prefix_still_stops_at_size_change(self):
        """字号差 >1.5 仍是块边界：Note 块不吞更大字号的后续行。"""
        import fitz
        from lib.table_refine import _table_note_rects
        lines = self._lines("Note: Values are reported in percent.", y0=202.0)
        lines.append((fitz.Rect(114.0, 213.0, 300.0, 226.0), 12.0, "7.1 Conclusion"))
        assert len(_table_note_rects(self._clip(), lines)) == 1
