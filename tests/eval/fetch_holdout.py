#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""按清单重建冻结 Holdout 集（2026-11-26，Holdout 验收）。

- 清单：tests/eval/holdout_manifest.json（文档号、下载地址、sha256、来源页）；
- 每份 PDF 落在各自独立的目录 tests/holdout/<文档号>/<文件名>（该目录已
  gitignore，克隆后需在本机重建）；
- 已存在且 sha256 与清单一致的文件跳过；已存在但对不上的文件报错并保留，
  不覆盖——冻结集里的文件只能由人确认后手工替换；
- 清单已登记 sha256 时，下载内容先在临时文件上校验，一致才落盘：坏包不会
  留在磁盘上挡住下一次重试；清单尚未登记 sha256 时只校验 PDF 文件头，并把
  实际 sha256 打印出来供登记；
- 下载内容只按字节校验，不做任何解析或执行；
- 文档号与文件名会拼进落盘路径，只能是单段名称：清单入口与两个落盘函数
  （`download_document()` / `check_document()`）各自兜底校验，绕过清单直接
  构造条目调用也不会越出 Holdout 根目录。

用法：
    python3 tests/eval/fetch_holdout.py            # 下载缺失的文档
    python3 tests/eval/fetch_holdout.py --check    # 只校验，不下载（退出码 0=齐全一致）
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = REPO_ROOT / "tests" / "eval" / "holdout_manifest.json"
HOLDOUT_ROOT = REPO_ROOT / "tests" / "holdout"
USER_AGENT = "pdf-markdown-summary-holdout/0.6.15 (frozen regression set)"
DOWNLOAD_TIMEOUT_SECONDS = 180


def _is_plain_name(value: str) -> bool:
    """只是一个文件名或目录名：不含路径分隔符，不是当前目录、上级目录或绝对路径。"""
    return bool(value) and value not in (".", "..") and not any(ch in value for ch in ("/", "\\", ":", "\0"))


def _plain_entry_parts(entry: Dict[str, Any]) -> tuple[str, str]:
    """取出一份条目里会拼进落盘路径的文档号与文件名，并再次做单段名校验。

    ``load_manifest()`` 已在清单入口校验过，但 ``download_document()`` 与
    ``check_document()`` 是公开函数，外部代码可能绕过清单直接构造条目调用，
    因此两个落盘入口都要各自兜底，绝不能让文档号/文件名带出 Holdout 根目录。
    """
    doc_id = str(entry.get("id") or "")
    file_name = str(entry.get("file") or "")
    if not _is_plain_name(doc_id) or not _is_plain_name(file_name):
        raise ValueError(f"Holdout 条目的文档号或文件名含路径分隔符：{doc_id!r} / {file_name!r}")
    return doc_id, file_name


def load_manifest(path: Path = MANIFEST_PATH) -> List[Dict[str, Any]]:
    """读取清单并返回文档条目列表；缺字段、文档号重复或文档号与文件名带路径一律报错。"""
    with open(path, "r", encoding="utf-8") as handle:
        manifest = json.load(handle)
    documents = manifest.get("documents") if isinstance(manifest, dict) else None
    if not isinstance(documents, list) or not documents:
        raise ValueError(f"Holdout 清单没有 documents 条目：{path}")
    seen = set()
    for entry in documents:
        for key in ("id", "file", "url"):
            if not str(entry.get(key) or "").strip():
                raise ValueError(f"Holdout 清单条目缺少 {key}：{entry}")
        # 文档号与文件名会拼进落盘路径，只能是单段名称
        doc_id, _ = _plain_entry_parts(entry)
        if doc_id in seen:
            raise ValueError(f"Holdout 清单文档号重复：{doc_id}")
        seen.add(doc_id)
    return documents


