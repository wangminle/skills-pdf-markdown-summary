# PDF-to-Markdown Workflow

Use this workflow when the user asks to convert a PDF into Markdown or prepare a PDF for knowledge-base ingestion.

For the full list of command-line flags, see `cli-options.md`.

## Preferred Flow

1. Run `scripts/pdf_to_markdown.py`.
2. Check the generated Markdown.
3. Check `conversion_report.json`.
4. Verify image links if images were exported.

## Command

```bash
python3 scripts/pdf_to_markdown.py \
  --pdf "<paper>.pdf" \
  --out "<paper>.md" \
  --asset-dir images \
  --tables auto \
  --images figures \
  --ocr auto
```

## Expected Outputs

```text
<paper>.md
images/
text/
  markdown_blocks.json
  conversion_report.json
```

## Conversion Policy

- Use PyMuPDF as the primary PDF backend.
- Use pdfplumber only as an optional table-structure enhancement.
- Use OCR only when requested or when text-layer detection is insufficient.
- Do not drop tables if structure extraction fails; use image fallback.
- Keep Markdown paths relative to the Markdown file location.

## Quality Checks

Check:

- Markdown file exists and is non-empty.
- `markdown_blocks.json` is valid JSON.
- `conversion_report.json` is valid JSON.
- Every `images/...` link points to an existing file.
