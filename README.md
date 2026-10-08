# PDF Markdown Summary Skill

> 一个用于 PDF 转 Markdown、图表导出和论文带图摘要生成的 Codex Skill。
> A Codex Skill for PDF-to-Markdown conversion, figure/table asset extraction, and figure-aware PDF summaries.
>
> 当前版本 / Current version: **0.6.9**

---

## 中文说明

### 项目定位

本项目已升级为正式 Skill，核心目录是：

```text
skills/pdf-markdown-summary/
```

这个 Skill 面向论文、报告、技术文档等 PDF 文件，提供三类能力：

1. **PDF 转 Markdown**：提取 PDF 文本，生成 `.md`，并可导出图表资源。
2. **PDF 带图摘要**：提取正文与 Figure/Table 图片，辅助生成中文或英文阅读摘要。
3. **完整处理流程**：一条命令同时完成 Markdown 转换和摘要素材准备。

历史根目录 `scripts/` 已迁移到正式 Skill 包，并保留快照于 `old-version/scripts-archive-20260605/`。当前对外能力以 `skills/pdf-markdown-summary/scripts/` 为准。

### Skill 目录结构

```text
skills/pdf-markdown-summary/
├── SKILL.md                    # Skill 触发说明与工作流入口
├── agents/
│   └── openai.yaml             # OpenAI/Codex Agent 配置
├── references/
│   ├── pdf-to-markdown.md      # PDF 转 Markdown 说明
│   ├── pdf-summary.md          # PDF 摘要说明
│   └── cli-options.md          # 全部入口 CLI 参数参考
└── scripts/
    ├── pdf_to_markdown.py      # PDF -> Markdown
    ├── summarize_pdf.py        # 摘要素材准备
    ├── process_pdf.py          # 转换 + 摘要准备
    ├── extract_pdf_assets.py   # 图表/正文资产提取兼容入口
    ├── core/                   # CLI 主流程
    └── lib/                    # PDF 后端、版式、裁剪、渲染等模块
```

### 主要效果

PDF 转 Markdown 后会生成：

```text
<paper>.md
text/markdown_blocks.json
text/conversion_report.json
images/*.png                 # 启用图表导出时生成
```

PDF 摘要准备后会生成：

```text
text/<paper>.txt
text/gathered_text.json
images/*.png
images/index.json
images/figure_contexts.json
images/layout_model.json
```

Agent 可基于这些文件继续生成：

```text
<paper>_阅读摘要-YYYYMMDD.md
```

### 安装

建议使用 Python 3.10+，推荐 Python 3.12+。

安装核心依赖：

```bash
python3 -m pip install --user -r "skills/pdf-markdown-summary/scripts/requirements.txt"
```

最低核心依赖是：

```bash
python3 -m pip install --user pymupdf
```

可选增强：

```bash
python3 -m pip install --user pdfplumber
```

后续 OCR 能力会通过可选依赖接入。

### 使用方法

> 各入口的全部命令行参数（含图表裁剪、表格、版式驱动等调参选项）见 `skills/pdf-markdown-summary/references/cli-options.md`。

#### 1. PDF 转 Markdown

```bash
python3 "skills/pdf-markdown-summary/scripts/pdf_to_markdown.py" \
  --pdf "paper.pdf" \
  --out "paper.md"
```

带图表资产导出：

```bash
python3 "skills/pdf-markdown-summary/scripts/pdf_to_markdown.py" \
  --pdf "paper.pdf" \
  --out "paper.md" \
  --images figures \
  --tables screenshot
```

#### 2. 准备 PDF 带图摘要素材

```bash
python3 "skills/pdf-markdown-summary/scripts/summarize_pdf.py" \
  --pdf "paper.pdf" \
  --preset robust
```

运行后读取：

- `text/<paper>.txt`
- `images/*.png`
- `images/index.json`

然后由 Agent 撰写带图摘要。

#### 3. 完整处理：转 Markdown + 准备摘要

```bash
python3 "skills/pdf-markdown-summary/scripts/process_pdf.py" \
  --pdf "paper.pdf" \
  --out "paper.md" \
  --preset robust
```

### Skill 触发词

