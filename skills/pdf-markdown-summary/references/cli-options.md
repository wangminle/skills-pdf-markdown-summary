# CLI Options Reference

Complete reference for every entry point and its command-line options. Use this when you need to tune extraction, override caption direction, or understand what a flag does. For workflow-level guidance see `pdf-to-markdown.md` and `pdf-summary.md`.

## Entry Points

The skill exposes three high-level entry points and one low-level extraction engine:

| Script | Purpose | Layer |
| --- | --- | --- |
| `scripts/pdf_to_markdown.py` | PDF → structured Markdown (text-first) | High level |
| `scripts/summarize_pdf.py` | PDF → summary assets (plain text + figure PNGs + `index.json`) | High level |
| `scripts/process_pdf.py` | Runs Markdown conversion then reuses those assets for summary | High level (auto-reuses first extraction) |
| `scripts/extract_pdf_assets.py` | Figure/table screenshot extraction engine | Low level (called by `summarize`, also runnable standalone for tuning) |

The high-level shims live in `scripts/` and load their implementation from `scripts/core/` via importlib. `extract_pdf_assets` has the most flags and is the primary tuning surface.

## pdf_to_markdown

| Flag | Type | Default | Purpose |
| --- | --- | --- | --- |
| `--pdf` | str | required | Source PDF path |
| `--out` | str | `<stem>.md` | Output Markdown path |
| `--asset-dir` | str | `images` | Image asset directory (relative to the Markdown output dir) |
| `--report-json` | str | none | Conversion report JSON output path |
| `--blocks-json` | str | none | Markdown blocks JSON output path |
| `--tables` | enum | `off` | Table handling: `off` / `auto` / `screenshot` / `structure` |
| `--images` | enum | `off` | Image mode: `off` / `figures` |
| `--ocr` | enum | `off` | OCR mode: `off` / `auto` / `force` (**roadmap, reserved**) |
| `--preset` | enum | `robust` | Asset extraction preset (only `robust`) |
| `--allow-continued` | flag | off | Allow exporting items that continue across pages |

## summarize_pdf

| Flag | Type | Default | Purpose |
| --- | --- | --- | --- |
| `--pdf` | str | required | Source PDF path |
| `--preset` | enum | `robust` | Parameter preset (only `robust`) |
| `--allow-continued` | flag | off | Allow exporting items that continue across pages |
| `--out-dir` | str | `<pdf-dir>/images` | Image output directory |
| `--text-path` | str | none | Prepared plain-text path (used by reuse mode) |
| `--reuse-existing` | flag | off | Reuse an existing `index.json` + text file instead of extracting again (`process_pdf` sets this automatically) |

## process_pdf

| Flag | Type | Default | Purpose |
| --- | --- | --- | --- |
| `--pdf` | str | required | Source PDF path |
| `--out` | str | `<stem>.md` | Output Markdown path |
| `--asset-dir` | str | `images` | Image asset directory |
| `--preset` | enum | `robust` | Parameter preset |
| `--allow-continued` | flag | off | Allow continued items |
| `--ocr` | enum | `off` | OCR mode (same as above, reserved) |

`process_pdf` computes asset/text paths that match `pdf_to_markdown`, then invokes `summarize_pdf` with `--reuse-existing` so the PDF is parsed only once.

## extract_pdf_assets

Flags are grouped below to match their function in the source. Most flags are already given sane defaults by `--preset robust`; adjust a group only when a specific PDF needs it.

### Input / Output

| Flag | Type | Default | Purpose |
| --- | --- | --- | --- |
| `--pdf` | str | required | PDF path |
| `--preset` | enum | none | Parameter preset (`robust`) |
| `--out-text` | str | none | Plain text output path (`.txt`) |
| `--out-dir` | str | none | PNG output directory |
| `--manifest` | str | none | CSV manifest output path |
| `--index-json` | str | none | `index.json` output path |
| `--prune-images` / `--no-prune-images` | flag | enabled | Remove unindexed `Figure_*/Table_*` PNGs |

### Rendering & Clipping (Figure)

| Flag | Type | Default | Purpose |
| --- | --- | --- | --- |
| `--dpi` | int | 300 | Render DPI |
| `--clip-height` | float | 650.0 | Clip window height (pt) |
| `--margin-x` | float | 20.0 | Horizontal margin (pt) |
| `--caption-gap` | float | 5.0 | Gap between caption and crop (pt) |
| `--max-caption-chars` | int | 160 | Max caption chars used in filename |
| `--max-caption-words` | int | 12 | Max words used in filename |
| `--min-figure` / `--max-figure` | int | 1 / 999 | Figure number range to extract |

### Autocrop

| Flag | Type | Default | Purpose |
| --- | --- | --- | --- |
| `--autocrop` | flag | off | Enable figure autocrop |
| `--autocrop-pad` | int | 30 | Autocrop padding (px) |
| `--autocrop-white-th` (`--autocrop-white-threshold` alias) | int | 250 | White detection threshold |

### Direction Override (Figure)

