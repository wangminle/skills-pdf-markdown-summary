# PDF-to-Markdown Workflow

Use this workflow when the user asks to convert a PDF into Markdown or prepare a PDF for knowledge-base ingestion.

For the full list of command-line flags, see `cli-options.md`.

## Preferred Flow

1. Run `scripts/pdf_to_markdown.py`.
2. Check the generated Markdown.
3. Check `conversion_report.json`.
4. Verify image links if images were exported.
5. Treat a non-zero `assets.exit_code` and top-level `status: failed` as a failed/partial conversion.

## Command

```bash
python3 scripts/pdf_to_markdown.py \
  --pdf "<paper>.pdf" \
  --out "<paper>.md" \
  --asset-dir images \
  --tables auto \
  --images figures
```

## Expected Outputs

```text
<paper>.md
images/
  *.png                # Figure/Table screenshots
  index.json           # asset index
  layout_model.json    # layout text/format model
  figure_contexts.json # per-figure context metadata
  run.log.jsonl        # structured run log
  debug/<run_id>/      # debug overlays (only with --debug-visual)
text/
  <stem>.txt           # gathered plain text
  gathered_text.json   # structured gathered text
  markdown_blocks.json
  conversion_report.json
```

## Conversion Policy

- Use PyMuPDF as the primary PDF backend.
- Use pdfplumber only as an optional table-structure enhancement.
- `--tables auto`, `screenshot`, and `structure` currently all export table screenshots; structured table parsing is not implemented yet.
- Treat OCR flags as reserved roadmap options; current production extraction relies on the PDF text layer.
- Do not drop tables if structure extraction fails; use image fallback.
- Keep Markdown paths relative to the Markdown file location.
- Use `--debug-visual` through `scripts/extract_pdf_assets.py` when figure/table crop quality needs diagnosis.

## Quality Checks

Check:

- Markdown file exists and is non-empty.
- `markdown_blocks.json` is valid JSON.
- `conversion_report.json` is valid JSON.
- `assets.exit_code` is `0` when asset extraction was enabled and completed successfully; it is `null` when assets were disabled. A non-zero value must be paired with top-level `status: failed`.
- Every `images/...` link points to an existing file.
