#!/usr/bin/env python3
"""编号资料一致性校验（动态版）：所有计数从磁盘与 JSON 推导，不硬编码 85/1106 等数字。

不替代业务测试。任一检查失败即非零退出。
"""
import ast
import hashlib
import json
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[2]
A = ROOT / "design/4-analysis"
R = json.loads((A / "PDF功能模块编号表-20260930.json").read_text(encoding="utf-8"))
INDEX = (A / "PDF功能模块源码覆盖索引-20260930.md").read_text(encoding="utf-8")
FULL = (A / "PDF功能模块全集与编号-20260930.md").read_text(encoding="utf-8")
GUIDE = (A / "PDF脚本协作图阅读说明-20260930.md").read_text(encoding="utf-8")
SVG_INDEX = (A / "PDF功能模块全集索引图-20260930.svg").read_text(encoding="utf-8")
fails = []


def check(cond, msg):
    if not cond:
        fails.append(msg)


def report_and_exit():
    """有失败项即逐条打印并非零退出；供分阶段前置校验复用。"""
    if fails:
        print("校验失败:", len(fails))
        for f in fails[:60]:
            print(" -", f)
        sys.exit(1)


# 0. 条目字段规范：先于一切取键操作。只要求本脚本自身无条件解引用的键
#    （id/group/refs），缺失时逐条报告而不是 KeyError 崩溃。其余键与多余键
#    （如 implementations）不在本脚本判定范围，交由编号同步脚本把关——
#    这样任何原脚本能跑完的 JSON 在这里结论不变，不会引入假失败。
REQUIRED_KEYS = ("id", "group", "refs")
for f in R["features"]:
    missing = [k for k in REQUIRED_KEYS if k not in f]
    if missing:
        fails.append(f"条目缺少必需键: {f.get('id', '<无 id>')} 缺少 {missing}")
report_and_exit()

# 1. 编号身份
ids = [f["id"] for f in R["features"]]
check(len(ids) == len(set(ids)), "功能编号重复")
check(all(re.fullmatch(r"F\d{2}\.\d{3}", i) for i in ids), "编号格式错误")
cnt = Counter("F" + f["group"] for f in R["features"])
check(cnt == {g["id"]: g["count"] for g in R["groups"]}, "功能域计数与 groups 不一致")
idset = set(ids)
st = R["stats"]
check(st["runtime_features"] + st["testing_features"] == len(ids), "stats 功能数与编号数不符")

# 2. 文件集合与哈希
disk = {
    p.relative_to(ROOT).as_posix()
    for prefix in ["skills/pdf-markdown-summary/scripts", "tests/scripts", "tests/eval"]
    for p in (ROOT / prefix).rglob("*.py")
    if "__pycache__" not in p.parts
}
check(disk == set(R["source_sha256"]), f"磁盘文件集合与 JSON 不一致: {disk ^ set(R['source_sha256'])}")
t_files = sum(1 for f in disk if f.startswith("tests/"))
check(st["testing_files"] == t_files and st["runtime_files"] == len(disk) - t_files, "stats 文件数不符")

# 3. 源码声明归属
cov = {}
for c in R["source_coverage"]:
    if c["symbol"] != "<module>":
        cov[(c["file"], c["symbol"])] = c
