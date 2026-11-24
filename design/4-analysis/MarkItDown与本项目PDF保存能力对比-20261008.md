# MarkItDown 与本项目 PDF 保存能力对比

核查日期：2026-10-08。本文将「保存 PDF」理解为将 PDF 内容保存成 Markdown、图片及可追溯资源，比较对象为 MarkItDown v0.1.8 与当前工作区 PDF Markdown Summary 0.6.9。

## 版本与核查范围

- GitHub Releases API 的最新稳定版为 **v0.1.8**，发布时间 `2026-09-21T21:22:51Z`，即北京时间 2026-09-22 05:22；不是预发布。
- 发布标签对应提交 `b8f79c57ebc0044be41323d89b2a45d3fda8460e`。
- 查询时 main 为 `4cc9fa17653d695d64fb9eee5b33d4de55ff84e8`（2026-10-04）。默认 PDF 转换器在 v0.1.8 与该 main 快照中逐字节相同，SHA-256 为 `8a48783a111f8c240ab87320921455e879a5f6753421a6cc472e6d2b89bf2c92`。
- 本次核查发布记录、默认 PDF 转换器、独立 OCR 插件、Azure 转换器和本项目正式源码；未安装 MarkItDown，未运行同 PDF 的 A/B 测试。因此结论是能力与实现范围对比，不是速度、准确率或裁剪质量排名。

