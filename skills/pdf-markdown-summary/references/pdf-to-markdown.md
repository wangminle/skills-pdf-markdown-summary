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
- Display-equation regions are preserved as a whole instead of OCR fragments: fragments are detected conservatively (strong math signals, column geometry). Short prose that merely contains an equals sign (`We set a=1.`) is not an equation. Groups stay inside one column and stop at intervening prose. After a seed hit, the region grows to vertical pieces on that column — denominators, summation limits, tall brackets, equation numbers, and adjacent OCR blocks that still contain the formula — without crossing into another column or an extracted asset box. Neighbors are judged against each member line, not the union of a multi-line box. With `--images figures` a complete region is screenshotted from the original page; with images off (or if the render fails) the fragments merge into one text fenced block. If the boundary cannot be completed, the original paragraphs stay and `equations.needs_review` counts them; the conversion report status becomes `review`. Detection prefers misses over false positives. Counts appear in `conversion_report.json` under `equations`.
- Use `--debug-visual` through `scripts/extract_pdf_assets.py` when figure/table crop quality needs diagnosis.
- Reading order is decided per page. Confirmed double-column pages teach left/right column origins, and sparse pages inherit them when they offer too little evidence on their own. A page with full-width body text beside a two-column grid whose gutter is much wider than the column gap is treated as side-by-side table content and read row by row, so labels and readings stay together.
- Repeated headers and footers are removed only inside the margin band; a same-text heading in the body survives. Bottom numbers become page-number candidates only when isolated from body text and consistent with a fixed printed-page offset or a mirrored neighboring side; numbers sharing a row with table labels are kept.
- Headings, tables, and list items escape literal asterisks, backslashes, and HTML-like angle brackets exactly once. Inline styles are produced and validated during extraction rather than reconstructed during rendering, so bold `x**2`, consecutive backslashes, and escaped bullet characters round-trip as the original text.
- Crossing a column or page resets the list-indent stack. Cross-page ordered lists omit the page marker only when continuation was confirmed during extraction, and they bridge only genuine page-number sequences. Bullets escaped to literal asterisks still render as CommonMark lists.
- `--layout-model-detail summary|blocks|full` controls `layout_model.json`; when it is omitted, asset extraction runs at `blocks`. With both figures and tables off, an explicit level exports the layout model alone, leaving `index.json` and existing PNGs untouched. Layout and derived asset paths are identity-checked before writing and cannot overwrite the source PDF or another output.

## Quality Checks

Check:

- Markdown file exists and is non-empty.
- `markdown_blocks.json` is valid JSON.
- `conversion_report.json` is valid JSON.
- `assets.exit_code` is `0` when asset extraction was enabled and completed successfully; it is `null` when assets were disabled. A non-zero value must be paired with top-level `status: failed`. With a zero exit code, top-level `status` is `review` when `assets.omitted` is non-empty (review/rejected assets kept out of the Markdown) and `ready` otherwise.
- Every `images/...` link points to an existing file.
- Every exported asset's embed status in `images/index.json` matches the Markdown: inserted assets report `referenced_in_markdown: true` with an `embed_mode`, and the console prints the extracted/embedded/omitted summary.
