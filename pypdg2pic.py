#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pyPdg2Pic 兼容模块与别名入口
基于 https://github.com/bj5/pdg2pdf_open 修改与增强
"""
from pdg2pdf import (
    PdgConverter,
    PdgPage,
    PdgDecoderSession,
    parse_pdg_bytes,
    parse_bookinfo,
    parse_bookcontents,
    scan_book_targets,
    resolve_output_path,
    batch_convert,
    BatchResult,
    BatchItemResult,
    main,
)

__all__ = [
    "PdgConverter",
    "PdgPage",
    "PdgDecoderSession",
    "parse_pdg_bytes",
    "parse_bookinfo",
    "parse_bookcontents",
    "scan_book_targets",
    "resolve_output_path",
    "batch_convert",
    "BatchResult",
    "BatchItemResult",
    "main",
]

if __name__ == "__main__":
    main()
