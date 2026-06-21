---
name: pdf-markdown-summary
description: Convert PDFs, especially research papers and technical reports, into structured Markdown with extracted figure/table screenshots, or prepare figure-aware reading summaries. Use for "PDF 转 Markdown", "转 md", "提取图表", "论文摘要", "带图摘要", "阅读笔记", "论文阅读摘要", "资料库入库", "处理这篇论文", "extract figures/tables from PDF", and "paper summary with figures". Do not use for generic PDF merge/split/rotate/watermark/encrypt/form-filling tasks; use the system pdf skill for those.
---

# PDF Markdown Summary

Use this skill to convert PDFs into Markdown, extract Figure/Table PNG assets, and prepare text-plus-image materials for paper reading summaries.

## Core Workflow

1. Choose the entry point:
   - `scripts/pdf_to_markdown.py` for PDF -> Markdown.
   - `scripts/summarize_pdf.py` for summary assets only.
   - `scripts/process_pdf.py` for Markdown plus summary assets in one run.
   - `scripts/extract_pdf_assets.py` only when tuning figure/table extraction.
2. Run the script with `--preset robust` unless a narrow diagnostic task requires custom flags.
3. Inspect generated Markdown, `images/index.json`, extracted PNGs, and any `--debug-visual` overlays when crop quality matters.
4. For summaries, read both `text/<paper>.txt` and the extracted images before writing the final note.

## Commands

```bash
python3 scripts/pdf_to_markdown.py --pdf "<paper>.pdf" --out "<paper>.md" --images figures --tables screenshot
```

```bash
python3 scripts/summarize_pdf.py --pdf "<paper>.pdf" --preset robust
```

```bash
python3 scripts/process_pdf.py --pdf "<paper>.pdf" --out "<paper>.md" --preset robust
```

For crop diagnostics:

```bash
python3 scripts/extract_pdf_assets.py --pdf "<paper>.pdf" --preset robust --debug-visual --debug-captions
```

## Output Rules

- Use relative image links in generated Markdown.
- Keep table screenshots when structure extraction is unavailable; do not drop tables.
- For summaries, default to Chinese unless the user asks for another language.
- Always use both the text file and Figure/Table images when writing a figure-aware summary.
- Explain important figures and tables briefly instead of listing images without interpretation.

## Extraction Capabilities

The asset extractor includes:

- Smart caption scoring using position, format, structure, and context.
- Identifier parsing for numeric, roman, S-prefix, Extended Data, Chinese Figure/Table labels.
- Direction detection using local evidence, global anchor fallback, page-position heuristics, and explicit overrides.
- Baseline limiting by neighboring captions and layout text blocks.
- Figure refinement for text trimming, object alignment, column-aware X clipping, layout adjustment, autocrop, and figure-title recovery.
- Table refinement for multiline header recovery, rendered horizontal-rule compensation, table-band detection, width restoration, text-bbox padding, wrapped-tail preservation, and far-side section-heading trimming.
- Debug overlays showing `baseline`, `phase_a`, `phase_b`, and `final` regions.

## References

Load only the reference needed for the current task:

- `references/pdf-to-markdown.md` for Markdown conversion workflow.
- `references/pdf-summary.md` for figure-aware summary workflow.
- `references/cli-options.md` for all CLI flags and extraction tuning options.
