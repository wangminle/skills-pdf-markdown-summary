# PDF-to-Markdown 重构出发点与实施路径

> **日期**：2026-06-05
> **范围**：在现有 `pdf-summary-agent` 基础上，新增稳定的 PDF → Markdown 产品能力。
> **结论**：不要把现有 `extract_pdf_assets.py` 继续扩成万能脚本，应新增独立的 `pdf_to_markdown` 产品层，并复用已有 PDF 后端、文本提取、图表裁剪与版式分析能力。

---

## 1. 重构出发点

当前项目的核心能力是“从论文 PDF 提取正文与图表资产”，产物是：

- `text/<paper>.txt`
- `text/gathered_text.json`
- `images/*.png`
- `images/index.json`
- `images/figure_contexts.json`
- `images/layout_model.json`

这些产物足够支撑 Agent 生成带图阅读摘要，但它们还不是一个稳定的 PDF → Markdown 转换器。

如果后续目标是“团队资料库上传 PDF 后自动转 Markdown”，现有设计存在几个根本缺口：

1. 缺少 Markdown 文档中间模型，无法稳定表达标题、段落、图片、表格、公式、脚注等结构。
2. 缺少 Markdown 渲染器，现有脚本只输出 `.txt` 和图表 PNG，不负责组织成 `.md`。
3. 表格目前主要以截图形式保存，不能稳定转成 Markdown 表格。
4. 扫描版 PDF 目前只做文本层预验证和 warning，没有 OCR fallback。
5. `extract_figures()` / `extract_tables()` 已经很重，继续加 Markdown 会让主流程更难维护。
6. README、AGENTS、旧入口与新入口的说明存在不一致，产品边界需要先明确。

因此，重构目标不是“替换现有图表提取脚本”，而是新增一个上层转换管线：

```text
PDF
  -> PDF 后端读取
  -> 页面元素解析
  -> 阅读顺序恢复
  -> 文档块模型
  -> 表格/图片/OCR 增强
  -> Markdown 渲染
  -> 转换报告
```

---

## 2. 目标边界

### 2.1 要做什么

新增一个可独立运行的 PDF-to-Markdown 能力：

```bash
python3 scripts/pdf_to_markdown.py \
  --pdf paper.pdf \
  --out paper.md \
  --asset-dir images \
  --mode auto \
  --tables auto \
  --images figures \
  --ocr auto
```

稳定输出：

```text
paper.md
images/
  Figure_1_xxx.png
  Table_1_xxx.png
text/
  markdown_blocks.json
  conversion_report.json
```

### 2.2 不做什么

第一阶段不要追求完全还原 PDF 视觉排版。

明确不作为首期目标：

- 不保证复杂数学公式 100% 转 LaTeX。
- 不保证所有跨页表格自动合并。
- 不保证扫描版 PDF 在无 OCR 依赖时可完整转换。
- 不把 `extract_pdf_assets.py` 改造成 PDF-to-Markdown 主入口。
- 不把所有表格都强行结构化；结构化失败时允许截图 fallback。

---

## 3. 建议目录结构

新增文件与模块建议如下：

```text
scripts/
├── pdf_to_markdown.py              # 新增：兼容导出层 / CLI 入口
├── core/
│   └── pdf_to_markdown.py          # 新增：参数解析与主流程
└── lib/
    ├── markdown_models.py          # 新增：Markdown 文档块数据结构
    ├── markdown_render.py          # 新增：Markdown 渲染器
    ├── reading_order.py            # 新增：阅读顺序恢复
    ├── table_structure.py          # 新增：表格结构提取与 Markdown 化
    ├── image_assets.py             # 新增：图片/图表资产插入策略
    └── ocr.py                      # 新增：OCR fallback 抽象
```

保留现有能力：

- `scripts/extract_pdf_assets.py`：继续负责论文图表/正文资产提取。
- `scripts/lib/pdf_backend.py`：继续作为 PyMuPDF 主路径薄适配层。
- `scripts/lib/extract_figures.py`、`scripts/lib/extract_tables.py`：可被 PDF-to-Markdown 管线复用，但不应承载 Markdown 渲染职责。

---

## 4. 五步实施顺序

### 第一步：整理入口与产品契约

目标：先把“资产提取”和“Markdown 转换”两个产品边界讲清楚。

主要工作：

1. 修正 README 和 AGENTS 中关于 `scripts-old/`、`old-version/scripts-old/`、新入口、legacy engine 的不一致说明。
2. 明确 `extract_pdf_assets.py` 的职责是资产提取，不是 Markdown 转换。
3. 新增 `pdf_to_markdown.py` 的 CLI 设计文档和参数说明。
4. 修复或规避 `python3 scripts/extract_pdf_assets.py --help` 显示帮助时加载重型提取栈的问题。
5. 在 docs 中增加产品边界说明：普通 PDF、扫描版 PDF、结构化表格、图表截图 fallback 的处理策略。

