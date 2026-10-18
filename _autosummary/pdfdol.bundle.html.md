# pdfdol.bundle

Bundle several PDFs into one, with a contents page, per-document headers and bookmarks.

`concat_pdfs` just joins documents. `bundle_pdf_bytes` keeps track of which
page each document starts on while joining, which is what makes these possible:

- `toc`: a contents page (several pages if needed) whose lines link to the
  documents’ first pages;
- `doc_header`: a band naming the document, added *above* its first page, so
  no content is covered;
- `outline`: one bookmark per document.

Rendering text uses `reportlab`, imported lazily: without `toc` and
`doc_header`, only `pypdf` is used.

```pycon
>>> import io, pypdf
>>> def blank(n, w=200, h=300):
...     writer = pypdf.PdfWriter()
...     for _ in range(n):
...         _ = writer.add_blank_page(width=w, height=h)
...     buf = io.BytesIO(); _ = writer.write(buf); return buf.getvalue()
>>> out = bundle_pdf_bytes({'a.pdf': blank(2), 'b.pdf': blank(1)}, outline=True)
>>> reader = pypdf.PdfReader(io.BytesIO(out))
>>> len(reader.pages), [o.title for o in reader.outline]
(3, ['a.pdf', 'b.pdf'])
```

### Module Attributes

