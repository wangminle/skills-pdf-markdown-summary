---
name: pdf-markdown-summary
description: Use this skill whenever the user wants to convert PDFs to Markdown, extract PDF figures/tables/images, generate a PDF or research-paper summary, create a Chinese or English reading summary with embedded figures, or run a complete PDF processing workflow for knowledge-base ingestion. Trigger for phrases like "PDF 转 Markdown", "转 md", "提取 PDF 内容", "总结这篇 PDF", "论文阅读摘要", "带图摘要", "资料库入库", or "处理这篇论文".
---

# PDF Markdown Summary

This skill turns PDF documents, especially research papers, into reusable Markdown and summary artifacts.

It supports three workflows:

1. **PDF-to-Markdown**: Convert a PDF into Markdown and export related assets.
2. **PDF Summary**: Extract text and figures, then generate a reading summary with embedded figures.
3. **Complete Processing**: Run conversion and summary preparation together.

## Choose the Workflow

Use **PDF-to-Markdown** when the user asks to:

- convert a PDF to Markdown or `.md`
- prepare a PDF for a knowledge base
- extract text, tables, and images into a Markdown document

Use **PDF Summary** when the user asks to:

- summarize a PDF
- summarize a research paper
- create a reading note or reading summary
- explain figures and tables
- generate a Chinese or English paper summary

Use **Complete Processing** when the user asks to:

- process a PDF end to end
- convert to Markdown and summarize
- ingest into a knowledge base and produce a summary

## Commands

### PDF-to-Markdown

```bash
python3 scripts/pdf_to_markdown.py --pdf "<paper>.pdf" --out "<paper>.md"
```

### PDF Summary Preparation

```bash
python3 scripts/summarize_pdf.py --pdf "<paper>.pdf" --preset robust
```

After the preparation command, read both:

- `text/<paper>.txt`
- `images/*.png`

Then write the summary Markdown with embedded relative image links.

### Complete Processing

```bash
python3 scripts/process_pdf.py --pdf "<paper>.pdf" --out "<paper>.md" --preset robust
```

## Output Rules

For Markdown conversion:

- Use relative image paths such as `images/Figure_1_xxx.png`.
- Write a conversion report when possible.
- Preserve enough structure for knowledge-base ingestion.
- If table structure extraction fails, prefer a table screenshot fallback rather than dropping information.

For summaries:

- Default language is Chinese unless the user requests otherwise.
- Target 1500-3000 Chinese characters for research-paper reading summaries unless the user gives a different length.
- Embed all relevant figures and tables.
- Explain each figure or table in 1-2 concise sentences.
- Write for senior undergraduate readers in the same technical field.

## References

Read only the relevant reference:

- `references/pdf-to-markdown.md` for PDF-to-Markdown workflows.
- `references/pdf-summary.md` for summary workflows.
