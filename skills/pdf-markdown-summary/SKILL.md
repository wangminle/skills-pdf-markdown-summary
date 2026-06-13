---
name: pdf-markdown-summary
description: Use this skill when the user wants to turn a PDF (especially a research paper or technical report) into well-structured Markdown with extracted figures/tables, or generate a reading summary with embedded images. Do NOT trigger for general PDF operations like merge, split, rotate, watermark, encrypt, or form-filling — those belong to the system pdf skill. Trigger specifically for "PDF 转 Markdown", "转 md", "提取图表", "论文摘要", "带图摘要", "阅读笔记", "论文阅读摘要", "资料库入库", "处理这篇论文", "extract figures from PDF", "paper summary with figures".
---

# PDF Markdown Summary

Convert PDF documents — especially research papers and technical reports — into well-structured Markdown with extracted figure/table assets, or generate a Chinese reading summary with embedded images.

## When to Use This Skill

**Use this skill when the user wants to:**

- Convert a PDF to well-structured Markdown (preserve headings, paragraphs, formulas)
- Extract figures, tables, or diagrams from a PDF as standalone PNG images
- Generate a reading summary of a research paper with embedded figures
- Prepare PDF content for knowledge-base ingestion
- Create a Chinese or English paper reading note ("阅读笔记")

**Do NOT use this skill when the user wants to:**

- Merge, split, rotate, watermark, or encrypt PDFs → use the system `pdf` skill
- Fill PDF forms → use the system `pdf` skill
- Create PDFs from scratch → use the system `pdf` skill
- Basic OCR on scanned documents → use the system `pdf` skill

## Three Workflows

### 1. PDF-to-Markdown (转 Markdown)

Convert a PDF into structured Markdown with extracted assets.

```bash
python3 scripts/pdf_to_markdown.py --pdf "<paper>.pdf" --out "<paper>.md"
```

Outputs:
- `{stem}.md` — structured Markdown document
- `images/Figure_*.png`, `images/Table_*.png` — extracted assets
- `images/index.json` — asset index with captions, pages, identifiers
- `text/{stem}.txt` — plain text extraction
- `text/conversion_report.json` — conversion quality report

### 2. PDF Summary (论文摘要)

Extract text and figure assets, then write a reading summary with embedded images.

```bash
python3 scripts/summarize_pdf.py --pdf "<paper>.pdf" --preset robust
```

After the command finishes:
1. Read `text/<paper>.txt` for full paper text
2. Read `images/index.json` and inspect all `images/*.png`
3. Write `{paper}_阅读摘要-{date}.md` with embedded relative image links

### 3. Complete Processing (完整处理)

Run Markdown conversion and summary preparation together.

```bash
python3 scripts/process_pdf.py --pdf "<paper>.pdf" --out "<paper>.md" --preset robust
```

## Output Rules

**For Markdown conversion:**
- Use relative image paths: `images/Figure_1_xxx.png`
- Preserve headings, paragraphs, and document structure
- If table structure extraction fails, use screenshot fallback — never drop tables

**For summaries:**
- Default language: Chinese (unless user requests English)
- Target 1500-3000 Chinese characters for research-paper summaries
- Embed all important figures and tables
- Explain each figure/table in 1-2 concise sentences
- Write for senior undergraduate readers in the same technical field
- Always use BOTH text AND images — do not write summary from text alone

## Core Capabilities (What Makes This Skill Different)

This skill provides **intelligent figure/table extraction** beyond simple embedded-image export:

- **Caption detection**: Finds "Figure 1:", "Table 2:", "Figure SIV", "图1" captions and uses them to locate assets
- **Identifier parsing**: Supports roman numerals (I, IV), S-prefix (S1, SIV), Extended Data, Chinese labels (图/表/附图)
- **4-phase clip refinement**: text-trim → object-align → layout-driven → autocrop
- **Acceptance checking**: Validates extraction quality with fallback mechanism
- **Context building**: Links figures/tables to their text references in the paper body

## References

For detailed workflow instructions and advanced options, read the relevant reference:

- `references/pdf-to-markdown.md` — PDF-to-Markdown workflow details
- `references/pdf-summary.md` — Summary workflow details
- `references/cli-options.md` — Complete CLI options reference for all entry points