当用户说以下内容时，应使用这个 Skill：

- “PDF 转 Markdown”
- “把 PDF 转成 md”
- “提取 PDF 内容做知识库”
- “总结这篇 PDF”
- “生成论文阅读摘要”
- “带图摘要”
- “处理这篇论文，转 Markdown 并总结”

### 当前状态

已完成：

- 正式 Skill 包结构。
- PDF-to-Markdown 可用流程。
- 摘要素材准备入口。
- 完整处理入口。
- Markdown block JSON 与 conversion report 输出。
- 智能 caption 检测（位置/格式/结构/上下文评分）与 Figure/Table 分流精裁。
- 图表截图支持 baseline 限制、文本裁切、对象对齐、列感知 X 收窄、版式驱动、autocrop、autocrop 否决时的横向收窄（原生对象面积支撑 + 原框文字保全双重守卫）、final 安全补边和 debug visual。
- Table 专用多行表头回收、渲染横线补偿、强结构表格行带识别、宽度恢复、末行/换行尾行保护、远端章节标题裁除、底线外显式尾注恢复（含上角标数字脚注 ¹-N 及其顺序性校验）与外框线并入。
- 双栏版式感知与伪双栏几何防护。
- 完整流程复用首次提取产物，避免重复解析 PDF。
- 可选 PyMuPDF4LLM Layout 后端，支持语义区域证据、全页一对一配对、多框合并与保守边界精修。
- 资产记录包含 `final_bbox`、候选证据、配对/边界置信度、warnings、review_required 和四态质量结果。
- 四态质量评估（`lib/assess.py`）：截断与完整性质疑基于可见墨迹探测而非矢量路径外框，`review_required` / `rejected` 资产不进入 Markdown。
- 跨页无题注续表自动恢复：续页标记、重复表头与横线三重证据一致时回收相邻页表格片段，未通过边界检查的片段标记待复核。
- 题注对账（caption inventory）：显式题注与裸 `Figure N` / `Table N` 标签自动对账导出资产，缺口补裁后写入索引。
- Markdown 图表就近插入：accepted 截图插到对应题注段落旁（内容在题注上方则图在题注前，否则在后），无匹配题注的资产追加到文末「提取资产」节。
- 插图后框内文字抑制：截图插入 Markdown 时，完整落入资产框内的表体/图内散行文字自动抑制（显式题注行与框外正文保留），逐资产嵌入状态（`referenced_in_markdown` / `embed_mode` / `suppressed_text_blocks`）回写 `images/index.json`。
- Markdown 图片序列化：图片目的地址按需 URL 编码、题注替代文本转义反斜杠与方括号，含空格目录与半开区间题注仍形成有效图片语法，文件名保持原值。
- 题注多行合并增强：跨紧邻同栏文本块的续行合并（未完信号 + 几何/字号守卫，不吞正文）、动词句式多行真题注完整合并、行末断词连字符合并（全文未跨行词形证据优先，避免 Pro-gramBench 式真实复合词误并）。
- 独立公式区域整块保留：OCR/排版拆散的公式碎片按保守信号识别、按栏分组，并在同栏内补全竖向分母、求和限、高括号和公式编号；不跨栏、不越过图表区域、不吞中间正文。含等号的短句（如 `We set a=1.`）不是公式。图片开启时对完整区域按原页截图，图片关闭时合并为单个 text 围栏代码块；无法补全的悬挂碎片保留原文并记入 `equations.needs_review`。宁可漏检不误检正文。
- 多行标题归一：编号与标题文本被排版拆行时序列化为单行 ATX 标题，后半段不再掉入正文（段落换行策略保持不变）。
- `--prune-images` 安全化：仅清理运行前已存在且未被修改、未被当前索引引用的 PNG。
- 全部入口 CLI 参数参考文档（`references/cli-options.md`）。
- Basic Benchmark 八份 PDF 已纳入 Golden 变更检测；输入集于 2026-09 更新（Kimi K3、DeepSeek V4.1 替换旧版 K3/V4 报告，仍为 8 份）。Golden 基准存放于独立批次，与被比产物分批，杜绝同批自比假绿；当前回归基线为 653 passed、0 failed、0 skipped（2026-10-08 复验）。
- Basic Benchmark 已完成多轮逐图 debug 排查，图表选取策略记录见 `design/1-archive/Basic-Benchmark图表细致排查记录-20260618-0621.md`。
- 当前图表提取代码流程说明见 `design/1-archive/PDF图表提取流程逻辑说明-20260621.md`。
- 旧版 scripts 快照归档。

