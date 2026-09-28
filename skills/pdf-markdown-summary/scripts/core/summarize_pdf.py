#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Prepare PDF assets for Agent-written summaries.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime
from typing import List, Optional

_scripts_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare PDF text and figure assets for summary writing.")
    parser.add_argument("--pdf", required=True, help="Path to the source PDF")
    parser.add_argument("--preset", default="robust", choices=["robust"])
    parser.add_argument("--allow-continued", action="store_true", default=False, help="Allow repeated-caption continuation items; structurally matched captionless table pages are recovered automatically")
    parser.add_argument("--out-dir", default=None, help="Output image directory")
    parser.add_argument("--text-path", default=None, help="Prepared plain-text path")
    parser.add_argument(
        "--reuse-existing",
        action="store_true",
        help="Reuse an existing index.json and text file instead of extracting again",
    )
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    pdf_path = os.path.abspath(args.pdf)
    if not os.path.exists(pdf_path):
        print(f"PDF not found: {pdf_path}", file=sys.stderr)
        return 1

    pdf_dir = os.path.dirname(pdf_path)
    stem = os.path.splitext(os.path.basename(pdf_path))[0]
    out_dir = os.path.abspath(args.out_dir or os.path.join(pdf_dir, "images"))
    text_path = os.path.abspath(args.text_path or os.path.join(pdf_dir, "text", stem + ".txt"))

    if args.reuse_existing:
        missing = [
            path
            for path in (os.path.join(out_dir, "index.json"), text_path)
            if not os.path.exists(path)
        ]
        if missing:
            print(f"Cannot reuse summary assets; missing: {', '.join(missing)}", file=sys.stderr)
            return 1
        # 存在性不够：默认 out_dir 是 <pdf_dir>/images，同目录放第二份 PDF 时
        # 上一份的 index.json 依然「存在」，会被静默当成当前 PDF 的产物复用。
        # 用 index.json 里记录的源 PDF 名核对，串档时直接报错而不是给出
        # 属于另一篇文档的文本与图片。
        index_path = os.path.join(out_dir, "index.json")
        try:
            with open(index_path, "r", encoding="utf-8") as fh:
                index_data = json.load(fh)
            if not isinstance(index_data, dict) or not isinstance(index_data.get("meta"), dict):
                raise ValueError("index.json 缺少有效的 meta 对象")
            index_meta = index_data["meta"]
        except (OSError, ValueError, TypeError) as exc:
            print(f"Cannot reuse summary assets; unreadable {index_path}: {exc}", file=sys.stderr)
            return 1
        indexed_pdf = index_meta.get("pdf")
        current_pdf = os.path.basename(pdf_path)
        if indexed_pdf != current_pdf:
            print(
                f"Refusing to reuse assets of another PDF: {index_path} was built from "
                f"'{indexed_pdf}', not '{current_pdf}'. Use --out-dir to separate them, "
                f"or drop --reuse-existing.",
                file=sys.stderr,
            )
            return 1
        indexed_hash = index_meta.get("pdf_hash")
        if not isinstance(indexed_hash, str) or not indexed_hash.startswith("sha256:"):
            print(f"Cannot reuse summary assets; missing PDF hash in {index_path}", file=sys.stderr)
            return 1
        expected_digest = indexed_hash.removeprefix("sha256:")
        if len(expected_digest) != 16 or any(ch not in "0123456789abcdef" for ch in expected_digest):
            print(f"Cannot reuse summary assets; invalid PDF hash in {index_path}", file=sys.stderr)
            return 1
        hasher = hashlib.sha256()
        try:
            with open(pdf_path, "rb") as fh:
                for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                    hasher.update(chunk)
        except OSError as exc:
            print(f"Cannot reuse summary assets; unreadable PDF {pdf_path}: {exc}", file=sys.stderr)
            return 1
        if hasher.hexdigest()[:16] != expected_digest:
            print(f"Refusing to reuse assets from a different PDF revision: {index_path}", file=sys.stderr)
            return 1
    else:
        from core.extract_pdf_assets import main as extract_main

        extraction_args = [
            "--pdf", pdf_path,
            "--preset", args.preset,
            "--out-dir", out_dir,
            "--out-text", text_path,
        ]
        if args.allow_continued:
            extraction_args.append("--allow-continued")

        exit_code = extract_main(extraction_args)
        if exit_code != 0:
            return exit_code

    today = datetime.now().strftime("%Y%m%d")
    print("Summary assets prepared.")
    print(f"Read text: {text_path}")
    print(f"Inspect images: {out_dir}")
    print(f"Suggested summary: {os.path.join(pdf_dir, stem + '_阅读摘要-' + today + '.md')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
