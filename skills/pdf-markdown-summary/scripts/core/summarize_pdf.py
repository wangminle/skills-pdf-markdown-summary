#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Prepare PDF assets for Agent-written summaries.
"""

from __future__ import annotations

import argparse
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
    parser.add_argument("--allow-continued", action="store_true", default=False)
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