继续改进方向：

- pdfplumber 表格结构化输出。
- OCR fallback（当前 CLI 保留 `--ocr` 参数，但生产流程仍依赖 PDF 文本层）。
- 完成独立 holdout PDF 与人工 GT 标注，执行 A4 正式 KPI 评估。
- 清理确认无引用的旧代码。

### 开发与归档

当前正式脚本源码位于 Skill 包内：

```text
skills/pdf-markdown-summary/scripts/
```

正式 Skill 包以此目录为准：

```text
skills/pdf-markdown-summary/
```

历史归档：

```text
old-version/scripts-archive-20260605/
old-version/scripts-old/
```

---

## English

### What This Project Is

This repository provides a formal Codex Skill for PDF processing. The active Skill package is:

```text
skills/pdf-markdown-summary/
```

It supports three workflows:

1. **PDF to Markdown**: extract PDF text, generate Markdown, and optionally export figure/table assets.
2. **PDF Summary**: prepare text and image assets for figure-aware paper summaries.
3. **Complete Processing**: run Markdown conversion and summary preparation in one command.

### Directory Layout

```text
skills/pdf-markdown-summary/
├── SKILL.md
├── agents/
├── references/
└── scripts/
    ├── pdf_to_markdown.py
    ├── summarize_pdf.py
    ├── process_pdf.py
    ├── extract_pdf_assets.py
    ├── core/
    └── lib/
```

### Installation

Use Python 3.10+; Python 3.12+ is recommended.

```bash
python3 -m pip install --user -r "skills/pdf-markdown-summary/scripts/requirements.txt"
```

Minimal dependency:

```bash
python3 -m pip install --user pymupdf
```

Optional table enhancement:

```bash
python3 -m pip install --user pdfplumber
```

### Usage

> For the full list of command-line flags across all entry points (figure clipping, tables, layout-driven tuning, optional `--layout-backend`), see `skills/pdf-markdown-summary/references/cli-options.md`.

#### PDF to Markdown

```bash
python3 "skills/pdf-markdown-summary/scripts/pdf_to_markdown.py" \
  --pdf "paper.pdf" \
  --out "paper.md"
```

With asset extraction:

```bash
python3 "skills/pdf-markdown-summary/scripts/pdf_to_markdown.py" \
  --pdf "paper.pdf" \
  --out "paper.md" \
  --images figures \
  --tables screenshot
```

#### Prepare Summary Assets

```bash
python3 "skills/pdf-markdown-summary/scripts/summarize_pdf.py" \
  --pdf "paper.pdf" \
  --preset robust
```

The Agent should then read:

- `text/<paper>.txt`
- `images/*.png`
- `images/index.json`

and write the final figure-aware summary.

#### Complete Processing

```bash
python3 "skills/pdf-markdown-summary/scripts/process_pdf.py" \
  --pdf "paper.pdf" \
  --out "paper.md" \
  --preset robust
```

### Outputs

Markdown conversion outputs:

```text
<paper>.md
text/markdown_blocks.json
text/conversion_report.json
images/*.png
```

Summary preparation outputs:

```text
text/<paper>.txt
text/gathered_text.json
images/*.png
images/index.json
images/figure_contexts.json
images/layout_model.json
```

### Status

Implemented:

