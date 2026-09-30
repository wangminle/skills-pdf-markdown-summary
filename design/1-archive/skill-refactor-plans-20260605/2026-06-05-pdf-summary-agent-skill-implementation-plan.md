# PDF Summary Agent Skill Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Turn `pdf-summary-agent` into a formal Skill with PDF-to-Markdown, PDF summary, and combined processing entrypoints.

**Architecture:** Add a Skill/product layer above the existing extraction pipeline. Keep old extraction code stable while new CLI entrypoints and Markdown models are introduced behind tests.

**Tech Stack:** Python 3.10+, PyMuPDF, optional pdfplumber, optional OCR, Markdown rendering, Codex Skill directory conventions.

---

## Task 1: Skill Shell

**Files:**
- Create: `SKILL.md`
- Create: `references/pdf-to-markdown.md`
- Create: `references/pdf-summary.md`
- Create: `examples/README.md`

**Steps:**

1. Write `SKILL.md` with trigger descriptions for three workflows.
2. Document PDF-to-Markdown expectations in `references/pdf-to-markdown.md`.
3. Document summary workflow in `references/pdf-summary.md`.
4. Add examples placeholder in `examples/README.md`.
5. Run `python3 -m compileall scripts` to ensure existing Python still imports.

Expected result:

- Skill metadata exists.
- Trigger phrases distinguish conversion, summary, and combined processing.

---

## Task 2: Lightweight CLI Entrypoints

**Files:**
- Create: `scripts/pdf_to_markdown.py`
- Create: `scripts/summarize_pdf.py`
- Create: `scripts/process_pdf.py`
- Create: `scripts/core/pdf_to_markdown.py`
- Create: `scripts/core/summarize_pdf.py`
- Create: `scripts/core/process_pdf.py`

**Steps:**

1. Add thin top-level wrappers.
2. Keep all heavy imports inside `main()`, after argparse handles `--help`.
3. Add `--pdf`, `--out`, `--asset-dir`, `--tables`, `--images`, `--ocr`, and `--report-json`.
4. Verify all help commands return quickly:

```bash
python3 scripts/pdf_to_markdown.py --help
python3 scripts/summarize_pdf.py --help
python3 scripts/process_pdf.py --help
```

Expected result:

- New commands exist.
- `--help` does not import the full extraction stack.

---

## Task 3: Minimal PDF-to-Markdown

**Files:**
- Create: `scripts/lib/markdown_models.py`
- Create: `scripts/lib/markdown_render.py`
- Modify later: `scripts/core/pdf_to_markdown.py`

**Steps:**

1. Add minimal Markdown block dataclasses.
2. Convert `GatheredText.paragraphs` into Markdown blocks.
3. Render headings and paragraphs.
4. Write `<paper>.md`.
5. Write `text/markdown_blocks.json`.
6. Write `text/conversion_report.json`.

Verification:

```bash
python3 scripts/pdf_to_markdown.py \
  --pdf tests-basic-benchmark/1706.03762v7-attention_is_all_you_need/1706.03762v7-attention_is_all_you_need.pdf \
  --out /tmp/attention.md
```

Expected result:

- `/tmp/attention.md` exists.
- Report JSON exists next to the PDF unless overridden.
- Command exits with status 0.

---

## Task 4: Summary Preparation Entrypoint

**Files:**
- Modify later: `scripts/core/summarize_pdf.py`

**Steps:**

1. Delegate to existing `extract_pdf_assets` pipeline.
2. Output clear next-step instructions for Agent summary writing.
3. Do not attempt to generate final prose in Python.
4. Add `--preset robust` default.

Expected result:

- The CLI prepares `text/` and `images/`.
- It reports expected summary filename.

---

## Task 5: Combined Entrypoint

**Files:**
- Modify later: `scripts/core/process_pdf.py`

**Steps:**

1. Run PDF-to-Markdown first.
2. Run summary preparation second.
3. Produce a combined report containing paths to Markdown, text, images, and summary target.

Expected result:

- One command prepares both workflows.

---

## Task 6: Tests

**Files:**
- Create: `tests/test_pdf_to_markdown_cli.py`
- Create: `tests/test_markdown_render.py`
- Create: `tests/test_skill_entrypoints.py`

**Steps:**

1. Test help commands.
2. Test Markdown renderer with synthetic blocks.
3. Test minimal PDF conversion on one benchmark PDF.
4. Test report JSON shape.

Expected result:

```bash
pytest tests/test_pdf_to_markdown_cli.py tests/test_markdown_render.py tests/test_skill_entrypoints.py -v
```

passes.

---

## Task 7: Asset Insertion

**Files:**
- Create: `scripts/lib/image_assets.py`
- Modify later: `scripts/core/pdf_to_markdown.py`

**Steps:**

1. Reuse existing Figure/Table extraction.
2. Convert `AttachmentRecord` to image blocks.
3. Insert image Markdown near captions or at the end of the relevant page.
4. Add broken-link validation.

Expected result:

- Markdown image links point to existing files.

---

## Task 8: Tables and OCR

**Files:**
- Create: `scripts/lib/table_structure.py`
- Create: `scripts/lib/ocr.py`

**Steps:**

1. Add optional pdfplumber table extraction.
2. Render simple tables as Markdown.
3. Fallback complex tables to screenshots.
4. Add OCR mode enum: `off`, `auto`, `force`.
5. Add dependency-missing report behavior.

Expected result:

- Missing optional dependencies degrade gracefully.

---

## Task 9: Cleanup

**Files:**
- Audit: `old-version/`
- Audit: `scripts/extract_pdf_assets.py`
- Audit: `scripts/lib/*`

**Steps:**

1. Run `rg` for imports and CLI references.
2. List dead files in a cleanup doc.
3. Delete only files with no active references and no historical/debug value.
4. Update README and AGENTS.

Expected result:

- Old code is removed only after replacement paths are proven.
