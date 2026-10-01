# Agent 工作流指南

> 本文档只记录本仓库最关键的 Agent 执行规则。

## 1. 交互规则

- to-do list 使用中文书写。
- 用户交互内容使用中文输出。
- 代码 review 的结论内容使用中文输出。
- 不要随意删除、回滚或覆盖用户已有修改。
- 涉及归档、删除、迁移时，先确认影响范围，再执行。

## 2. 顶层目录职责

- `design/`：项目设计与文档目录。
- `skills/`：核心工作目录，正式 Skill 存放处。
- `experiments/`：本地实验产物目录（已加入 .gitignore，不上传 GitHub）。一次性探索脚本与大体积 PNG/debug/Layout 产物写这里，内部文件不受 `-yyyyMMDD` 命名约束。
- `tests/`：测试数据、测试脚本、测试结果目录（不要整体加入 .gitignore）。
  - `tests/basic-benchmark/`：**只读**。固定测试集 PDF 存放目录。**禁止往 benchmark 中写入任何测试结果或临时文件**。
  - `tests/results/`：端到端测试输出目录，按日期分文件夹（如 `20260807-001/`），已加入 .gitignore。**所有测试结果都写这里**（含 golden 基准）。
  - `tests/annotations/`：人工标注 GT，已加入 .gitignore。
  - `tests/holdout/`：冻结 holdout 集，已加入 .gitignore。
  - `tests/scripts/`、`tests/eval/`：pytest 脚本与版本化评测器，保留可提交。
- `old-version/`：历史代码归档目录，仅供参考。
- `task-list.md`：后续用于记录所有操作、修改和测试。

## 3. 正式 Skill 目录

- 当前正式 Skill 位于 `skills/pdf-markdown-summary/`。
- 该目录下的 `SKILL.md`、`references/`、`scripts/` 必须保持为最新版。
- Skill 对外能力以 `skills/pdf-markdown-summary/` 为准。

## 4. design 目录规则

- `design/1-archive/` 存放旧文档归档。
- `design/2-ref/` 是只读参考目录（只读约束不变）。
- `design/3-plans/` 存放当前计划类文档（2026-09-23 由原 `docs/2-plans/` 重编号而来；2026-09-30 随顶层 `docs/` 改名为 `design/`）。
- 所有新建 Markdown 文档文件名必须增加 `-yyyyMMDD` 时间后缀。
- 禁止修改、删除、移动、重命名 `design/2-ref/` 中的任何文件。
- 禁止把新的运行产物写入 `design/2-ref/`。
- 与当前 Skill 重构无关的旧文档，应移动到 `design/1-archive/`。

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
- 测试数据、测试输出放入 `tests/`，不要写入 `design/2-ref/`。
- 完成开发后如需进行实际 PDF 文档测试，优先使用 `tests/basic-benchmark/`（Basic Benchmark）中的 8 份 PDF（扁平存放于 `tests/basic-benchmark/*.pdf`）：1706.03762v7、Qwen3-Omni、2607.24653v2-Kimi-K3、FunAudio-ASR、gemini_v2_5、gpt-5-system-card、KearnsNevmyvakaHFTRiskBooks、DeepSeek_V41_Tech_Report。
- **`tests/basic-benchmark/` 是只读目录**：只从中读取 PDF，**不要往里面写入任何测试结果、临时文件或调试产物**。测试输出统一写入 `tests/results/<yyyymmdd-xxx>/`。注意：`extract_pdf_assets.py` 在未传 `--out-text` 时默认回退写到 PDF 所在目录的 `text/`——跑 benchmark PDF 时**必须显式传 `--out-text`**，否则会违反只读约束（此默认回退已多次造成 `tests/basic-benchmark/text/` 违规产物）。
- 实际测试输出统一写入 `tests/results/<yyyymmdd-xxx>/`，格式为日期加序号，如 `20260605-001`、`20260605-002`。
- `tests/results/<yyyymmdd-xxx>/` 下按每个 PDF 名称建立独立结果目录，例如 `tests/results/20260605-001/<pdf-name>/`。
- 每个 PDF 结果目录下应按输出类型分层保存：`markdown/` 存 Markdown，`assets/` 存通用资源，`images/` 存图片，`txt/` 存文本。
- `pytest tests/scripts/ -q` 的「全绿」定义：golden 用例默认纳入且必须实际执行、0 跳过；golden 收集数为 0 或被跳过一律判失败。本地定向调试可用环境变量 `PDF_SKILL_ALLOW_GOLDEN_SKIP=1` 放行排除，但该模式**不算全绿**（仅 WARNING）。
- golden 基准（`tests/results/**/images/golden_index.json`）是变更检测器而非正确性基准；基准不纳入版本控制（tests/results/ 已 gitignore），clone 后需运行 `--update-golden` 本地生成；基准更新后在 `task-list.md` 逐条说明差异原因。
- `tests/eval/` 是版本化评测器（非 pytest 套件），可复用指标计算放这里；一次性探索脚本与大体积产物放 `experiments/`。
- `tests/annotations/` 存放人工 bbox 真值与标注规范（SCHEMA），标注产物不进 `design/2-ref/`。
- debug 叠图做跨版本/跨批次对比前，必须先用机器判据标注产物代际：`grep -l "LINE STYLE TAXONOMY" <批次>/*/images/debug/*_stages_legend.txt | wc -l`（0 命中=旧体系 ≤V0.6.6，全命中=新三桶线型体系）；不要用 `"Style: Solid"` 判别（旧图例天然含该字样）。体系规范、新旧对照与判据详见 `design/4-analysis/debug视觉标注体系说明-20260930.md`；改动标线颜色/线型须同步该文档与功能编号 F23.008/011/012。