建议验收：

```bash
python3 scripts/extract_pdf_assets.py --help
python3 scripts/pdf_to_markdown.py --help
```

预期：

- 两个命令都能快速返回 help。
- README 中推荐命令真实可运行。
- 用户能明确知道何时用 `extract_pdf_assets.py`，何时用 `pdf_to_markdown.py`。

---

### 第二步：实现最小可用 PDF-to-Markdown

目标：先支持“有文本层的普通 PDF”转 Markdown。

主要工作：

1. 新增 `MarkdownDocument`、`MarkdownPage`、`MarkdownBlock` 等数据结构。
2. 新增段落块、标题块、分页元信息块。
3. 复用 `pdf_backend.open_pdf()` 读取页面文本与坐标。
4. 新增 `reading_order.py`，处理单栏/双栏基础阅读顺序。
5. 新增 `markdown_render.py`，把文档块渲染为 `.md`。
6. 输出 `text/markdown_blocks.json`，便于调试和回归测试。

建议验收：

```bash
python3 scripts/pdf_to_markdown.py \
  --pdf tests-basic-benchmark/1706.03762v7-attention_is_all_you_need/1706.03762v7-attention_is_all_you_need.pdf \
  --out /tmp/attention.md \
  --no-images \
  --tables off \
  --ocr off
```

预期：

- 能生成 `/tmp/attention.md`。
- Markdown 中有标题和正文段落。
- 不要求首期图片和表格完整。
- 同时生成 `markdown_blocks.json` 和 `conversion_report.json`。

---

### 第三步：接入图片与现有图表提取

目标：复用现有 Figure/Table PNG 提取能力，并把图片插入到 Markdown 的合理位置。

主要工作：

1. 调用现有 `extract_figures()` 和 `extract_tables()`，生成 `AttachmentRecord`。
2. 新增 `ImageBlock` 和 `AssetRecord`，统一记录图片路径、页码、caption、ident。
3. 基于 caption 位置或 `figure_contexts.json` 将图片插入 Markdown。
4. 图片路径使用相对路径，如 `images/Figure_1_xxx.png`。
5. 对插入失败的图片，在转换报告中标记 `unplaced_assets`。

建议验收：

```bash
python3 scripts/pdf_to_markdown.py \
  --pdf tests-basic-benchmark/gpt-5-system-card/gpt-5-system-card.pdf \
  --out /tmp/gpt5-system-card.md \
  --images figures \
  --tables screenshot \
  --ocr off
```

预期：

- Markdown 中存在 `![Figure ...](images/...)`。
- 所有引用到的图片文件实际存在。
- `conversion_report.json` 能报告图片数量、已插入数量和未插入数量。

---

### 第四步：表格结构化与截图 fallback

目标：能把结构清晰的表格转成 Markdown 表格，复杂表格保留截图。

主要工作：

1. 在 `table_structure.py` 中封装 `pdfplumber` 表格提取。
2. `pdfplumber` 保持可选依赖，缺失时不影响主转换，只降级为截图。
3. 新增 `TableBlock`，支持两种渲染模式：
   - `markdown_table`
   - `image_fallback`
4. 为结构化失败的表格记录原因：无表格、跨页、单元格为空、列数不一致等。
5. 对复杂论文表格优先保证不丢信息，而不是强行结构化。

建议验收：

```bash
python3 scripts/pdf_to_markdown.py \
  --pdf tests-basic-benchmark/KearnsNevmyvakaHFTRiskBooks/KearnsNevmyvakaHFTRiskBooks.pdf \
  --out /tmp/hft-risk-books.md \
  --tables auto \
  --ocr off
```

预期：

- 简单表格渲染为 Markdown table。
- 复杂表格以图片 fallback 插入。
- 报告中区分 `structured_tables` 和 `fallback_tables`。

---

### 第五步：OCR fallback 与批量回归测试

目标：支持扫描版或低文本层 PDF，并用 benchmark 建立质量基线。

主要工作：

1. 在 `pre_validate_pdf()` 的文本层检测结果基础上触发 OCR。
2. 新增 `ocr.py`，首期可支持 `pytesseract + pdf2image` 或保留接口等待 PaddleOCR/Surya/MinerU 接入。
3. OCR 输出进入同一个 `MarkdownBlock` 模型，不单独走一条文本渲染路径。
4. 新增测试样例：
   - 有文本层单栏 PDF
   - 有文本层双栏论文 PDF
   - 含 Figure/Table 的论文 PDF
   - 表格结构化成功样例
   - 表格 fallback 样例
   - 低文本层或扫描版样例
