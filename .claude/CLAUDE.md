# pdfdol - Data Object Layer for PDF

Dict-like access to PDF files and universal format conversion to PDF.

## Package Structure

```
pdfdol/
  base.py      # PDF store classes: PdfFilesReader, PdfTextReader
  tools.py     # Conversion: get_pdf, any_to_pdf_bytes, concat_pdfs
  download.py  # Download PDFs from markdown: download_articles
  util.py      # Utilities
```

## Key Functions

- `PdfFilesReader(folder)` — dict-like access to PDF files (key=name, value=pages)
- `get_pdf(source, egress=...)` — convert anything to PDF
- `concat_pdfs(pdf_sources)` — merge multiple PDFs into one
- `download_articles(md_string)` — download PDFs from markdown links
- `pdf_to_title(pdf_bytes)` — extract title from PDF metadata

## Dependencies

Core: `dol`, `pypdf`, `markdown`, `pdfkit`, `requests`.
Optional: Calibre's ebook-convert for 30+ ebook/document formats.