| [`PAGE_SIZES`](#pdfdol.bundle.PAGE_SIZES)   | Page sizes in points (1/72 inch), portrait.                                                                                                                                                                                              |
|---------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`TocRenderer`](#pdfdol.bundle.TocRenderer)  | A contents renderer maps `(entries, title)` to the contents PDF bytes, or to `(pdf_bytes, link_rects)` where `link_rects[i]` is `(toc_page_index, (x0, y0, x1, y1))` for entry `i`, making that region a link to the entry's first page. |

### Functions

| [`add_header_band`](#pdfdol.bundle.add_header_band)(page, text, \*[, height, ...])   | Extend `page` upward by `height` and draw `text` in the new band (in place).          |
|---------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------|
| [`bundle_pdf_bytes`](#pdfdol.bundle.bundle_pdf_bytes)(items, \*[, toc, ...])          | Join PDFs, optionally adding a contents page, document headers and bookmarks.         |
| [`fit_pdf_to_page`](#pdfdol.bundle.fit_pdf_to_page)(pdf_bytes[, page_size, ...])     | Put each page of `pdf_bytes` on a `page_size` page, scaled to fit and centered.       |
| [`render_contents_pdf`](#pdfdol.bundle.render_contents_pdf)(entries[, title, ...])       | Default `TocRenderer`: a title, then one line per entry with its page range at right. |
| [`resolve_page_size`](#pdfdol.bundle.resolve_page_size)(page_size)                     | Name (case-insensitive, see `PAGE_SIZES`) or `(w, h)` points -> `(w, h)`.             |

### Classes

| [`Entry`](#pdfdol.bundle.Entry)(key, start_page, n_pages)   | One document in a bundle.   |
|------------------------------------------------------------------------------------|-----------------------------|

### *class* pdfdol.bundle.Entry(key, start_page, n_pages)

Bases: [`NamedTuple`](https://docs.python.org/3/library/typing.html#typing.NamedTuple)

One document in a bundle. `start_page` is 1-based, in the final PDF.

#### key *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

Alias for field number 0

#### n_pages *: [int](https://docs.python.org/3/builtins/functions.html#int)*

Alias for field number 2

#### start_page *: [int](https://docs.python.org/3/builtins/functions.html#int)*

Alias for field number 1

### pdfdol.bundle.PAGE_SIZES *= {'A3': (841.89, 1190.55), 'A4': (595.28, 841.89), 'A5': (419.53, 595.28), 'legal': (612.0, 1008.0), 'letter': (612.0, 792.0)}*

Page sizes in points (1/72 inch), portrait.

### pdfdol.bundle.TocRenderer

A contents renderer maps `(entries, title)` to the contents PDF bytes, or to
`(pdf_bytes, link_rects)` where `link_rects[i]` is `(toc_page_index, (x0, y0, x1, y1))`
for entry `i`, making that region a link to the entry’s first page.

alias of [`Callable`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Callable)[[[`list`](https://docs.python.org/3/builtins/stdtypes.html#list), [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)], [`bytes`](https://docs.python.org/3/builtins/stdtypes.html#bytes) | [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)]

### pdfdol.bundle.add_header_band(page, text, , height=30, margin=36, font='Helvetica-Bold', font_size=9, gray=0.92)

Extend `page` upward by `height` and draw `text` in the new band (in place).

* **Return type:**
  [`None`](https://docs.python.org/3/builtins/constants.html#None)

### pdfdol.bundle.bundle_pdf_bytes(items, , toc=False, doc_header=None, outline=False, title=None, toc_title='Contents', header_height=30)

Join PDFs, optionally adding a contents page, document headers and bookmarks.

* **Parameters:**
  * **items** ([`Mapping`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Mapping) | [`Iterable`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Iterable)) – `{key: pdf_bytes}` or an iterable of `(key, pdf_bytes)`, in order.
  * **toc** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool) | [`Callable`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Callable)[[[`list`](https://docs.python.org/3/builtins/stdtypes.html#list), [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)], [`Union`](https://docs.python.org/3/library/typing.html#typing.Union)[[`bytes`](https://docs.python.org/3/builtins/stdtypes.html#bytes), [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)]]) – `True` for the default contents page (`render_contents_pdf`), or a
    `TocRenderer` callable `(entries, title) -> bytes | (bytes, link_rects)`.
  * **doc_header** ([`None`](https://docs.python.org/3/builtins/constants.html#None) | [`bool`](https://docs.python.org/3/builtins/functions.html#bool) | [`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`Callable`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Callable)[[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)], [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]) – Text of the band added above each document’s first page.
    `True` -> the key; a format string using `{key}`, `{start_page}`,
    `{n_pages}`; or a callable `key -> str`.
  * **outline** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – Add one bookmark per document.
  * **title** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`None`](https://docs.python.org/3/builtins/constants.html#None)) – PDF title metadata; also the contents page title if `toc_title` is
    left at its default.
  * **toc_title** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – Title of the contents page.
  * **header_height** ([`float`](https://docs.python.org/3/builtins/functions.html#float)) – Height in points of the header band.
* **Return type:**
  [`bytes`](https://docs.python.org/3/builtins/stdtypes.html#bytes)

```pycon
>>> import io, pypdf
>>> w = pypdf.PdfWriter(); _ = w.add_blank_page(width=200, height=300)
>>> buf = io.BytesIO(); _ = w.write(buf); one = buf.getvalue()
>>> out = bundle_pdf_bytes({'a.pdf': one, 'b.pdf': one}, toc=True, doc_header='{key}')
>>> reader = pypdf.PdfReader(io.BytesIO(out))
>>> len(reader.pages)  # 1 contents page + 2 documents
3
>>> float(reader.pages[1].mediabox.height)  # 300 + header band
330.0
```

### pdfdol.bundle.fit_pdf_to_page(pdf_bytes, page_size='A4', , margin=36, landscape_if_wider=True)

Put each page of `pdf_bytes` on a `page_size` page, scaled to fit and centered.

A page wider than tall gets a landscape page when `landscape_if_wider`.

```pycon
>>> import io, pypdf
>>> w = pypdf.PdfWriter(); _ = w.add_blank_page(width=1000, height=500)
>>> buf = io.BytesIO(); _ = w.write(buf)
>>> out = fit_pdf_to_page(buf.getvalue(), 'A4')
>>> [round(float(v)) for v in pypdf.PdfReader(io.BytesIO(out)).pages[0].mediabox[2:]]
[842, 595]
```

* **Return type:**
  [`bytes`](https://docs.python.org/3/builtins/stdtypes.html#bytes)

### pdfdol.bundle.render_contents_pdf(entries, title='Contents', , page_size='A4', margin=36, line_height=18, font='Helvetica', title_font='Helvetica-Bold', font_size=10, title_size=16)

Default `TocRenderer`: a title, then one line per entry with its page range at right.

Returns `(pdf_bytes, link_rects)`.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)

### pdfdol.bundle.resolve_page_size(page_size)

Name (case-insensitive, see `PAGE_SIZES`) or `(w, h)` points -> `(w, h)`.

```pycon
>>> resolve_page_size('a4')
(595.28, 841.89)
>>> resolve_page_size((100, 200))
(100.0, 200.0)
```

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float)]
