# PDF-to-Markdown Workflow

Use this workflow when the user asks to convert a PDF into Markdown or prepare a PDF for knowledge-base ingestion.

For the full list of command-line flags, see `cli-options.md`.

## Preferred Flow

1. Run `scripts/pdf_to_markdown.py`.
2. Check the generated Markdown.
3. Check `conversion_report.json`.
4. Verify image links if images were exported.
5. Treat a non-zero `assets.exit_code` and top-level `status: failed` as a failed/partial conversion; top-level `status: review` means the conversion completed but some review/rejected assets were omitted from the Markdown (see `assets.omitted`).

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
- Insert accepted Figure/Table screenshots next to the matching caption paragraph. If the crop sits above the caption, place the image immediately before that paragraph; otherwise place it immediately after. Assets without a matching caption still go to a trailing `## 提取资产` section.
- When a screenshot is inserted, body text lines fully covered by the asset bbox are suppressed from the Markdown; explicit captions and out-of-frame text are kept. Each asset's embed status (`referenced_in_markdown` / `embed_mode` / `suppressed_text_blocks`) is written back to `images/index.json`.
- Image destinations are URL-encoded on demand and caption alt text escapes backslashes and brackets, so directories with spaces and half-open-interval captions (e.g. `(0, 1]`) still form valid image syntax; file names stay untouched.
- Use `--debug-visual` through `scripts/extract_pdf_assets.py` when figure/table crop quality needs diagnosis.

## Quality Checks

Check:

- Markdown file exists and is non-empty.
- `markdown_blocks.json` is valid JSON.
- `conversion_report.json` is valid JSON.
- `assets.exit_code` is `0` when asset extraction was enabled and completed successfully; it is `null` when assets were disabled. A non-zero value must be paired with top-level `status: failed`. With a zero exit code, top-level `status` is `review` when `assets.omitted` is non-empty (review/rejected assets kept out of the Markdown) and `ready` otherwise.
- Every `images/...` link points to an existing file.
- Every exported asset's embed status in `images/index.json` matches the Markdown: inserted assets report `referenced_in_markdown: true` with an `embed_mode`, and the console prints the extracted/embedded/omitted summary.
