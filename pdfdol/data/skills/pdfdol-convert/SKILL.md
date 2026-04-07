---
name: pdfdol-convert
description: >
  Convert files, URLs, or raw content to PDF using pdfdol.
  Use this skill whenever the user wants to convert documents to PDF format --
  including EPUB, MOBI, DOCX, ODT, HTML, Markdown, images, URLs, or any other
  file format to PDF. Also use when the user asks about what formats can be
  converted to PDF, wants to register custom format converters, or needs to
  check whether Calibre/ebook-convert is available. Triggers on: "convert to
  pdf", "make a pdf from", "epub to pdf", "save as pdf", "export to pdf",
  "pdf from url", "screenshot to pdf", "image to pdf", "docx to pdf".
---

# Converting Sources to PDF with pdfdol

Install: `pip install pdfdol`

## The Main Entry Point: `get_pdf`

`get_pdf(src, egress=None, *, src_kind=None)` is the universal converter.
It auto-detects the source type and returns PDF bytes (or saves to file).

```python
from pdfdol import get_pdf

# Auto-detected from file extension
pdf_bytes = get_pdf("report.html")
pdf_bytes = get_pdf("photo.png")
pdf_bytes = get_pdf("book.epub")       # requires Calibre

# Explicit source kind
pdf_bytes = get_pdf("https://example.com", src_kind="url")
pdf_bytes = get_pdf("<h1>Hello</h1>", src_kind="html")
pdf_bytes = get_pdf("# Title\nBody", src_kind="markdown")

# Save to file (egress controls output)
get_pdf("book.epub", egress="book.pdf")

# Apply a function to the result
reader = get_pdf("doc.html", egress=pypdf.PdfReader)
```

### Source kinds

| `src_kind` | Input | Detection heuristic |
|------------|-------|---------------------|
| `"url"` | URL string | Starts with `http://` or `https://` |
| `"html"` | HTML string | Contains `<html` |
| `"text"` | Plain text string | Fallback for non-file strings |
| `"file"` | Path to HTML file | Existing file with `.html`/`.htm`/`.xhtml` ext |
| `"image"` | Image path or bytes | Existing file with image extension, or image bytes |
| `"markdown"` / `"md"` | Markdown string or file | `.md`/`.markdown` extension |
| `"ebook"` | Ebook/document file | `.epub`, `.mobi`, `.docx`, etc. (requires Calibre) |

Auto-detection works well -- you rarely need to specify `src_kind` explicitly.
Only set it when passing raw strings that could be ambiguous (HTML content that
isn't a file, markdown that isn't a file).

### Egress: controlling output

| `egress` value | Behavior | Returns |
|----------------|----------|---------|
| `None` (default) | Return raw bytes | `bytes` |
| `"path/to/out.pdf"` | Write bytes to file | filepath `str` |
| `callable` | Apply function to bytes | whatever the callable returns |

## Ebook & Document Conversion (Calibre)

For EPUB, MOBI, DOCX, ODT, DJVU, RTF, and 30+ other formats, pdfdol
delegates to Calibre's `ebook-convert` CLI tool.  Calibre is **not** a
Python dependency -- it's auto-detected at runtime.

```python
from pdfdol import find_ebook_convert, ebook_convert_to_pdf

# Check availability
path = find_ebook_convert()   # returns binary path or None

# Convert from file path
pdf_bytes = ebook_convert_to_pdf("book.epub")

# Convert from bytes (extension hint required)
pdf_bytes = ebook_convert_to_pdf(epub_bytes, extension=".epub")
```

If Calibre is not installed and the user tries to convert an ebook format,
`FileNotFoundError` is raised with install instructions.

**Installing ebook-convert:**

| Platform | Command |
|----------|---------|
| macOS | `brew install --cask calibre` |
| Debian/Ubuntu | `sudo apt install calibre` |
| Fedora/RHEL | `sudo dnf install calibre` |
| Linux servers | `sudo -v && wget -nv -O- https://download.calibre-ebook.com/linux-installer.sh \| sudo sh` |

The Linux CLI installer is self-contained (no GUI needed) -- recommended for servers.

### Calibre-extended formats

Ebooks: `.epub`, `.mobi`, `.azw`, `.azw3`, `.azw4`, `.kepub`, `.fb2`, `.fbz`,
`.lit`, `.lrf`, `.pdb`, `.pml`, `.pmlz`, `.prc`, `.rb`, `.snb`, `.tcr`

Documents: `.docx`, `.docm`, `.odt`, `.rtf`

Comics: `.cb7`, `.cbc`, `.cbr`, `.cbz`

Academic: `.djvu`, `.djv`

Other: `.htmlz`, `.opf`, `.textile`, `.txtz`, `.chm`, `.pobi`, `.updb`

## Natively Supported Formats

These work without Calibre (only need `wkhtmltopdf` for HTML/URL, and
`img2pdf` or `Pillow` for images):

- **Images**: `.png`, `.jpg`, `.jpeg`, `.bmp`, `.gif`, `.tiff`, `.webp`
- **Markup**: `.html`, `.htm`, `.md`, `.markdown`
- **PDF**: `.pdf` (pass-through)
- **Other**: URLs, raw HTML strings, raw text strings

## Format Converter Registry

pdfdol has a pluggable format converter registry.  Each converter is a function
`(source: str | bytes) -> bytes` that takes a file path or raw content and
returns PDF bytes.

```python
from pdfdol import (
    supported_extensions,
    get_format_converter,
    register_format_converter,
)

# What's currently supported?
print(supported_extensions())
# ('.bmp', '.gif', '.htm', '.html', '.jpg', '.jpeg', '.md', '.markdown',
#  '.pdf', '.png', '.tiff', '.webp', ... plus Calibre formats if installed)

# Look up a converter
converter = get_format_converter(".epub")  # returns callable or None

# Register a custom converter
def rst_to_pdf(source):
    """Convert reStructuredText to PDF bytes."""
    if isinstance(source, bytes):
        source = source.decode("utf-8")
    # ... your conversion logic ...
    return pdf_bytes

register_format_converter(".rst", rst_to_pdf)
```

After registration, the new format works automatically with `get_pdf`,
`any_to_pdf_bytes`, `key_and_value_to_pdf_bytes`, and `concat_pdfs`.

## Convenience Wrapper: `any_to_pdf_bytes`

If you always want bytes back (no egress logic), use `any_to_pdf_bytes`:

```python
from pdfdol import any_to_pdf_bytes

pdf_bytes = any_to_pdf_bytes("page.html")
pdf_bytes = any_to_pdf_bytes(image_bytes, src_kind="image")
```

It also short-circuits: if the input is already PDF bytes, it returns them
unchanged.

## System Dependencies

| Dependency | Required for | Install |
|------------|-------------|---------|
| `wkhtmltopdf` | HTML, URL, text -> PDF (via pdfkit) | https://wkhtmltopdf.org/ |
| Calibre | EPUB, MOBI, DOCX, and other ebook/doc formats | https://calibre-ebook.com/download |
| `img2pdf` or `Pillow` | Image -> PDF (at least one recommended) | `pip install img2pdf` or `pip install Pillow` |
