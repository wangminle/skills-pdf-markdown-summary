# -*- coding: utf-8 -*-
"""tests/eval — 版本化评测器（A0-3）。

从 docs/3-experiments/20260728-pymupdf4llm-layout-bbox/scripts/ 的
一次性实验脚本（03/05/09）迁出可复用的指标计算，并修正二次复核
发现的三处口径缺陷：

1. 资产键改为 document_id + kind + ident + caption_page + occurrence + group_id
   （原实验只用 type+ident，忽略页码，造成虚假跨页分歧）；
2. legacy/预测匹配强制校验页码；
3. 配对器加全页一对一约束，并输出候选重复占用统计。

口径以 docs/PDF图表提取技术迭代实施方案-20260731.md §2 为准。

本包不是 pytest 套件；自检请运行 ``python tests/eval/selfcheck.py``
或 ``python tests/eval/run_eval.py --selfcheck``。
"""