5. 建立 golden tests，至少检查：
   - Markdown 文件存在
   - 图片链接不失效
   - blocks JSON 可解析
   - conversion report 可解析
   - OCR 依赖缺失时有清晰降级提示

建议验收：

```bash
pytest tests/test_pdf_to_markdown_cli.py -v
pytest tests/test_markdown_render.py -v
pytest tests/test_reading_order.py -v
```

预期：

- 可复制文本 PDF 的核心路径通过。
- 缺少 OCR 依赖时不崩溃。
- 扫描版 PDF 能给出明确报告，安装 OCR 依赖后可生成正文。

---

## 5. 推荐技术路线

### 5.1 主路径

继续使用 PyMuPDF 作为主引擎：

- 文本与坐标提取
- 页面渲染
- 图像和矢量对象检测
- 现有图表裁剪逻辑复用

原因：

- 当前代码已经围绕 PyMuPDF 建模。
- 图像裁剪、矢量对象、页面渲染都依赖 PyMuPDF 能力。
- pdfplumber 不适合作为完整替代后端。

### 5.2 表格增强

使用 pdfplumber 作为可选表格结构化引擎：

- 能结构化时输出 Markdown 表格。
- 不能结构化时回退为截图。
- 不作为默认强依赖，避免影响现有主流程安装成本。

### 5.3 OCR 增强

OCR 做成插件式 fallback：

```text
ocr=off   -> 永不 OCR
ocr=auto  -> 文本层不足时 OCR
ocr=force -> 强制 OCR
```

首期可以先实现接口和降级报告，再接具体 OCR 引擎。

---

## 6. 测试策略

新增测试目录建议：

```text
tests/
├── test_pdf_to_markdown_cli.py
├── test_markdown_models.py
├── test_markdown_render.py
├── test_reading_order.py
├── test_table_structure.py
└── test_conversion_report.py
```

测试原则：

1. 优先测稳定契约，不测每个 PDF 的完整文字内容。
2. golden tests 只固定少量关键片段，避免 PDF 提取细节轻微变化导致大量误报。
3. 图片链接必须真实存在。
4. `conversion_report.json` 必须能解释降级原因。
5. OCR 测试分为“依赖缺失降级”和“依赖存在可用”两类。

---

## 7. 阶段性交付物

### P0 交付物

- 文档入口修正。
- `pdf_to_markdown` CLI 设计说明。
- 现有 `extract_pdf_assets` 职责边界说明。

### P1 交付物

- `scripts/pdf_to_markdown.py`
- `scripts/core/pdf_to_markdown.py`
- `scripts/lib/markdown_models.py`
- `scripts/lib/markdown_render.py`
- `scripts/lib/reading_order.py`
- 基础 CLI 测试。

### P2 交付物

- 图片和图表插入 Markdown。
- 图片链接有效性检查。
- `conversion_report.json` 记录资产插入情况。

### P3 交付物

- pdfplumber 表格结构化。
- 表格截图 fallback。
- 表格相关测试。

### P4 交付物

- OCR fallback 接口。
- 扫描版 PDF 降级报告。
- OCR 可用路径测试。

---

## 8. 风险与取舍

| 风险 | 影响 | 建议 |
|------|------|------|
| PDF 天然缺少语义结构 | 标题、段落、表格层级可能误判 | 通过 blocks JSON 和 report 暴露可调试信息 |
| 表格结构复杂 | Markdown 表格失真 | 优先截图 fallback，避免丢信息 |
| OCR 依赖重 | 安装成本高，跨平台差异大 | 插件式接入，默认 auto 但可降级 |
| 继续堆叠现有巨型函数 | 后续维护困难 | 新增产品层，逐步拆出小模块 |
| 文档与入口不一致 | 用户照文档运行失败 | P0 先修文档和 CLI help |

---

## 9. 最小可行路线

如果只做一个最小闭环，建议按以下顺序：

1. 新增 `scripts/pdf_to_markdown.py --help`，先不做重逻辑。
2. 新增 Markdown block 数据结构。
3. 用 PyMuPDF 提取普通 PDF 文本，输出 `.md`。
4. 输出 `markdown_blocks.json` 和 `conversion_report.json`。
5. 接入现有图表 PNG，插入 Markdown。
6. 表格先截图 fallback，再做 pdfplumber 结构化。
7. OCR 最后做。

这个路线能最快得到可验证产物，同时不破坏现有图表提取流程。
