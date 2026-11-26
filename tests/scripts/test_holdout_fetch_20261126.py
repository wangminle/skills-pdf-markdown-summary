# -*- coding: utf-8 -*-
"""Holdout 清单下载器的校验回归（2026-11-26，独立验收 CHK-098 发现）。

背景：download_document 原先先落盘再由 check_document 校验 sha256，下到坏包时文件已经
留在磁盘上；而脚本的规则是「已存在但对不上不覆盖」，下一次重试会永远卡在 mismatch。
现在清单已登记 sha256 时，内容先在临时文件上校验，一致才落盘；文档号与文件名会拼进
落盘路径，只能是单段名称。

守住的性质：
- 下载内容与清单 sha256 不符或不是 PDF 时不落盘，也不留临时文件，重试可以成功；
- 一致的下载正常落盘；已存在但对不上的文件原样保留并报 mismatch；
- 清单的文档号与文件名含路径分隔符时整份清单拒绝使用，不会发起下载；
- 绕过清单直调 check_document/download_document 时，同一约束在函数内兜底复验，
  非法条目既不读盘也不建目录，更不会把文件写到 Holdout 根目录之外。

网络响应全部用假的，不触网。
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
EVAL_DIR = PROJECT_ROOT / "tests" / "eval"
if str(EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(EVAL_DIR))

import fetch_holdout as fetch  # noqa: E402 - local script path is set above

RIGHT_BYTES = b"%PDF-1.4 the bytes the manifest was frozen with"
RIGHT_SHA = hashlib.sha256(RIGHT_BYTES).hexdigest()


class _FakeResponse:
    """最小的响应对象：读一次给出全部内容，再读返回空。"""

    def __init__(self, payload: bytes) -> None:
        self._chunks = [payload]

    def read(self, size: int = -1) -> bytes:
        return self._chunks.pop(0) if self._chunks else b""

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *exc) -> bool:
        return False


def _serve(monkeypatch, payload: bytes) -> None:
    monkeypatch.setattr(fetch.urllib.request, "urlopen", lambda request, timeout=None: _FakeResponse(payload))


def _entry(**overrides) -> dict:
    entry = {"id": "doc-a", "file": "doc-a.pdf", "url": "https://example.invalid/doc-a.pdf", "sha256": RIGHT_SHA}
    entry.update(overrides)
    return entry


def _write_manifest(tmp_path: Path, name: str, *entries: dict) -> Path:
    path = tmp_path / name
    path.write_text(json.dumps({"documents": list(entries)}), encoding="utf-8")
    return path


@pytest.mark.parametrize("payload, reason", [
    (b"%PDF-1.4 a corrupted or substituted download", "sha256 不符"),
    (b"<html>upstream returned an error page</html>", "不是 PDF"),
])
def test_failed_download_leaves_nothing_behind(tmp_path: Path, monkeypatch, payload: bytes, reason: str) -> None:
    _serve(monkeypatch, payload)

    with pytest.raises(ValueError, match=reason):
        fetch.download_document(_entry(), tmp_path)

    # 目标文件与临时文件都不留：下一次重试不会撞上「已存在但对不上」
    assert list((tmp_path / "doc-a").iterdir()) == []


def test_matching_download_is_placed(tmp_path: Path, monkeypatch) -> None:
    _serve(monkeypatch, RIGHT_BYTES)

    info = fetch.download_document(_entry(), tmp_path)

    assert (tmp_path / "doc-a" / "doc-a.pdf").read_bytes() == RIGHT_BYTES
    assert info == {"sha256": RIGHT_SHA, "bytes": len(RIGHT_BYTES)}
    assert fetch.check_document(_entry(), tmp_path) == "ok"


def test_retry_succeeds_after_a_bad_download(tmp_path: Path, monkeypatch) -> None:
    manifest = _write_manifest(tmp_path, "manifest.json", _entry())
    root = tmp_path / "holdout"

    _serve(monkeypatch, b"%PDF-1.4 bad download")
    assert fetch.main(["--manifest", str(manifest), "--root", str(root)]) == 1
    assert not (root / "doc-a" / "doc-a.pdf").exists()

    _serve(monkeypatch, RIGHT_BYTES)
    assert fetch.main(["--manifest", str(manifest), "--root", str(root)]) == 0
    assert fetch.check_document(_entry(), root) == "ok"


def test_existing_mismatched_file_is_kept_and_reported(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "holdout"
    target = root / "doc-a" / "doc-a.pdf"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"%PDF-1.4 the version someone left on disk")
    monkeypatch.setattr(fetch, "download_document", lambda *args, **kwargs: pytest.fail("对不上的文件不得被覆盖"))

    assert fetch.check_document(_entry(), root) == "mismatch"
    assert fetch.main(["--manifest", str(_write_manifest(tmp_path, "m.json", _entry())), "--root", str(root)]) == 1
    assert target.read_bytes() == b"%PDF-1.4 the version someone left on disk"


@pytest.mark.parametrize("bad", [
    {"id": "nested/doc-a"}, {"id": ".."}, {"file": "../doc-a.pdf"}, {"file": "sub\\doc-a.pdf"}, {"file": "C:doc-a.pdf"},
])
def test_manifest_rejects_ids_and_file_names_that_carry_a_path(tmp_path: Path, bad: dict) -> None:
    with pytest.raises(ValueError, match="含路径分隔符"):
        fetch.load_manifest(_write_manifest(tmp_path, "manifest.json", _entry(**bad)))


def test_unusable_manifest_stops_before_any_download(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(fetch, "download_document", lambda *args, **kwargs: pytest.fail("清单不可用时不得下载"))
    root = tmp_path / "holdout"

    assert fetch.main(["--manifest", str(_write_manifest(tmp_path, "manifest.json", _entry(id="../x"))),
                       "--root", str(root)]) == 1
    assert not root.exists()


@pytest.mark.parametrize("bad", [
    {"id": "nested/doc-a"},
    {"id": ".."},
    {"id": ""},
    {"file": "../doc-a.pdf"},
    {"file": "sub\\doc-a.pdf"},
    {"file": "C:doc-a.pdf"},
    {"file": "."},
])
def test_direct_entries_with_a_path_are_rejected_by_both_writers(tmp_path: Path, monkeypatch, bad: dict) -> None:
    """绕过 load_manifest 直调两个落盘函数时，路径字段仍要在函数内兜底复验。"""
    entry = _entry(**bad)
    monkeypatch.setattr(fetch.urllib.request, "urlopen", lambda *args, **kwargs: pytest.fail("非法条目不得发起下载"))

    with pytest.raises(ValueError, match="含路径分隔符"):
        fetch.check_document(entry, tmp_path)
    with pytest.raises(ValueError, match="含路径分隔符"):
        fetch.download_document(entry, tmp_path)

    # 既没有读盘探测，也没有先 mkdir 出半个目录
    assert list(tmp_path.iterdir()) == []


def test_real_manifest_names_are_plain() -> None:
    """版本化清单里的文档号与文件名都要能通过路径校验，否则整套重建入口直接失效。"""
    for entry in fetch.load_manifest():
        assert fetch._is_plain_name(entry["id"]) and fetch._is_plain_name(entry["file"])
