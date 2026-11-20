# 超星 PDG 转 PDF 工具 (Python 版)

[English](README.md) | [中文](README_cn.md)

基于 Python 实现的高性能超星（Chaoxing / SuperStar）PDG 格式转 PDF 工具。支持 ZIP 压缩包输入、00H/02H 高精度解码、自动页面顺序排序、元数据提取与多级目录大纲书签生成。

> **项目说明**：本项目是从 [bj5/pdg2pdf_open](https://github.com/bj5/pdg2pdf_open) 修改与增强而来，新增了批量目录扫描转换、多线程并发加速、断点续转（跳过已有 PDF）、超大内置常用密码库（近 700 条常用密码自动匹配）、虚拟环境依赖自动定位加载以及对多种页面格式（PNG/JPG/BMP 等）的兼容支持。

## 功能特性

1. **多格式直接输入**：
   - 支持 `.zip` 压缩包（直接流式读取，无需手动解压）
   - 支持包含 `.pdg` 文件的文件夹目录
   - 支持单个 `.pdg` 文件转换
2. **高精度无损解码 (00H / 02H)**：
   - 彻底解决普通解码出现的拉丝、花屏与黑色横条问题
   - 内嵌专用 WebAssembly 引擎，精准支持 00H/02H XTEA 变体解密与特有 CCITT 2D 游程码表还原
   - 转换为国际标准 ITU-T CCITT Group 4 (Fax T.6) TIFF 并经 `img2pdf` 无损封装进 PDF，体积超小且画质零损失
3. **智能页面排序**：
   - 按照超星书籍标准阅读顺序智能排序：
     封面 (`!00001` / `cov`) $\rightarrow$ 书名页 (`bok`) $\rightarrow$ 版权页 (`leg`) $\rightarrow$ 前言 (`fow` / `pre`) $\rightarrow$ 目录 (`dir` / `toc`) $\rightarrow$ 正文 (`000001`..) $\rightarrow$ 附录 (`att`) $\rightarrow$ 封底 (`!00002` / `bac`)
4. **元数据与多级目录大纲书签 (TOC / Outlines)**：
   - 自动解析 `bookinfo.dat` 中的书名、作者、出版日期等元数据写入 PDF
   - 自动解压并解析 `BookContents.dat`（zlib 压缩大纲），生成可点击的多级 PDF 目录大纲书签并精准对齐正文起始页
5. **极速转换**：
   - 500+ 页图书转换仅需 10~12 秒左右

## 安装依赖

```bash
pip install -r requirements.txt
```

或者手动安装：

```bash
pip install pillow img2pdf pikepdf tqdm wasmtime
```

## 使用方法

### 命令行使用 (CLI)

```bash
# 1. 单本转换：转换 ZIP 压缩包（默认在同目录下生成同名 PDF）
python pdg2pdf.py "book.zip"

# 2. 单本转换：指定输出 PDF 路径
python pdg2pdf.py "book.zip" -o "output.pdf"

# 3. 单本转换：转换包含 PDG 文件的目录
python pdg2pdf.py ./book_folder/ -o output.pdf

# 4. 指定渲染 DPI（默认 200）
python pdg2pdf.py "book.zip" --dpi 300

# 5. 批处理：批量转换当前目录下所有 ZIP 电子书并输出至指定目录
python pdg2pdf.py *.zip -o ./output/

# 6. 批处理：扫描图书目录（自动转换目录下所有 ZIP 与书籍子文件夹）
python pdg2pdf.py -b ./my_books/ -o ./output/

# 7. 批处理：递归扫描多层子目录 (-r) 与 断点续转跳过已有 PDF (-s)
python pdg2pdf.py -b ./my_books/ -r -s -o ./output/

# 8. 批处理：开启 4 线程并发加速转换 (-w 4)
python pdg2pdf.py -b ./my_books/ -w 4 -o ./output/
```

### Python 代码调用 (API)

```python
# 1. 单本图书转换
from pdg2pdf import PdgConverter

converter = PdgConverter("book.zip", output_path="output.pdf", dpi=200)
pdf_path = converter.convert()
print("PDF 已生成:", pdf_path)

# 2. 批量图书转换
from pdg2pdf import batch_convert

result = batch_convert(
    inputs="./my_books/",       # 支持目录、文件列表或通配符
    output_dir="./output_pdf/", # 输出目录
    dpi=200,
    recursive=True,             # 是否递归扫描子目录
    skip_existing=True,         # 跳过已存在的 PDF (断点续转)
    workers=4,                  # 并发工作线程数
)

print(f"转换成功: {len(result.succeeded)} 本 | 失败: {len(result.failed)} 本")
```

## License

MIT License
