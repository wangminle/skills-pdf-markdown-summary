#!/usr/bin/env python3
"""
QA-04 回归：结构化日志 run.log.jsonl

验证点：
1) configure_logging 设置 log_jsonl 后，_JSONL_FILE 路径被正确记录
2) log_event() 能将结构化事件写入 JSONL 文件
3) JSONL 文件每行都是有效 JSON 且包含 event 字段
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

# 项目根目录：tests/scripts/ -> 向上三级
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SCRIPTS_DIR = os.path.join(PROJECT_ROOT, "skills", "pdf-markdown-summary", "scripts")
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

import lib.extraction_logger as extraction_logger
from lib.extraction_logger import configure_logging, log_event


def test_log_event_writes_jsonl() -> None:
    # 保存模块级全局状态，测试结束后还原（configure_logging 不会清理
    # 已设置的 _JSONL_FILE，需直接还原模块全局变量）
    old_jsonl_file = extraction_logger._JSONL_FILE
    old_run_id = extraction_logger._RUN_ID
    try:
        with tempfile.TemporaryDirectory() as td:
            log_path = Path(td) / "images" / "run.log.jsonl"
            log_path.parent.mkdir(parents=True, exist_ok=True)

            run_id = configure_logging(
                level="INFO",
                log_jsonl=str(log_path),
            )

            # 写入结构化事件
            log_event("run_start", pdf="test.pdf", preset="robust")
            log_event("figure_extracted", figure_id="1", page=2)
            log_event("run_end", figures=1, tables=0)

            # 验证文件存在且非空
            assert log_path.exists(), f"run.log.jsonl 未生成: {log_path}"
            content = log_path.read_text(encoding="utf-8").strip()
            assert content, "run.log.jsonl 内容为空"

            # 验证每行是有效 JSON
            lines = [l for l in content.splitlines() if l.strip()]
            assert len(lines) >= 3, f"应有至少 3 行事件日志，实际 {len(lines)} 行"

            events = []
            for line in lines:
                data = json.loads(line)
                assert "event" in data, f"日志行应包含 event 字段"
                events.append(data["event"])

            assert "run_start" in events, f"缺少 run_start 事件: {events}"
            assert "run_end" in events, f"缺少 run_end 事件: {events}"
    finally:
        # 还原日志模块全局状态，避免泄漏到其他测试
        extraction_logger._JSONL_FILE = old_jsonl_file
        extraction_logger._RUN_ID = old_run_id


def test_run_end_always_written_even_when_no_fallback() -> None:
    """端到端回归：验收门收紧后零回退时 run.log.jsonl 不得静默为空。

    BUG-047 起 run.log.jsonl 只在「精修被拒回退」时产生事件；BUG-085 把
    图路径验收门收紧为 not polluted 后，干净资产全部直接通过，回退类
    事件数为 0，run.log.jsonl 变成 0 字节——「零回退」与「日志系统坏了」
    无法区分（V0.6.4 的 20260928-045 批次 8/8 空文件即此症状）。
    main_modular 收尾必须无条件写一条带 figures/tables 统计的 run_end。
    """
    import importlib.util

    core_path = Path(SCRIPTS_DIR) / "core" / "extract_pdf_assets.py"
    spec = importlib.util.spec_from_file_location("_qa04_core", core_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    old_jsonl_file = extraction_logger._JSONL_FILE
    old_run_id = extraction_logger._RUN_ID
    try:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            pdf_path = root / "paper.pdf"
            _make_text_only_pdf(pdf_path)

            out_dir = root / "images"
            exit_code = module.main_modular(
                [
                    "--pdf", str(pdf_path),
                    "--out-dir", str(out_dir),
                    "--out-text", str(root / "paper.txt"),
                ]
            )
            assert exit_code == 0, f"extract_pdf_assets 应成功，实际 exit={exit_code}"

            log_path = out_dir / "run.log.jsonl"
            assert log_path.exists(), f"run.log.jsonl 未生成: {log_path}"
            content = log_path.read_text(encoding="utf-8").strip()
            assert content, (
                "run.log.jsonl 为空：纯文本 PDF 无资产零回退，"
                "run_end 必须无条件写入以区分「零回退」与「日志系统坏了」"
            )

            events = []
            for line in content.splitlines():
                data = json.loads(line)
                assert "event" in data
                events.append(data["event"])
            assert "run_end" in events, f"缺少 run_end 事件: {events}"

            # 统计字段必须存在且与 index.json 对得上（kwargs 落在 details 子字典）
            end_events = [
                json.loads(line)
                for line in content.splitlines()
                if json.loads(line).get("event") == "run_end"
            ]
            ev = end_events[-1]
            details = ev.get("details") or {}
            assert "figures" in details and "tables" in details, (
                f"run_end 应带 figures/tables 统计: {ev}"
            )
            assert details["figures"] == 0 and details["tables"] == 0, (
                f"纯文本 PDF 应统计为 0/0: {ev}"
            )
    finally:
        extraction_logger._JSONL_FILE = old_jsonl_file
        extraction_logger._RUN_ID = old_run_id


def test_run_end_counts_match_index_json() -> None:
    """端到端回归：run_end 的 figures/tables 统计必须与实际提取结果一致。

    run_end 统计曾误用 getattr(r, "type")，而 AttachmentRecord 只有 kind
    字段，导致带资产的 PDF 也永远记 0/0——「顺带核对数量的能力」静默失效。
    本用例用带图 PDF 对账 index.json，防止该错误回归。
    """
    import importlib.util

    core_path = Path(SCRIPTS_DIR) / "core" / "extract_pdf_assets.py"
    spec = importlib.util.spec_from_file_location("_qa04_core2", core_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    old_jsonl_file = extraction_logger._JSONL_FILE
    old_run_id = extraction_logger._RUN_ID
    try:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            pdf_path = root / "with_figure.pdf"
            _make_pdf_with_figure(pdf_path)

            out_dir = root / "images"
            exit_code = module.main_modular(
                [
                    "--pdf", str(pdf_path),
                    "--out-dir", str(out_dir),
                    "--out-text", str(root / "paper.txt"),
                ]
            )
            assert exit_code == 0, f"extract_pdf_assets 应成功，实际 exit={exit_code}"

            index_path = out_dir / "index.json"
            assert index_path.exists(), f"index.json 未生成: {index_path}"
            index = json.loads(index_path.read_text(encoding="utf-8"))
            expected_figures = len(index.get("figures") or [])
            expected_tables = len(index.get("tables") or [])
            assert expected_figures >= 1, (
                f"带图 PDF 应至少提取 1 张图，index.json 实际: "
                f"figures={expected_figures}, tables={expected_tables}"
            )

            log_path = out_dir / "run.log.jsonl"
            content = log_path.read_text(encoding="utf-8").strip()
            end_events = [
                json.loads(line)
                for line in content.splitlines()
                if json.loads(line).get("event") == "run_end"
            ]
            assert end_events, "缺少 run_end 事件"
            details = end_events[-1].get("details") or {}
            assert details.get("figures") == expected_figures, (
                f"run_end figures={details.get('figures')} 与 index.json "
                f"figures={expected_figures} 不一致: {end_events[-1]}"
            )
            assert details.get("tables") == expected_tables, (
                f"run_end tables={details.get('tables')} 与 index.json "
                f"tables={expected_tables} 不一致: {end_events[-1]}"
            )
    finally:
        extraction_logger._JSONL_FILE = old_jsonl_file
        extraction_logger._RUN_ID = old_run_id


def _make_pdf_with_figure(path: Path) -> None:
    """造一份带一张位图和题注的 PDF，确保至少提取出 1 个 figure 记录。"""
    import fitz

    doc = fitz.open()
    page = doc.new_page(width=600, height=500)
    page.insert_text((48, 60), "Paper body text above the figure.", fontsize=12)

    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 240, 160))
    pix.clear_with(200)
    img_rect = fitz.Rect(150, 120, 450, 280)
    page.insert_image(img_rect, pixmap=pix)
    page.insert_text((150, 305), "Figure 1: A sample embedded image.", fontsize=10)

    doc.save(path)
    doc.close()


def _make_text_only_pdf(path: Path) -> None:
    """造一份只有正文、无任何图表的 PDF（0 资产、0 回退）。"""
    import fitz

    doc = fitz.open()
    page = doc.new_page(width=420, height=320)
    page.insert_text((48, 72), "Plain text only, no figures or tables.", fontsize=12)
    page.insert_text((48, 96), "Second paragraph for good measure.", fontsize=12)
    doc.save(path)
    doc.close()


def main() -> int:
    tests = [
        test_log_event_writes_jsonl,
        test_run_end_always_written_even_when_no_fallback,
        test_run_end_counts_match_index_json,
    ]
    passed = 0
    failed = 0

    for t in tests:
        try:
            t()
            passed += 1
        except AssertionError as e:
            print(f"FAIL {t.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"ERROR {t.__name__}: {e}")
            failed += 1

    print(f"\n测试结果: {passed} 通过, {failed} 失败")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())