defs = 0
for rel, sha in R["source_sha256"].items():
    raw = (ROOT / rel).read_bytes()
    check(hashlib.sha256(raw).hexdigest() == sha, f"JSON 哈希陈旧: {rel}")
    tree = ast.parse(raw)

    def visit(node, anc):
        global defs
        for ch in ast.iter_child_nodes(node):
            if isinstance(ch, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                name = ".".join(anc + [ch.name])
                defs += 1
                c = cov.get((rel, name))
                if c is None:
                    fails.append(f"声明未归属: {rel}::{name}")
                else:
                    check(c["line"] == ch.lineno and c["end"] == ch.end_lineno, f"行号漂移: {rel}::{name}")
                    check(c["ids"] and set(c["ids"]) <= idset, f"归属编号无效: {rel}::{name}")
                visit(ch, anc + [ch.name])
            else:
                visit(ch, anc)

    visit(tree, [])
check(defs == len(cov) == st["definitions"] == st["definition_coverage"],
      f"声明数不一致: AST={defs} coverage={len(cov)} stats={st['definitions']}")

# 4. refs 与 AST
amap = {}
for f in R["features"]:
    for r in f["refs"]:
        c = cov.get((r["file"], r["symbol"]))
        if c is None:
            check(r["symbol"] == "<module>", f"refs 指向无声明: {f['id']} {r['file']}::{r['symbol']}")
        else:
            check(c["line"] == r["line"], f"refs 行号陈旧: {f['id']} {r['file']}::{r['symbol']}")

# 5. 覆盖索引 md：每文件哈希与 JSON 一致
sec = {m.group(1).strip(): m.group(2) for m in
       re.finditer(r"(?m)^## (.+)\n\n源码 SHA256：`([0-9a-f]{64})`", INDEX)}
check(set(sec) == set(R["source_sha256"]), "覆盖索引章节集合与 JSON 不一致")
for rel, h in sec.items():
    check(R["source_sha256"].get(rel) == h, f"覆盖索引哈希陈旧: {rel}")
rows = len(re.findall(r"(?m)^\| `[^`]+` \| \[L\d+–\d+\]", INDEX))
check(rows == len(cov) + 0 or rows >= len(cov), f"覆盖索引行数异常 {rows}/{len(cov)}")

# 6. 全集 md 与阅读说明、SVG 文案
check(f"**{len(ids)} 个编号功能模块**" in FULL, "全集 md 功能总数")
check(f"正式实现 **{st['runtime_features']} 个**（{st['runtime_files']} 个 Python 文件）" in FULL, "全集 md 正式实现数")
check(f"测试/评测保障 **{st['testing_features']} 个**（{st['testing_files']} 个 Python 文件）" in FULL, "全集 md 测试数")
check(f"**{st['definitions']} 个，全部有功能归属**" in FULL, "全集 md 声明数")
check(f"覆盖 {len(disk)} 个维护 Python 文件" in GUIDE, "阅读说明维护文件数")
check(f"{len(disk)} 个维护 Python 文件" in SVG_INDEX, "索引图维护文件数")
check(f"{st['definitions']:,} 个声明" in SVG_INDEX, "索引图声明数")
check(f"{len(ids)}个编号功能" in SVG_INDEX, "索引图功能总数")
feat_by_id = {f["id"]: f for f in R["features"]}
cur = None
for line in FULL.split("\n"):
    m = re.match(r"### (F\d+\.\d+) ·", line)
    if m:
        cur = m.group(1)
    if line.startswith("**实现位置：**") and cur:
        refs = feat_by_id[cur]["refs"][:12]
        want = "；".join(f"[{r['file']}::{r['symbol']}（L{r['line']}）](../../{r['file']})" for r in refs)
        check(line == f"**实现位置：**{want}。", f"全集 md 实现位置陈旧: {cur}")

# 7. SVG XML 合法
for svg in A.glob("*.svg"):
    try:
        ET.parse(svg)
    except ET.ParseError as e:
        fails.append(f"SVG 非法 XML: {svg.name}: {e}")

# 8. 文档内文件链接有效
for md in A.glob("*.md"):
    text = md.read_text(encoding="utf-8")
    for m in re.finditer(r"\]\(([^)#\s]+)(?:#[^)]*)?\)", text):
        tgt = m.group(1)
        if tgt.startswith(("http://", "https://")):
            continue
        check((md.parent / unquote(tgt)).resolve().exists(), f"断链: {md.name} -> {tgt}")

report_and_exit()
print(f"校验通过: {len(ids)} 编号 / {len(R['groups'])} 域 / {len(disk)} 文件 "
      f"({st['runtime_files']}+{st['testing_files']}) / {defs} 声明 / AST-JSON-索引-全集-SVG 一致")
