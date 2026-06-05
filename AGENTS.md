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
- `tests/`：测试数据、测试脚本、测试结果目录。
- `old-version/`：历史代码归档目录，仅供参考。
- `task-list.md`：后续用于记录所有操作、修改和测试。

## 3. 正式 Skill 目录

- 当前正式 Skill 位于 `skills/pdf-markdown-summary/`。
- 该目录下的 `SKILL.md`、`references/`、`examples/`、`scripts/` 必须保持为最新版。
- Skill 对外能力以 `skills/pdf-markdown-summary/` 为准。
- 如果根目录 `scripts/` 有有效代码更新，必须同步到 `skills/pdf-markdown-summary/scripts/`。
- 不要只改根目录 `scripts/` 而忘记同步 Skill 包。

## 4. docs 目录规则

- `docs/1-archive/` 存放旧文档归档。
- `docs/2-plans/` 存放当前重构设计与实施计划。
- `docs/3-ref/` 是只读参考目录。
- 所有新建 Markdown 文档文件名必须增加 `-yyyyMMDD` 时间后缀。
- 禁止修改、删除、移动、重命名 `docs/3-ref/` 中的任何文件。
- 禁止把新的运行产物写入 `docs/3-ref/`。
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

- 修改 Skill 脚本后，至少验证三个入口脚本的 `--help`。
- 修改 Python 脚本后，至少运行一次 `compileall` 或同等语法检查。
- 修改根目录 `scripts/` 后，同步到 Skill 目录，并检查两边差异。
- 测试数据、测试输出放入 `tests/`，不要写入 `docs/3-ref/`。
