# PDF Markdown Summary Skill

> 一个用于 PDF 转 Markdown、图表导出和论文带图摘要生成的 Codex Skill。
> A Codex Skill for PDF-to-Markdown conversion, figure/table asset extraction, and figure-aware PDF summaries.

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
- 图表截图支持 baseline 限制、文本裁切、对象对齐、列感知 X 收窄、版式驱动、autocrop、final 安全补边和 debug visual。
- Table 专用多行表头回收、渲染横线补偿、强结构表格行带识别、宽度恢复、末行/换行尾行保护和远端章节标题裁除。
- 双栏版式感知与伪双栏几何防护。
- 完整流程复用首次提取产物，避免重复解析 PDF。
- 全部入口 CLI 参数参考文档（`references/cli-options.md`）。
- Basic Benchmark 八份 PDF 已完成多轮逐图 debug 排查，图表选取策略记录见 `docs/1-archive/Basic-Benchmark图表细致排查记录-20260618-0621.md`。
- 当前图表提取代码流程说明见 `docs/1-archive/PDF图表提取流程逻辑说明-20260621.md`。
- 旧版 scripts 快照归档。

继续改进方向：

- 图片按 caption 位置插入 Markdown。
- pdfplumber 表格结构化输出。
- OCR fallback（当前 CLI 保留 `--ocr` 参数，但生产流程仍依赖 PDF 文本层）。
- 更完整的测试集与 benchmark。
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
- Figure/Table screenshots support baseline limiting, text trimming, object alignment, column-aware X clipping, layout-driven trimming, autocrop, final padding, and debug overlays.
- Table-specific multiline header recovery, rendered-rule compensation, strong table-band detection, width restoration, tail-row protection, wrapped-tail preservation, and far-side section-heading trimming.
- Double-column layout awareness and false-double-column geometry guards.
- Full pipeline reuses the first extraction to avoid re-parsing the PDF.
- Complete CLI options reference (`references/cli-options.md`).
- Multi-round Basic Benchmark visual review is recorded in `docs/1-archive/Basic-Benchmark图表细致排查记录-20260618-0621.md`.
- Current extraction flow diagrams are documented in `docs/1-archive/PDF图表提取流程逻辑说明-20260621.md`.
- Archived previous root-level scripts snapshot.

Planned:

- Better asset placement in Markdown.
- Structured table extraction.
- OCR fallback (`--ocr` is reserved; production extraction currently relies on the PDF text layer).
- Broader tests and benchmarks.
- Safe cleanup of unused legacy code.

### License

Apache-2.0 License. See [LICENSE](LICENSE).