| Flag | Type | Default | Purpose |
| --- | --- | --- | --- |
| `--below` | str | "" | Figure ids to crop BELOW captions (e.g. `2,3,S1`) |
| `--above` | str | "" | Figure ids to crop ABOVE captions (e.g. `1,4`) |
| `--allow-continued` | flag | off | Allow exporting continued items |

Use `--below`/`--above` to force a direction when automatic detection picks the wrong side. Identifiers support plain numbers, S-prefix (`S1`), and roman numerals.

### Phase A: text-trim

| Flag | Type | Default | Purpose |
| --- | --- | --- | --- |
| `--text-trim` | flag | off | Enable text trim |
| `--text-trim-width-ratio` | float | 0.5 | Text trim width ratio |
| `--text-trim-font-min` | float | 7.0 | Min font size for masking |
| `--text-trim-font-max` | float | 16.0 | Max font size for masking |
| `--text-trim-gap` | float | 6.0 | Gap for text trim (pt) |
| `--adjacent-th` | float | 24.0 | Adjacency threshold (pt) |

### Phase B: objects

| Flag | Type | Default | Purpose |
| --- | --- | --- | --- |
| `--object-pad` | float | 8.0 | Object padding (pt) |
| `--object-min-area-ratio` | float | 0.012 | Min area ratio for an object region |
| `--object-merge-gap` | float | 6.0 | Object merge gap (pt) |

### Phase D: text-mask assisted autocrop

| Flag | Type | Default | Purpose |
| --- | --- | --- | --- |
| `--autocrop-mask-text` | flag | off | Mask text for autocrop |
| `--mask-font-max` | float | 14.0 | Max font size to mask |
| `--mask-width-ratio` | float | 0.5 | Mask width ratio |
| `--mask-top-frac` | float | 0.6 | Near-side (caption side) fraction to mask |

> Phase C (far-side paragraph handling) is internal layout logic and has no exposed flags.

### Safety

| Flag | Type | Default | Purpose |
| --- | --- | --- | --- |
| `--no-refine` | str | "" | Comma-separated figure ids to disable refinements |
| `--refine-near-edge-only` | flag | enabled | Only adjust the near-caption edge, leave the far edge alone |
| `--protect-far-edge-px` | int | 14 | Extra pixels to keep on the far edge |
| `--near-edge-pad-px` | int | 32 | Extra pixels towards the caption side |

### Tables

| Flag | Type | Default | Purpose |
| --- | --- | --- | --- |
| `--include-tables` / `--no-tables` | flag | enabled | Enable table extraction |
| `--table-clip-height` | float | 520.0 | Table clip height (pt) |
| `--table-margin-x` | float | 26.0 | Table horizontal margin (pt) |
| `--table-caption-gap` | float | 6.0 | Table caption gap (pt) |
| `--t-below` / `--t-above` | str | "" | Force table direction override by id |
| `--table-autocrop` / `--no-table-autocrop` | flag | enabled | Table autocrop |
| `--table-autocrop-pad` | int | 20 | Table autocrop padding (px) |
| `--table-adjacent-th` | float | 28.0 | Table adjacency threshold (pt) |
| `--table-object-min-area-ratio` | float | 0.005 | Table object min area ratio |
| `--table-object-merge-gap` | float | 4.0 | Table object merge gap |

### Smart Detection & Layout

| Flag | Type | Default | Purpose |
| --- | --- | --- | --- |
| `--smart-caption-detection` / `--no-smart-caption-detection` | flag | enabled | Smart caption detection (position/format/structure/context scoring) |
| `--debug-captions` | flag | off | Print caption scoring details |
| `--debug-visual` | flag | off | Emit debug overlay images showing clip regions |
| `--adaptive-line-height` / `--no-adaptive-line-height` | flag | enabled | Adaptive line height |
| `--layout-driven` | enum | `on` | Layout-driven mode: `auto` / `on` / `off` (column detection, double-column awareness) |

### Logging

| Flag | Type | Default | Purpose |
| --- | --- | --- | --- |
| `--log-level` | enum | INFO | Log level: `DEBUG` / `INFO` / `WARNING` / `ERROR` |
| `--log-file` | str | none | Log file path |
| `--log-jsonl` | str | none | Structured JSONL log path |

## Common Tuning Scenarios

- **Wrong caption direction (figure cropped on the wrong side):** add the id to `--below` or `--above` (or `--t-below`/`--t-above` for tables).
- **Table truncated mid-way:** raise `--table-clip-height`; if rows stop at a group gap, the band-bridging logic already handles strong rows.
- **Body text leaking into a figure:** raise `--caption-gap`, or enable `--text-trim` / `--autocrop-mask-text`.
- **Double-column PDF:** keep `--layout-driven on` (default); this enables column-aware clipping.
- **Diagnose a bad crop:** add `--debug-captions` (scoring) and `--debug-visual` (overlay images) to inspect what the pipeline decided.

## Roadmap Flags (Reserved)

These flags are accepted but not yet fully wired into the pipeline:

- `--ocr` (all entry points) — OCR fallback for scanned PDFs; currently a no-op aside from detection hints.
- `--tables structure` — structured table parsing; `screenshot` is the supported fallback today.
