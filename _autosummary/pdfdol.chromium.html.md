# pdfdol.chromium

Headless Chromium engine: print web pages designed for the screen.

wkhtmltopdf and WeasyPrint cannot print CSS grid, flex, `env()`, sticky headers or
scripts. `html_to_pdf_w_chromium` renders the page in Chromium with the viewport set
to the printable width, so the screen layout is the print layout, then fixes what
paginated output gets wrong:

- sticky/fixed elements become static (or are removed);
- single-track grids become flex columns with the same gap, *before* any keep-together
  rule. Without this, `break-inside: avoid` on grid items makes Chromium push an item
  to the next page without growing its grid row, and the next block is drawn on top of
  it;
- keep-together (`break-inside: avoid`) is applied to a configurable list of
  selectors, and headings keep with what follows.

The PDF is then checked with `pdfdol.checks.text_overlaps`, so a broken pagination is
never silent. Needs the `chromium` extra of pdfdol (playwright and PyMuPDF), then
`playwright install chromium`.

```pycon
>>> top, right, bottom, left = parse_margin("12mm 10mm")
>>> round(top), round(right), round(bottom), round(left)
(45, 38, 45, 38)
>>> round(printable_width_px("A4", "12mm 10mm"))
718
```

### Functions

| [`html_to_pdf_w_chromium`](#pdfdol.chromium.html_to_pdf_w_chromium)(src[, egress, ...])   | Print a web page (URL, HTML file path or HTML string) to PDF with headless Chromium.      |
|-----------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------|
| [`parse_margin`](#pdfdol.chromium.parse_margin)(margin)                         | CSS-style margin (1 to 4 values; px, mm, cm, in, pt) -> (top, right, bottom, left) in px. |
| [`printable_width_px`](#pdfdol.chromium.printable_width_px)([page_format, margin])    | Width in CSS px of the area inside the margins.                                           |

### Exceptions

| [`PdfTextOverlapError`](#pdfdol.chromium.PdfTextOverlapError)(overlaps)   | The PDF has overlapping text; `.overlaps` maps page -> overlapping line pairs.   |
|----------------------------------------------------------------------------------|----------------------------------------------------------------------------------|

### *exception* pdfdol.chromium.PdfTextOverlapError(overlaps)

Bases: [`ValueError`](https://docs.python.org/3/builtins/exceptions.html#ValueError)

The PDF has overlapping text; `.overlaps` maps page -> overlapping line pairs.

### pdfdol.chromium.html_to_pdf_w_chromium(src, egress=None, , page_format='A4', margin='12mm 10mm', color_scheme='light', media='screen', remove=(), keep_together='.screen,.card,figure,table,tr,blockquote,li,h1,h2,h3,h4', keep_with_next='h1,h2,h3,h4', on_overlap='raise', overlap_min_frac=0.3, viewport_height=1000, wait_until='networkidle')

Print a web page (URL, HTML file path or HTML string) to PDF with headless Chromium.

* **Parameters:**
  * **src** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – URL, path to an HTML file, or an HTML string.
  * **egress** ([`None`](https://docs.python.org/3/builtins/constants.html#None) | [`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`Callable`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Callable)) – `None` -> bytes; a str -> save there and return the path; a callable
    -> applied to the bytes (as in `get_pdf`).
  * **page_format** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)) – `'A4'`, `'letter'`, … or `(w, h)` in points.
  * **margin** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – CSS-style margin, e.g. `"12mm 10mm"`.
  * **color_scheme** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – `'light'` or `'dark'` (`prefers-color-scheme`).
  * **media** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – CSS media to emulate; `'screen'` prints the designed screen layout.
  * **remove** ([`Iterable`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Iterable)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]) – CSS selectors of elements to delete (navigation bars, cookie banners).
  * **keep_together** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`Iterable`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Iterable)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]) – selectors that must not be split across pages.
  * **keep_with_next** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`Iterable`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Iterable)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]) – selectors that must stay with the following content.
  * **on_overlap** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – what to do when text overlaps in the result: `'raise'`
    (`PdfTextOverlapError`), `'warn'`, or `'ignore'` (skips the check).
  * **overlap_min_frac** ([`float`](https://docs.python.org/3/builtins/functions.html#float)) – threshold passed to `text_overlaps`.
* **Return type:**
  [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)

### pdfdol.chromium.parse_margin(margin)

CSS-style margin (1 to 4 values; px, mm, cm, in, pt) -> (top, right, bottom, left) in px.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float), [`float`](https://docs.python.org/3/builtins/functions.html#float)]

### pdfdol.chromium.printable_width_px(page_format='A4', margin='12mm 10mm')

Width in CSS px of the area inside the margins.

* **Return type:**
  [`float`](https://docs.python.org/3/builtins/functions.html#float)
