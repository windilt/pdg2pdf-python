# PDG to PDF Converter (Python Edition)

[English](README.md) | [中文](README_cn.md)

A high-performance Python-based converter for Chaoxing (SuperStar) **PDG** format e-books into standard **PDF** documents. 

Supports direct `.zip` archive processing, exact 00H/02H format decoding, intelligent reading-order page sorting, metadata extraction, and hierarchical table-of-contents (TOC) bookmarks generation.

> **Attribution**: This project is modified and enhanced from [bj5/pdg2pdf_open](https://github.com/bj5/pdg2pdf_open). New features include batch directory scanning & conversion, multi-threaded acceleration, resume/skip-existing, an expanded built-in password library (~700 common passwords), automatic virtual environment loading, and broader image page format support (PNG/JPG/BMP).

---

## Key Features

1. **Flexible Input Formats**:
   - Direct support for `.zip` archives (streams files without manual extraction)
   - Support for folders containing `.pdg` files
   - Support for single `.pdg` files

2. **Precise & Lossless 00H / 02H Decoding**:
   - Completely eliminates decoding artifacts such as horizontal black bars, distorted lines, and half-corrupted pages.
   - Built-in WebAssembly engine supporting XTEA-variant decryption and proprietary 2D CCITT run-length decoding for 00H/02H formats.
   - Converts pages into standard **ITU-T CCITT Group 4 (Fax T.6) TIFF** and embeds them directly via `img2pdf` for zero quality loss and minimal file size.

3. **Intelligent Page Sorting**:
   - Automatically orders pages according to the standard SuperStar reading sequence:
     $$\text{Front Cover (!00001/cov)} \rightarrow \text{Title (bok)} \rightarrow \text{Copyright (leg)} \rightarrow \text{Preface (fow/pre)} \rightarrow \text{TOC (dir/toc)} \rightarrow \text{Main Body (000001..)} \rightarrow \text{Appendix (att)} \rightarrow \text{Back Cover (!00002/bac)}$$

4. **Metadata & Hierarchical Bookmark (TOC) Generation**:
   - Automatically extracts book title, author, and publication date from `bookinfo.dat` and injects them into PDF metadata.
   - Decompresses and parses `BookContents.dat` (zlib-compressed outline) to generate a fully clickable, multi-level PDF bookmark outline tree accurately mapped to the main content pages.

5. **Blazing Fast Performance**:
   - Converts a full 500+ page book in approximately 10–12 seconds.

---

## Installation

Install the required dependencies:

```bash
pip install -r requirements.txt
```

Or install them directly:

```bash
pip install pillow img2pdf pikepdf tqdm wasmtime
```

---

## Usage

### Command Line Interface (CLI)

```bash
# 1. Convert a single ZIP archive
python pdg2pdf.py "book.zip"

# 2. Specify custom output path
python pdg2pdf.py "book.zip" -o "output.pdf"

# 3. Convert a directory containing PDG files
python pdg2pdf.py ./book_folder/ -o output.pdf

# 4. Specify custom rendering DPI (default: 200)
python pdg2pdf.py "book.zip" --dpi 300

# 5. Batch convert all ZIP files to an output directory
python pdg2pdf.py *.zip -o ./output/

# 6. Batch convert an entire folder of books (-b)
python pdg2pdf.py -b ./my_books/ -o ./output/

# 7. Batch convert recursively (-r) and skip already converted PDFs (-s)
python pdg2pdf.py -b ./my_books/ -r -s -o ./output/

# 8. Batch convert with multi-threading acceleration (-w 4)
python pdg2pdf.py -b ./my_books/ -w 4 -o ./output/
```

### Python API

```python
# 1. Single Book Conversion
from pdg2pdf import PdgConverter

converter = PdgConverter("book.zip", output_path="output.pdf", dpi=200)
pdf_path = converter.convert()
print("Generated PDF:", pdf_path)

# 2. Batch Conversion
from pdg2pdf import batch_convert

result = batch_convert(
    inputs="./my_books/",       # Path, list of files, or glob pattern
    output_dir="./output_pdf/", # Target output folder
    dpi=200,
    recursive=True,             # Scan subdirectories recursively
    skip_existing=True,         # Skip existing PDFs (resume interrupted tasks)
    workers=4,                  # Concurrent worker threads
)

print(f"Success: {len(result.succeeded)} | Failed: {len(result.failed)}")
```

---

## Project Structure

```text
pdg2pdf_open/
├── pdg2pdf.py          # Core converter script
├── pypdg2pic.py        # Module entry alias
├── pdg-decoder.wasm    # Dedicated WebAssembly PDG decoder engine
├── requirements.txt    # Python dependencies
├── README.md           # English documentation
└── README_cn.md        # Chinese documentation
```

---

## License

This project is licensed under the [MIT License](LICENSE).
