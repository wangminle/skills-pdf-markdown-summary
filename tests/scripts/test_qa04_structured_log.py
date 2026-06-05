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

from lib.extraction_logger import configure_logging, log_event


def test_log_event_writes_jsonl() -> None:
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


def main() -> int:
    tests = [test_log_event_writes_jsonl]
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