## 9. 功能模块全集与编号的持续维护

- 每次新增、删除、重命名、移动、拆分、合并函数/类/方法，或修改其职责、参数、返回值、调用关系、适用条件和行为时，必须检查功能模块全集与编号。范围包含正式 `skills/pdf-markdown-summary/scripts/`、维护的 `tests/scripts/` 与 `tests/eval/`。
- 功能按实际职责划分，不按脚本或函数个数机械编号。新增助手若仍服务于已有功能，应更新该功能的实现引用；出现独立新能力时，才新增功能编号。
- 必须同步维护 `design/4-analysis/` 中的[功能模块全集与编号](design/4-analysis/PDF功能模块全集与编号-20260930.md)、[机器可读编号表](design/4-analysis/PDF功能模块编号表-20260930.json)与[源码覆盖索引](design/4-analysis/PDF功能模块源码覆盖索引-20260930.md)，更新受影响的职责、适用状态、输入输出、实现引用、行号与源码哈希。
- 已发布的 `Fxx.nnn` 保持身份：函数/文件移动、重命名或展示排序变化不重排编号；新功能在对应域追加；删除功能保留原编号并标记弃用，不删除历史身份、不复用编号。拆分或合并时记录新旧功能的承接关系。
- 功能、数量、分组或流程关系变化时，同步更新[功能全集索引 SVG](design/4-analysis/PDF功能模块全集索引图-20260930.svg)、[脚本协作泳道图](design/4-analysis/PDF脚本协作泳道图-20260930.svg)、[图表提取展开图](design/4-analysis/PDF图表提取模块展开图-20260930.svg)及相关阅读说明；仅实现位置变化时，核对图中引用是否需要更新。
- 完成变更前，验证编号唯一性、文档/JSON/SVG 一致性、源码声明归属、实现引用与链接有效性；SVG 有变化时检查渲染。检查结果、编号调整与无需修改某项产物的理由须用中文记录到 `task-list.md`。源码声明覆盖检查不能替代第 8 节要求的业务测试。

## 会话结束任务同步（必须）

每次会话结束前，若本次涉及任务完成——包括但不限于 bug 修复、功能开发、代码审查、测试数据准备、文档更新、配置运维——必须：

1. 把新增条目与状态变更写入根目录 `task-list.md`，与实际进度同步；
2. 在本次最后一条回复中告知用户：记录/更新了哪些条目（ID + 简述）。
3. 写入后跑 `check`。`check` 是预览门禁：表内空行、单元格裸 HTML、未按 CommonMark 闭合的反引号必须失败；围栏代码里的示例表格不算真实表；手改 md 后也必须再跑。

若本次未涉及任何任务完成，无需操作也无需提示。若已配置 `.claude/settings.json` 的 `Stop` hook，则由该 hook 保证每会话触发一次；**未配置时由 agent 在会话结束前自觉执行**（不要在未安装 hook 时写「由 Stop hook 保证触发」）。