来源：[最新发布 API](https://api.github.com/repos/microsoft/markitdown/releases/latest)、[v0.1.8 发布说明](https://github.com/microsoft/markitdown/releases/tag/v0.1.8)。发布说明将本版定位为维护与修复汇总，典型输入的行为预计基本延续 0.1.7。

## 能力对照

| 维度 | MarkItDown v0.1.8 | 本项目当前实现 | 对我们的意义 |
| --- | --- | --- | --- |
| 定位 | 多格式文档转 Markdown，便于文本分析和入库 | 面向论文、技术报告，保存正文与图表并准备带图摘要 | 使用目标不同 |
| 默认 PDF 文本后端 | pdfplumber 与 pdfminer.six | PyMuPDF；可选 Layout 语义区域辅助图表提取 | 不能仅按后端推断输出质量 |
| 可编辑表格 | 有基于词坐标的表格/表单识别与 Markdown 表格输出 | `auto/screenshot/structure` 当前均输出截图，未接入结构化表格 | MarkItDown 提供了我们尚缺的能力 |
| 独立图表文件 | 默认 PDF 转换器返回 Markdown 文本；没有本项目式 PNG 资产导出流程 | Figure/Table 区域裁剪、独立 PNG、题注旁相对路径插图 | 本项目更适合图文阅读资料保存 |
| 矢量图与图内文字 | OCR 插件侧重 PDF 图片对象识别，不等同于完整 Figure 区域识别 | 按原页区域截图，利用图形对象和文字边界证据 | 对原页视觉内容保留更有针对性；仍需逐图验证 |
| 独立公式 | 默认转换器没有对应的公式区域保存流程 | 区域完整时截图，关图片时合并文本代码块；不完整时待复核 | 保留视觉公式，但不等于生成可编辑 LaTeX |
| 扫描页与图片文字 | 独立 `markitdown-ocr` 插件提供 LLM Vision OCR，需模型客户端和插件启用 | `--ocr` 尚为保留参数，报告明确标记 `not_implemented` | OCR 是我们的实际短板 |
| 云服务选择 | 可接 Azure Document Intelligence 与 Content Understanding | 当前正式工作流以本地提取为主 | 外部增强可作为可选后端评估 |
| 质量与追溯 | 转换结果主要为 Markdown；不提供同等的图表裁剪质量资产清单 | 块 JSON、图表索引、页码/bbox、置信度、告警、复核状态、转换报告 | 便于检查漏图、截断和图片来源 |
| 摘要 | 转换本身不完成本项目式论文带图摘要 | 脚本准备文本和图表素材，再由 Agent 结合两者撰写 | 本项目已有完整的阅读工作流约定 |
| 接入方式 | 统一 Python API/CLI、多格式、插件和 MCP 包 | 四个 PDF 入口脚本与 Skill | MarkItDown 的通用接入设计值得参考 |

MarkItDown 来源：[默认 PDF 转换器](https://github.com/microsoft/markitdown/blob/v0.1.8/packages/markitdown/src/markitdown/converters/_pdf_converter.py)、[OCR 插件说明](https://github.com/microsoft/markitdown/blob/v0.1.8/packages/markitdown-ocr/README.md)、[项目说明](https://github.com/microsoft/markitdown/blob/v0.1.8/README.md)。

## 核查出的适用边界

1. **表格结构化不是通用论文版式理解。** 默认 PDF 源码的词坐标算法面向表单/结构化行列，不能据此认定复杂科研表格、多级表头或双栏正文的准确率更高。实际 `convert()` 使用 `_extract_form_content_from_words()`；不能把文件中其他助手函数的存在当成调用生效。
2. **OCR 提取文字与保存原图不同。** OCR 图片在内存中处理，PDF 输出插入识别文字，并未落盘为与本项目等价的图表文件。其含图片页文字分支按 y/x 组合字符，存在同高度双栏串接的实现风险，尚未在本轮复现。
3. **扫描页能力需要实测。** 插件文档说明支持扫描页，但源码的最终整页回退检查文档结果是否为空，流程此前又添加了页标题；不能仅凭 README 保证每种无图片对象扫描页、混合页均触发整页 OCR。
4. **启用 OCR 不保证继承默认表格结构化。** `PdfConverterWithOCR` 使用独立 PDF 流程，并非默认 `PdfConverter` 的子类，需验证插件启用后表格和阅读顺序是否变化。
5. **云接入不等于离线默认能力。** Azure 转换器将服务结果转换为 Markdown，服务质量、费用和所需配置要单独评估；未看到它们实现与本项目等价的图表 PNG/索引保存工作流。

来源：[OCR PDF 转换器](https://github.com/microsoft/markitdown/blob/v0.1.8/packages/markitdown-ocr/src/markitdown_ocr/_pdf_converter_with_ocr.py)、[Document Intelligence 转换器](https://github.com/microsoft/markitdown/blob/v0.1.8/packages/markitdown/src/markitdown/converters/_doc_intel_converter.py)、[Content Understanding 转换器](https://github.com/microsoft/markitdown/blob/v0.1.8/packages/markitdown/src/markitdown/converters/_cu_converter.py)。上述源码风险属于实现推断，不是已完成的缺陷复现实验。

## 建议

**保留我们的图表保存与质量复核主流程，优先补结构化表格，再评估 OCR。**

- 表格：参考其结构化输出思路，基于已裁好的表格区域尝试解析；同时保留原截图和页码/bbox。高置信度结果输出 Markdown 表格，低置信度回退截图。避免将整页词坐标算法直接替换当前论文阅读顺序逻辑。
- OCR：采用可选识别后端，仅对缺文本页或指定区域调用；继续使用我们的图表索引和质量报告，明确成本与识别状态。MarkItDown 插件可作为对照实现，但不宜未经实测直接替换提取链路。
- 接入：如后续扩大到 DOCX/PPTX/XLSX 入库，再考虑以 MarkItDown 作为多格式入口，PDF 论文仍路由到本项目。
- 下一步评测：8 份 Basic Benchmark 验证正文顺序、表格数值与图表覆盖；扫描能力另用合成扫描页、混合页验证。结果统一写入 `tests/results/<yyyymmdd-xxx>/<pdf-name>/`，不写入只读 benchmark。当前不据此宣称哪一方更快或更准确。

## 补充：文本结构解析的组件与能力

MarkItDown 默认 PDF 路径采用公开的 `pdfminer.six`、`pdfplumber`，后者也构建于 pdfminer.six 之上。MarkItDown 自有逻辑负责表单/表格词坐标规则、部分编号断行合并与转换封装。默认 `PdfConverter.convert()` 直接读取文本/表单结果，并返回 Markdown 字符串，没有额外调用统一的论文语义结构解析器。

| 用户关心的结构 | 默认本地 PDF 路径的实际能力 |
| --- | --- |
| 标题与章节层级 | 没有按字号、字体、编号推断 H1–H6 的专门实现 |
| 正文类型 | 能恢复文字与部分空间分组；没有摘要、正文、参考文献、脚注等统一语义分类 |
| 图注、表注、题注 | 可提取这些文字，但没有专门题注分类及与图表的配对流程 |
| 表格结构 | 有表单/行列启发式，不等同于一般文档语义理解；首行作为表头也不代表识别了语义表头 |
| 返回结构 | `DocumentConverterResult` 包含 Markdown 与可选 title，没有本项目式逐块类型、层级、bbox、题注关联树；默认 PDF 转换器只填 Markdown |

pdfminer 的文本框层次是空间布局聚合，不是章节目录层次。见 [pdfminer 布局算法说明](https://pdfminersix.readthedocs.io/en/latest/topic/converting_pdf_to_text.html)、[pdfplumber 项目](https://github.com/jsvine/pdfplumber)、[MarkItDown 结果对象](https://github.com/microsoft/markitdown/blob/v0.1.8/packages/markitdown/src/markitdown/_base_converter.py)。

不同格式需分别判断：DOCX 经公开组件 Mammoth 转 HTML，再由 BeautifulSoup/markdownify 及自定义渲染规则转 Markdown；此时可利用原文件已有的标题样式。保留已有结构与从 PDF 视觉版式推断结构是不同任务，不能把 DOCX/HTML 的效果直接推广到 PDF。来源：[DOCX 转换器](https://github.com/microsoft/markitdown/blob/v0.1.8/packages/markitdown/src/markitdown/converters/_docx_converter.py)。

Azure Document Intelligence 路径调用 `prebuilt-layout`：服务提供标题/章节标题、页眉页脚/脚注等段落角色，也支持标题层级、表格 caption 与 figure caption 的富 Markdown 表达。能力来自云服务模型；MarkItDown 封装仅读取 `result.content`、去掉 HTML 注释并返回，没有透传完整 `paragraphs/figures/tables` JSON。官方能力说明不是本项目测试集上的准确率保证。见 [Layout 角色文档](https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/prebuilt/layout?view=doc-intel-4.0.0)、[Markdown 元素文档](https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/concept/markdown-elements?view=doc-intel-4.0.0)。

本项目也尚无完整层级恢复：`core/pdf_to_markdown.py::_paragraphs_to_document()` 对识别出的标题统一设置 `level=2`。我们具备标题候选规则及专门图表题注/配对能力，但不应宣称当前已准确恢复所有标题层级或正文语义类型。

因此，若目标是本地 PDF 的完整语义结构，MarkItDown 默认转换器不是可直接替换的优秀结构解析引擎；若评估云端布局识别，应直接比较服务的结构 JSON 与本项目输出，再用人工标注验证准确率。

## 本项目源码依据与维护范围

- `skills/pdf-markdown-summary/references/pdf-to-markdown.md`：表格截图现状、OCR 状态、公式与就近插图规则。
- `skills/pdf-markdown-summary/scripts/core/pdf_to_markdown.py`：相对图片路径、质量门、公式保存与转换报告；报告保留 OCR 未实现状态。
- `skills/pdf-markdown-summary/scripts/lib/text_extract.py`、`lib/markdown.py`：标题/文本结构与 Markdown 序列化。
- `skills/pdf-markdown-summary/scripts/lib/assess.py`：资产质量状态与插入条件。
- `skills/pdf-markdown-summary/scripts/core/process_pdf.py`、`core/summarize_pdf.py`：完整流程复用与摘要素材准备，最终摘要由 Agent 撰写。

本次仅新增调研文档并维护任务台账，未修改正式或维护测试源码，未改变函数声明、职责、编号或协作关系；功能全集、JSON、源码覆盖索引及三张 SVG 无需同步。未运行业务测试，未更新 golden。完成后执行任务台账 `check` 和 `git diff --check`，结果记录于台账。
