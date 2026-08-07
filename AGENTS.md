# Agent 工作流指南

> 本文档只记录本仓库最关键的 Agent 执行规则。

## 1. 交互规则

- to-do list 使用中文书写。
- 用户交互内容使用中文输出。
- 代码 review 的结论内容使用中文输出。
- 不要随意删除、回滚或覆盖用户已有修改。
- 涉及归档、删除、迁移时，先确认影响范围，再执行。

## 2. 顶层目录职责

- `docs/`：项目文档目录。
- `skills/`：核心工作目录，正式 Skill 存放处。
- `tests/`：测试数据、测试脚本、测试结果目录（不要整体加入 .gitignore）。
  - `tests/basic-benchmark/`：**只读**。固定测试集存放目录（回测 PDF + golden_index.json）。**禁止往 benchmark 中写入任何测试结果或临时文件**。
  - `tests/results/`：端到端测试输出目录，按日期分文件夹（如 `20260807-001/`），已加入 .gitignore。**所有测试结果都写这里**。
  - `tests/annotations/`：人工标注 GT，已加入 .gitignore。
  - `tests/holdout/`：冻结 holdout 集，已加入 .gitignore。
  - `tests/scripts/`、`tests/eval/`：pytest 脚本与版本化评测器，保留可提交。
- `old-version/`：历史代码归档目录，仅供参考。
- `task-list.md`：后续用于记录所有操作、修改和测试。

## 3. 正式 Skill 目录

- 当前正式 Skill 位于 `skills/pdf-markdown-summary/`。
- 该目录下的 `SKILL.md`、`references/`、`scripts/` 必须保持为最新版。
- Skill 对外能力以 `skills/pdf-markdown-summary/` 为准。

## 4. docs 目录规则

- `docs/1-archive/` 存放旧文档归档。
- `docs/2-plans/` 原存放重构设计与实施计划，重构完成后已归档至 `docs/1-archive/`；后续如有新计划可重建该目录。
- `docs/2-ref/` 是只读参考目录（原 `docs/3-ref/`，已重编号；只读约束不变）。
- `docs/3-experiments/` 是实验产物目录（已加入 .gitignore，不上传 GitHub）；其内部文件不受 `-yyyyMMDD` 命名约束。
- 所有新建 Markdown 文档文件名必须增加 `-yyyyMMDD` 时间后缀。
- 禁止修改、删除、移动、重命名 `docs/2-ref/` 中的任何文件。
- 禁止把新的运行产物写入 `docs/2-ref/`。
- 与当前 Skill 重构无关的旧文档，应移动到 `docs/1-archive/`。

## 5. old-version 规则

- `old-version/` 只供参考。
- 不再修改和维护 `old-version/` 下的旧代码。
- 不要基于 `old-version/` 开发新功能。
- 需要保留历史快照时，可以新增归档目录，但不要改动已有归档内容。

## 6. task-list.md 规则

- 根目录将维护 `task-list.md`。
- 所有操作、修改、移动、归档、删除都要记录。
- 所有测试命令、验证命令和结果都要记录。
- 记录使用中文。
- 在用户提供正式 example/template 前，先只遵守本规则，不主动新建 `task-list.md`。

## 7. PDF Skill 工作规则

- PDF 转 Markdown、PDF 带图摘要、完整处理流程都属于 `pdf-markdown-summary` Skill。
- 生成摘要时，必须同时使用论文文本和图表图片。
- 摘要默认中文，除非用户明确要求英文。
- Markdown 中图片路径使用相对路径。
- 旧版 PDF 图表提取逻辑可参考，但正式实现以当前 Skill 脚本为准。

## 8. 验证规则

- 修改 Skill 脚本后，至少验证四个入口脚本的 `--help`：`extract_pdf_assets.py`、`pdf_to_markdown.py`、`process_pdf.py`、`summarize_pdf.py`。
- 修改 Python 脚本后，至少运行一次 `compileall` 或同等语法检查。
- 测试数据、测试输出放入 `tests/`，不要写入 `docs/2-ref/`。
- 完成开发后如需进行实际 PDF 文档测试，优先使用 `tests/basic-benchmark/`（Basic Benchmark）中的 8 份 PDF：回测组1 七份 + 回测组2 的 `DeepSeek_V4.pdf`。
- **`tests/basic-benchmark/` 是只读目录**：只从中读取 PDF 和 golden 基准，**不要往里面写入任何测试结果、临时文件或调试产物**。测试输出统一写入 `tests/results/<yyyymmdd-xxx>/`。
- 实际测试输出统一写入 `tests/results/<yyyymmdd-xxx>/`，格式为日期加序号，如 `20260605-001`、`20260605-002`。
- `tests/results/<yyyymmdd-xxx>/` 下按每个 PDF 名称建立独立结果目录，例如 `tests/results/20260605-001/<pdf-name>/`。
- 每个 PDF 结果目录下应按输出类型分层保存：`markdown/` 存 Markdown，`assets/` 存通用资源，`images/` 存图片，`txt/` 存文本。
- `pytest tests/scripts/ -q` 的「全绿」定义：golden 用例默认纳入且必须实际执行、0 跳过；golden 收集数为 0 或被跳过一律判失败。本地定向调试可用环境变量 `PDF_SKILL_ALLOW_GOLDEN_SKIP=1` 放行排除，但该模式**不算全绿**（仅 WARNING）。
- golden 基准（`tests/basic-benchmark/**/images/golden_index.json`）是变更检测器而非正确性基准；基准更新必须单独提交，并在 `task-list.md` 逐条说明差异原因。
- `tests/eval/` 是版本化评测器（非 pytest 套件），可复用指标计算放这里；一次性探索脚本与大体积产物放 `docs/3-experiments/`。
- `tests/annotations/` 存放人工 bbox 真值与标注规范（SCHEMA），标注产物不进 `docs/2-ref/`。
