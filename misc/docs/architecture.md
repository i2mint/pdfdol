# pdfdol Architecture Notes

## Module Overview

| Module | Purpose |
|--------|---------|
| `__init__.py` | Public API re-exports |
| `base.py` | Core PDF reading: `PdfReader` wrappers, bytes-to-text pipelines, store wrappers (`PdfFilesReader`, `PdfTextReader`) |
| `tools.py` | Conversion engine: `get_pdf`, format converter registry, ebook-convert integration, metadata extraction, PDF concatenation |
| `util.py` | Small file-path and page utilities (`add_affix`, `remove_empty_pages`, etc.) |
| `examples/aggregations.py` | Higher-level image/document aggregation into PDFs |

## Key Design Patterns

### Pipeline Composition (`dol.Pipe`)
`base.py` builds transformations as composable `Pipe` chains:
```
bytes -> BytesIO -> PdfReader -> text_pages -> list -> joined_string
```
Each step is a standalone callable; `Pipe` composes them left-to-right.

### Store Abstraction (`dol`)
`PdfFilesReader` is a dict-like view over a folder of PDFs.  Built by applying
store wrappers (`wrap_kvs`, `KeyCodecs.suffixed`, `add_ipython_key_completions`)
to `dol.Files`.  Values are decoded on read (postget) -- no eager loading.

### Dual-Layer Conversion
- **High-level**: `get_pdf(src, egress, src_kind)` -- auto-detects source type,
  dispatches to the right converter, handles egress (return bytes / save file / apply callable).
- **Mid-level**: `any_to_pdf_bytes(src)` -- convenience wrapper returning bytes.
- **Low-level**: per-format functions (`pdfkit.from_*`, `markdown_to_pdf`,
  `_image_to_pdf_bytes`, `ebook_convert_to_pdf`).

### Format Converter Registry
Central dict `_format_converters` maps file extensions (`.epub`, `.png`, ...)
to converter callables.  Two access points:
- `register_format_converter(extensions, converter)` -- add/override entries.
- `get_format_converter(extension)` -- look up; falls back to ebook-convert
  for known extensions not in the dict.

Used by `key_and_value_to_pdf_bytes` (extension-based dispatch for batch
operations like `concat_pdfs`) and indirectly by `get_pdf` (via `_resolve_src_kind`).

### Source-Kind Dispatch (`get_pdf`)
`_resolve_src_kind(src)` heuristically maps input to a `SrcKind` literal:
`url | html | file | md | markdown | text | image | ebook`.
`get_pdf` uses a `func_for_kind` dict inside the function to dispatch.

## Terminology

| Term | Meaning in pdfdol |
|------|-------------------|
| **Source kind** (`SrcKind`) | High-level category of input: url, html, file, image, ebook, etc. |
| **Format converter** | Function `(str\|bytes) -> bytes` that converts a specific file format to PDF bytes |
| **Format converter registry** | The `_format_converters` dict + `register/get_format_converter` API |
| **Egress** | Output handler for PDF bytes: `None` (return bytes), `str` (write to filepath), or `callable` |
| **Store wrapper** | A `dol` transformer applied to a dict-like store to modify keys/values on access |

## Dependencies

**Required** (in `setup.cfg`): `dol`, `pypdf`, `markdown`, `pdfkit`

**System**: `wkhtmltopdf` (needed by pdfkit for HTML/URL/text -> PDF)

**Optional** (auto-detected at runtime):
- `weasyprint` -- preferred HTML-to-PDF renderer (over pdfkit) in `base.py`
- `img2pdf` -- optimal image-to-PDF (falls back to Pillow)
- `Pillow` (PIL) -- image-to-PDF fallback
- `reportlab` -- used in `examples/aggregations.py`
- Calibre (`ebook-convert`) -- EPUB, MOBI, DOCX, DJVU, and many more

## Natively Supported Formats

Images: `.png`, `.jpg`, `.jpeg`, `.bmp`, `.gif`, `.tiff`, `.webp`
Markup: `.html`, `.htm`, `.md`, `.markdown`
Pass-through: `.pdf`
Other: URL, raw HTML string, raw text string

## Calibre-Extended Formats

`.epub`, `.mobi`, `.azw`, `.azw3`, `.azw4`, `.docx`, `.docm`, `.odt`, `.rtf`,
`.djvu`, `.djv`, `.fb2`, `.fbz`, `.chm`, `.lit`, `.lrf`, `.pdb`, `.pml`,
`.pmlz`, `.prc`, `.cb7`, `.cbc`, `.cbr`, `.cbz`, `.kepub`, `.rb`, `.snb`,
`.tcr`, `.textile`, `.txtz`, `.htmlz`, `.opf`, `.pobi`, `.updb`

## Extension Points

1. **New format**: call `register_format_converter('.ext', converter_fn)`.
2. **New source kind**: add to `SrcKind` literal, `_resolve_src_kind`, and
   `func_for_kind` dict inside `get_pdf`.
3. **New store wrapper**: compose with `dol.wrap_kvs` / `Pipe` in `base.py`.
