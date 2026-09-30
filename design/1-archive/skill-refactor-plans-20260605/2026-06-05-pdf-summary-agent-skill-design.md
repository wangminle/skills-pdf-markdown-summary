# PDF Summary Agent Skill Design

> **For Claude:** This design has been approved by the user. Use it as the north star for the refactor.

**Goal:** Upgrade `pdf-summary-agent` from a project-specific extraction utility into a formal Codex Skill with PDF-to-Markdown, PDF summary, and combined processing workflows.

**Architecture:** Keep the current PDF extraction logic as a reusable lower-level asset pipeline. Add a new Skill/product layer with clear trigger behavior and three lightweight CLI entrypoints: `pdf_to_markdown.py`, `summarize_pdf.py`, and `process_pdf.py`. Migrate old code only after the new entrypoints have tests and stable output contracts.

**Tech Stack:** Python 3.10+, PyMuPDF primary backend, optional pdfplumber for table structure, optional OCR adapters, Markdown block model, Codex Skill `SKILL.md`.

---

## 1. 背景

当前项目已经具备较强的 PDF 论文资产提取能力：

- 提取纯文本与结构化文本。
- 基于 caption 裁剪 Figure 和 Table PNG。
- 生成 `index.json`、`figure_contexts.json`、`layout_model.json`。
- 支撑 Agent 后续生成带图阅读摘要。

但它还不是一个正式 Skill，也不是稳定的 PDF-to-Markdown 工具。现有脚本更像“论文图表资产提取器”，其输出需要 Agent 再人工组织为摘要或 Markdown。

本次重构的目标是把项目升级为正式 Skill，并提供三类可触发能力：

1. 快速将 PDF 转为 Markdown。
2. 为 PDF 生成带图 summary。
3. 一条指令同时完成 PDF-to-Markdown 和 summary。

---

## 2. Skill 产品边界

### 2.1 功能一：PDF-to-Markdown

触发场景：

- “把这个 PDF 转 Markdown”
- “PDF 转 md”
- “提取 PDF 内容做知识库入库”
- “把论文转成 Markdown，图片也导出来”

产物：

```text
<paper>.md
images/
  Figure_1_xxx.png
  Table_1_xxx.png
text/
  markdown_blocks.json
  conversion_report.json
```

首期能力：

- 支持有文本层 PDF。
- 输出基础 Markdown。
- 保留转换报告。
- 图片/表格后续逐步接入现有资产提取能力。

### 2.2 功能二：PDF Summary

触发场景：

- “总结这篇 PDF”
- “生成论文阅读摘要”
- “带图总结这篇论文”
- “把论文图表解释一下”

产物：

```text
<paper>_阅读摘要-YYYYMMDD.md
images/
text/
```

说明：

- 复用现有图表提取、重命名、摘要生成业务逻辑。
- Summary 是 Agent-mediated workflow，不应硬塞成纯 Python 脚本独立生成最终语言内容。
- Python 脚本负责准备文本、图片、索引、上下文和报告；Agent 负责阅读、重命名、撰写摘要。

### 2.3 功能三：Combined Processing

触发场景：

- “处理这篇论文，转 Markdown 并生成摘要”
- “做资料库入库并总结”
- “完整跑一遍 PDF 处理流程”

产物：

```text
<paper>.md
<paper>_阅读摘要-YYYYMMDD.md
images/
text/
```

说明：

- 先跑 PDF-to-Markdown。
- 再跑 summary 准备流程。
- Agent 在最后生成摘要 Markdown。

---

## 3. 方案选择

采用方案 A：增量产品层重构。

### 为什么不大重写

当前项目已经积累了 caption 检测、图表裁剪、版式分析和调试输出。直接换成 `pymupdf4llm` 或纯 `pdfplumber` 会丢掉这些业务价值。

### 为什么不只包装旧脚本

只写一个 `SKILL.md` 包住旧脚本，能快速“看起来像 Skill”，但内部仍然没有 Markdown 文档模型、转换报告、触发分流和测试契约。

### 推荐路径

保留现有 `extract_pdf_assets.py`，新增正式 Skill 层：

```text
pdf-summary-agent/
├── SKILL.md
├── scripts/
│   ├── pdf_to_markdown.py
│   ├── summarize_pdf.py
│   ├── process_pdf.py
│   └── core/
│       ├── pdf_to_markdown.py
│       ├── summarize_pdf.py
│       └── process_pdf.py
├── references/
├── examples/
└── evals/
```

---

## 4. 数据流

### 4.1 PDF-to-Markdown

```text
PDF
  -> PDF validation
  -> text extraction
  -> reading order
  -> Markdown block model
  -> image/table asset extraction
  -> Markdown render
  -> conversion_report.json
```

### 4.2 PDF Summary

```text
PDF
  -> extract_pdf_assets
  -> text/<paper>.txt
  -> images/*.png
  -> images/index.json
  -> image rename workflow
  -> Agent writes summary Markdown
```

### 4.3 Combined

```text
PDF
  -> PDF-to-Markdown pipeline
  -> Summary preparation pipeline
  -> Agent summary writing
```

---

## 5. 旧代码清理原则

不要立即删除旧代码。

清理顺序：

1. 新入口落地。
2. 新入口测试通过。
3. 梳理旧代码引用关系。
4. 迁移仍有价值的函数到 `scripts/lib/`。
5. 标记旧入口 deprecated。
6. 删除确认无引用、无测试价值、无文档价值的旧文件。

保留原则：

- `old-version/` 可先作为历史参考保留。
- 当前仍有业务价值的图表裁剪逻辑必须迁移或复用。
- 删除前必须有等价测试或明确替代路径。

---

## 6. 第一批落地范围

第一批只做低风险结构化改造：

1. 新增根目录 `SKILL.md`。
2. 新增三条 CLI 入口。
3. 新增 PDF-to-Markdown 最小文本层输出。
4. 新增设计文档和实施计划。
5. 不改动已有复杂提取算法。
6. 不删除旧代码。

---

## 7. 验收标准

第一批重构完成后，以下命令应可运行：

```bash
python3 scripts/pdf_to_markdown.py --help
python3 scripts/summarize_pdf.py --help
python3 scripts/process_pdf.py --help
```

并且普通文本层 PDF 应能生成基础 Markdown：

```bash
python3 scripts/pdf_to_markdown.py \
  --pdf tests-basic-benchmark/1706.03762v7-attention_is_all_you_need/1706.03762v7-attention_is_all_you_need.pdf \
  --out /tmp/attention.md
```

---

## 8. 后续实施路线

1. P0：Skill 外壳和入口拆分。
2. P1：Markdown 文档模型和渲染器。
3. P2：图片和 Figure/Table 插入。
4. P3：pdfplumber 表格结构化和截图 fallback。
5. P4：OCR fallback。
6. P5：旧代码清理和 benchmark。
