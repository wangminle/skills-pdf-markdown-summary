#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""维护工具回归：动态功能域、探测页数与缓存键、跨平台 JSON 换行。"""

from __future__ import annotations

import ast
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import fitz

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TOOLS_DIR = PROJECT_ROOT / "tools"


def _load_module(relative_path: str, name: str):
    spec = importlib.util.spec_from_file_location(name, PROJECT_ROOT / relative_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _synthetic_registry(domain_count: int = 27) -> dict:
    groups = []
    features = []
    for number in range(1, domain_count + 1):
        group = f"{number:02d}"
        scope = "runtime" if number <= domain_count - 2 else "testing"
        groups.append({"id": f"F{group}", "name": f"域 {group}", "count": 1})
        features.append({
            "id": f"F{group}.001",
            "group": group,
            "name": f"功能 {group}",
            "description": f"功能 {group} 描述",
            "mode": "默认",
            "scope": scope,
            "refs": [],
        })
    runtime = domain_count - 2
    return {
        "groups": groups,
        "features": features,
        "stats": {
            "runtime_features": runtime,
            "testing_features": 2,
            "definitions": domain_count,
        },
    }


def test_draw_feature_index_uses_dynamic_domain_count_and_scopes(tmp_path: Path) -> None:
    script_dir = tmp_path / "tools" / "feature-registry"
    script_dir.mkdir(parents=True)
    for name in ("draw_feature_index.py", "draw_flows.py"):
        shutil.copy2(TOOLS_DIR / "feature-registry" / name, script_dir / name)
    out_dir = tmp_path / "design" / "4-analysis"
    out_dir.mkdir(parents=True)
    (out_dir / "PDF功能模块编号表-20260930.json").write_text(
        json.dumps(_synthetic_registry(), ensure_ascii=False), encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, str(script_dir / "draw_feature_index.py")],
        cwd=tmp_path, capture_output=True, text=True,
    )

    assert proc.returncode == 0, proc.stderr
    svg = (out_dir / "PDF功能模块全集索引图-20260930.svg").read_text(encoding="utf-8")
    assert "27个功能域、27个编号功能" in svg
    assert "F01–F25：正式实现 25 项" in svg
    assert "F26–F27：测试与评测 2 项" in svg
    for number in range(1, 28):
        assert f'data-feature-id="F{number:02d}.001"' in svg


def test_dict_probe_pages_come_from_pdf_not_last_instrumented_call(
    tmp_path: Path, monkeypatch,
) -> None:
    probe = _load_module("tools/render-probe/probe_dict_call_reuse.py", "dict_probe_pages")
    pdf = tmp_path / "paper.pdf"
    with fitz.open() as doc:
        for _ in range(3):
            doc.new_page()
        doc.save(pdf)
    monkeypatch.setattr(probe, "BENCH_DIR", tmp_path)

    def fake_run(cmd, **_kwargs):
        out_json = Path(cmd[cmd.index("--out-json") + 1])
        out_json.parent.mkdir(parents=True, exist_ok=True)
        out_json.write_text(json.dumps({
            "return_code": 0,
            "total_sec": 0.1,
            "calls": [{"page": 0, "method": "dict", "detail": [], "calls": 1, "sec": 0.1}],
        }), encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(probe.subprocess, "run", fake_run)
    out_dir = tmp_path / "out"
    assert probe.main(["--only", "paper", "--out-dir", str(out_dir)]) == 0
    result = json.loads((out_dir / "dict_call_reuse.json").read_text(encoding="utf-8"))
    assert result["per_pdf"]["paper"]["pages"] == 3


def test_probe_call_keys_include_positional_and_keyword_options() -> None:
    probe = _load_module("tools/render-probe/probe_dict_call_reuse.py", "dict_probe_keys")
    assert probe.text_key(("dict", None, 16, True), {}) == probe.text_key(
        (), {"option": "dict", "clip": None, "flags": 16, "sort": True},
    )
    assert probe.text_key(("dict", None, 16, False), {}) != probe.text_key(
        ("dict", None, 32, False), {},
    )
    assert probe.drawings_key((True,), {}) == probe.drawings_key((), {"extended": True})
    assert probe.drawings_key((False,), {}) != probe.drawings_key((True,), {})
    assert probe.image_info_key((True, False), {}) == probe.image_info_key(
        (), {"hashes": True, "xrefs": False},
    )
    assert probe.image_info_key((False, True), {}) != probe.image_info_key((True, False), {})


def test_all_probe_json_writes_pin_lf_newlines() -> None:
    for relative in (
        "tools/render-probe/probe_dict_call_reuse.py",
        "tools/render-probe/probe_render_features.py",
    ):
        tree = ast.parse((PROJECT_ROOT / relative).read_text(encoding="utf-8"))
        missing = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr != "write_text" or not node.args:
                continue
            if not isinstance(node.args[0], ast.Call):
                continue
            if not (isinstance(node.args[0].func, ast.Attribute) and node.args[0].func.attr == "dumps"):
                continue
            if not any(kw.arg == "newline" and isinstance(kw.value, ast.Constant) and kw.value.value == "\n"
                       for kw in node.keywords):
                missing.append(node.lineno)
        assert not missing, f"{relative} 的 JSON 写盘未固定 LF：{missing}"