- Formal Skill package.
- Working PDF-to-Markdown pipeline.
- Summary preparation CLI.
- Combined processing CLI.
- Markdown block JSON and conversion report.
- Smart caption detection (position/format/structure/context scoring) and separate Figure/Table crop refinement.
- Figure/Table screenshots support baseline limiting, text trimming, object alignment, column-aware X clipping, layout-driven trimming, autocrop, autocrop-vetoed X narrowing (guarded by both native-object coverage and in-frame text preservation), final padding, and debug overlays.
- Table-specific multiline header recovery, rendered-rule compensation, strong table-band detection, width restoration, tail-row protection, wrapped-tail preservation, far-side section-heading trimming, explicit table-note recovery below the bottom rule (including superscript digit notes ¹-N with sequential-marker checks), and border-rule inclusion.
- Double-column layout awareness and false-double-column geometry guards.
- Full pipeline reuses the first extraction to avoid re-parsing the PDF.
- Optional PyMuPDF4LLM Layout backend for semantic-region evidence, full-page one-to-one pairing, multi-frame grouping, and conservative boundary refinement.
- Asset records include final bounding boxes, source signals, pairing/boundary confidence, warnings, review flags, and four-state quality outcomes.
- Four-state quality assessment (`lib/assess.py`): truncation and completeness signals use visible-ink probes instead of raw vector path bounds; `review_required` / `rejected` assets stay out of Markdown.
- Captionless cross-page table continuation recovery when continuation markers, repeated headers, and horizontal rules agree; fragments failing boundary checks are flagged for review.
- Caption inventory reconciliation: explicit captions and bare `Figure N` / `Table N` labels are reconciled against exported assets; gaps get recovery crops and are indexed.
- In-place asset placement: accepted Figure/Table screenshots are inserted next to their matching caption paragraph (before it when the crop sits above the caption, otherwise after); unmatched assets go to a trailing asset section.
- In-frame text suppression after placement: body/table text lines fully covered by an inserted screenshot's bbox are suppressed from the Markdown (explicit captions and out-of-frame text are kept); per-asset embed status (`referenced_in_markdown` / `embed_mode` / `suppressed_text_blocks`) is written back to `images/index.json`.
- Markdown image serialization: image destinations are URL-encoded on demand and caption alt text escapes backslashes and brackets, so directories with spaces and half-open-interval captions still form valid image syntax; file names stay untouched.
- Multi-line caption merging enhancements: continuation lines across adjacent same-column text blocks (unfinished-signal plus geometry/font-size guards that refuse to swallow body text), verb-opened multi-line captions merged whole, and hyphenated line-break rejoining driven by whole-document word-form evidence (avoiding false joins such as "Pro-gramBench").
- Display-equation region preservation: OCR-scattered formula fragments are identified by conservative signals and grouped per column. The same column then picks up vertical denominators, summation limits, tall brackets, and equation numbers; absorption does not cross columns, asset regions, or prose sitting between formulas. A short sentence such as `We set a=1.` is not an equation. With images on, a complete region is screenshotted from the original page; with images off it becomes one fenced ```text block. A dangling fragment that cannot be completed stays as source text and is counted in `equations.needs_review`. Misses are preferred over false positives on body text.
- Multi-line heading normalization: headings whose numbering and text were split across lines serialize as a single-line ATX heading (the tail no longer leaks into body text); paragraph line-breaking is unchanged.
- Safe `--prune-images`: only PNGs that existed before the run, are unchanged, and are unreferenced by the current index are removed.
- Complete CLI options reference (`references/cli-options.md`).
- Eight Basic Benchmark PDFs are covered by local Golden change detection; the set was refreshed in September 2026 (Kimi K3 and DeepSeek V4.1 replace the older K3/V4 reports, still 8 PDFs). Golden baselines live in a dedicated batch, separated from the artifacts they are compared against to rule out same-batch self-comparison; the current regression baseline is 653 passed, 0 failed, 0 skipped (reverified on 2026-10-08).
- Multi-round Basic Benchmark visual review is recorded in `design/1-archive/Basic-Benchmark图表细致排查记录-20260618-0621.md`.
- Current extraction flow diagrams are documented in `design/1-archive/PDF图表提取流程逻辑说明-20260621.md`.
- Archived previous root-level scripts snapshot.

Planned:

- Structured table extraction.
- OCR fallback (`--ocr` is reserved; production extraction currently relies on the PDF text layer).
- An independently annotated holdout set and the formal A4 KPI evaluation.
- Safe cleanup of unused legacy code.

### License

Apache-2.0 License. See [LICENSE](LICENSE).
