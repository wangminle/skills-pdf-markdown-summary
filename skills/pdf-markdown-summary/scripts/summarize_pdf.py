#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Thin wrapper for the PDF summary preparation CLI."""

from __future__ import annotations

import importlib.util
import os
import sys


def _load_main():
    core_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "core", "summarize_pdf.py")
    spec = importlib.util.spec_from_file_location("_summarize_pdf_core", core_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to load core module: {core_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.main


if __name__ == "__main__":
    raise SystemExit(_load_main()(sys.argv[1:]))
