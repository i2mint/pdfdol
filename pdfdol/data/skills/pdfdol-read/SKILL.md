---
name: pdfdol-read
description: >
  Read, extract text from, and process PDF files using pdfdol.
  Use this skill whenever the user wants to extract text from PDFs, read PDF
  metadata (title, author), access a folder of PDFs as a dict-like store,
  concatenate or merge multiple PDFs, or do batch PDF operations. Triggers on:
  "extract text from pdf", "read pdf", "pdf to text", "get pdf title",
  "merge pdfs", "combine pdfs", "concatenate pdfs", "pdf metadata",
  "pdf folder", "pdf store", "batch pdf".
---

# Reading and Processing PDFs with pdfdol

Install: `pip install pdfdol`

## Reading PDFs as a Dict-Like Store

`PdfFilesReader` gives a `dict`-like interface to a folder of PDF files.
Keys are filenames (without `.pdf`), values are lists of page texts.

```python
from pdfdol import PdfFilesReader

pdfs = PdfFilesReader("/path/to/folder")

# List available PDFs
list(pdfs)
# ['report_2024', 'invoice_march', 'paper_draft']

# Read one -- value is a list of strings, one per page
pages = pdfs['report_2024']
print(pages[0])  # first page text
```

### Getting full text instead of page lists

Use `PdfTextReader` for concatenated text (pages joined by a separator):

```python
from pdfdol.base import PdfTextReader

pdfs = PdfTextReader("/path/to/folder")
full_text = pdfs['report_2024']  # single string with all pages
```

Or add a decoder to an existing `PdfFilesReader`:

```python
from dol import add_decoder

page_sep = '\n\n---\n\n'
pdfs = add_decoder(PdfFilesReader(folder), decoder=page_sep.join)
```

## Extracting Text from PDF Bytes

When you have PDF content as bytes (from a download, database, API, etc.):

```python
from pdfdol import pdf_bytes_to_text_pages, pdf_bytes_to_text

# Get a list of page strings
pages = list(pdf_bytes_to_text_pages(pdf_bytes))

# Get all text as one string
text = pdf_bytes_to_text(pdf_bytes)
```

## PDF Metadata

```python
from pdfdol.tools import pdf_to_title, pdf_to_metadata

# Extract title (returns None if not set)
title = pdf_to_title("document.pdf")
title = pdf_to_title(pdf_bytes)

# Extract full metadata dict
meta = pdf_to_metadata("document.pdf")
# {'Title': '...', 'Author': '...', 'Subject': '...', ...}
```

All metadata functions accept a file path (`str`), raw `bytes`, or a
`pypdf.PdfReader` object.

## Concatenating PDFs

`concat_pdfs` merges multiple PDFs (and images) into one.

### From a folder

```python
from pdfdol import concat_pdfs

# Merge all PDFs in a folder, return bytes
pdf_bytes = concat_pdfs("/path/to/folder", filter_extensions=True)

# Save to a file
concat_pdfs("/path/to/folder", save_filepath="combined.pdf",
            filter_extensions=True, key_order=sorted)
```

### From a dict-like store

```python
from dol import Files
from pdfdol import concat_pdfs

store = Files("/path/to/folder")
pdf_bytes = concat_pdfs(store, filter_extensions=True, key_order=sorted)
```

### From a list of PDF bytes

```python
from pdfdol.tools import concat_pdf_bytes

combined = concat_pdf_bytes([pdf1_bytes, pdf2_bytes, pdf3_bytes])
```

### Ordering and filtering

```python
# Sort alphabetically
concat_pdfs(store, key_order=sorted)

# Custom sort (e.g. by numeric prefix)
concat_pdfs(store, key_order=lambda k: int(k.split('_')[0]))

# Explicit order
concat_pdfs(store, key_order=['intro.pdf', 'chapter1.pdf', 'appendix.pdf'])

# Only include PDFs and images (skip .txt, .docx, etc.)
concat_pdfs(store, filter_extensions=True)

# Skip files that fail to convert (instead of raising)
concat_pdfs(store, skip_errors=True)
```

`filter_extensions=True` keeps: `.pdf`, `.png`, `.jpg`, `.jpeg`, `.bmp`,
`.gif`, `.tiff`.  Images are automatically converted to PDF pages before
merging.

### Save behavior

| `save_filepath` | Behavior |
|-----------------|----------|
| `False` (default) | Return combined PDF as bytes |
| `True` | Auto-name from source folder, save, return path |
| `"path/to/out.pdf"` | Save to specified path, return path |

## Utility Functions

```python
from pdfdol.util import remove_empty_pages

# Remove pages with little/no text
remove_empty_pages("input.pdf", "cleaned.pdf")
```

## Building Custom Pipelines

pdfdol uses `dol.Pipe` for composable transformations.  You can build
custom read pipelines:

```python
from dol import Pipe
from pdfdol.base import bytes_to_pdf_reader_obj, pdf_reader_to_text_pages

# Custom pipeline: bytes -> reader -> text pages -> uppercased
my_reader = Pipe(
    bytes_to_pdf_reader_obj,
    pdf_reader_to_text_pages,
    lambda pages: [p.upper() for p in pages],
)

upper_pages = my_reader(pdf_bytes)
```

## Quick Reference

| Task | Function |
|------|----------|
| Folder of PDFs as dict | `PdfFilesReader(folder)` |
| Folder of PDFs as text | `PdfTextReader(folder)` |
| Bytes to page list | `pdf_bytes_to_text_pages(b)` |
| Bytes to full text | `pdf_bytes_to_text(b)` |
| Get title | `pdf_to_title(src)` |
| Get all metadata | `pdf_to_metadata(src)` |
| Merge PDFs | `concat_pdfs(source, save_filepath=...)` |
| Merge PDF bytes | `concat_pdf_bytes([b1, b2])` |
| Remove empty pages | `remove_empty_pages(in_path, out_path)` |
