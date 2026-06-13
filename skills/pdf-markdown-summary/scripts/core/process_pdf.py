#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Run combined PDF-to-Markdown and summary-preparation workflows.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import sys
from typing import List, Optional

_scripts_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _scripts_dir not in sys.path:
    sys.path.insert(0, _scripts_dir)


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Convert a PDF to Markdown and prepare summary assets.")
    parser.add_argument("--pdf", required=True, help="Path to the source PDF")
    parser.add_argument("--out", default=None, help="Output Markdown path")
    parser.add_argument("--asset-dir", default="images", help="Image asset directory")
    parser.add_argument("--preset", default="robust", choices=["robust"])
    parser.add_argument("--allow-continued", action="store_true", default=False)
    parser.add_argument("--ocr", choices=["off", "auto", "force"], default="off")
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    pdf_path = os.path.abspath(args.pdf)
    if not os.path.exists(pdf_path):
        print(f"PDF not found: {pdf_path}", file=sys.stderr)
        return 1

    markdown_main = _load_sibling_main("pdf_to_markdown.py", "_pdf_to_markdown_core_for_process")
    summary_main = _load_sibling_main("summarize_pdf.py", "_summarize_pdf_core_for_process")

    markdown_args = [
        "--pdf",
        pdf_path,
        "--asset-dir",
        args.asset_dir,
        "--images",
        "figures",
        "--tables",
        "screenshot",
        "--preset",
        args.preset,
        "--ocr",
        args.ocr,
    ]
    if args.out:
        markdown_args.extend(["--out", args.out])
    if args.allow_continued:
        markdown_args.append("--allow-continued")

    markdown_exit = markdown_main(markdown_args)
    if markdown_exit != 0:
        return markdown_exit

    pdf_dir = os.path.dirname(pdf_path)
    stem = os.path.splitext(os.path.basename(pdf_path))[0]
    out_md = os.path.abspath(args.out or os.path.join(pdf_dir, f"{stem}.md"))
    out_dir = os.path.dirname(out_md)
    asset_dir = args.asset_dir
    if not os.path.isabs(asset_dir):
        asset_dir = os.path.join(out_dir, asset_dir)

    summary_args = [
        "--pdf", pdf_path,
        "--preset", args.preset,
        "--out-dir", os.path.abspath(asset_dir),
        "--text-path", os.path.join(out_dir, "text", f"{stem}.txt"),
        "--reuse-existing",
    ]
    if args.allow_continued:
        summary_args.append("--allow-continued")

    return summary_main(summary_args)


def _load_sibling_main(filename: str, module_name: str):
    core_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), filename)
    spec = importlib.util.spec_from_file_location(module_name, core_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to load core module: {core_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.main


if __name__ == "__main__":
    raise SystemExit(main())