def sha256_of_file(path: Path) -> str:
    """分块计算文件 sha256。"""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def check_document(entry: Dict[str, Any], root: Path = HOLDOUT_ROOT) -> str:
    """返回一份文档的状态：ok / missing / mismatch / empty / no-hash / bad-header。

    文档号与文件名在函数内重新校验：绕过 ``load_manifest()`` 直调本函数时同样拒绝
    带路径分隔符的条目，避免探到 Holdout 根目录之外。
    """
    doc_id, file_name = _plain_entry_parts(entry)
    target = root / doc_id / file_name
    if not target.is_file():
        return "missing"
    expected = str(entry.get("sha256") or "").strip().lower()
    if not expected:
        with open(target, "rb") as handle:
            head = handle.read(5)
        return "no-hash" if head == b"%PDF-" else "bad-header"
    if target.stat().st_size == 0:
        return "empty"
    return "ok" if sha256_of_file(target) == expected else "mismatch"


def download_document(entry: Dict[str, Any], root: Path = HOLDOUT_ROOT) -> Dict[str, Any]:
    """下载一份文档到各自独立的目录，返回实际 sha256 与字节数。

    内容先写同目录的临时文件，通过校验后才落盘：文件头必须是 PDF，清单已登记
    sha256 时还须与清单一致。任何一步失败都删掉临时文件，目标路径保持原样。
    """
    # 先校验路径字段再建目录：非法文档号一个字节都不应写到 Holdout 根目录外
    doc_id, file_name = _plain_entry_parts(entry)
    folder = root / doc_id
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / file_name
    if urllib.parse.urlparse(entry["url"]).scheme not in ("http", "https"):
        raise ValueError(f"只支持 http/https 地址：{entry['url']}")
    expected = str(entry.get("sha256") or "").strip().lower()
    request = urllib.request.Request(entry["url"], headers={"User-Agent": USER_AGENT})
    handle_fd, temp_name = tempfile.mkstemp(prefix=".download-", dir=str(folder))
    os.close(handle_fd)
    temp_path = Path(temp_name)
    try:
        with urllib.request.urlopen(request, timeout=DOWNLOAD_TIMEOUT_SECONDS) as response, open(
            temp_path, "wb"
        ) as output:
            first = True
            for chunk in iter(lambda: response.read(1024 * 1024), b""):
                if first:
                    if not chunk.startswith(b"%PDF-"):
                        raise ValueError(f"下载内容不是 PDF：{entry['url']}")
                    first = False
                output.write(chunk)
        if first:
            raise ValueError(f"下载内容为空：{entry['url']}")
        actual = sha256_of_file(temp_path)
        if expected and actual != expected:
            raise ValueError(f"下载内容与清单 sha256 不符（实际 {actual}）：{entry['url']}")
        temp_path.replace(target)
    except BaseException:
        temp_path.unlink(missing_ok=True)
        raise
    return {"sha256": actual, "bytes": target.stat().st_size}


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="按清单重建冻结 Holdout 集")
    parser.add_argument("--check", action="store_true", help="只校验不下载")
    parser.add_argument("--manifest", type=Path, default=MANIFEST_PATH, help="清单路径")
    parser.add_argument("--root", type=Path, default=HOLDOUT_ROOT, help="Holdout 根目录")
    args = parser.parse_args(argv)

    try:
        documents = load_manifest(args.manifest)
    except (OSError, ValueError) as exc:
        print(f"[失败] 无法使用清单 {args.manifest}: {exc}")
        return 1
    failures = 0
    for entry in documents:
        status = check_document(entry, args.root)
        if status in ("missing", "empty") and not args.check:
            try:
                info = download_document(entry, args.root)
            except Exception as exc:  # 下载失败不影响其余文档
                print(f"[失败] {entry['id']}: {exc}")
                failures += 1
                continue
            print(f"[下载] {entry['id']}: {info['bytes']} 字节 sha256={info['sha256']}")
            status = check_document(entry, args.root)
        if status == "ok":
            print(f"[齐全] {entry['id']}")
        elif status == "no-hash":
            print(f"[待登记] {entry['id']}: 清单无 sha256，实际 {sha256_of_file(args.root / entry['id'] / entry['file'])}")
        else:
            print(f"[异常] {entry['id']}: {status}")
            failures += 1
    print(f"共 {len(documents)} 份，异常 {failures} 份")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
