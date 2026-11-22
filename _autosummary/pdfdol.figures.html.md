# pdfdol.figures

Crop a figure or table out of a PDF by its caption, and locate a quoted passage.

Two things a caller illustrating a paper needs:

- `figure(pdf, "Figure 3:")` returns the figure as PNG bytes, found by its caption.
  `figure_box` says where it is (`FigureBox(page, box, source)`) without rendering it.
- `find_passage(pdf, quote)` returns the page and the boxes of a quoted passage, so it
  can be highlighted (`Passage(page, boxes, source)`).

Pages are 0-based (like the page lists `PdfFilesReader` gives; `checks.text_overlaps`
reports 1-based page numbers for people). Boxes are `(x0, y0, x1, y1)` in PDF points,
origin at the top left of the *unrotated* page, which is how PyMuPDF reports text and
drawings; `figure` converts for a rotated page when it renders.

How a figure is found, in order: the graphics above its caption, else short text blocks
above it (a figure drawn as text), else the graphics beside it (a side caption). Growth
from the caption joins graphics no more than `max_gap` apart, and never across another
caption or a body paragraph, so a figure does not swallow its neighbour. A table is the
table PyMuPDF detects next to its caption, else its horizontal rules (booktabs), else the
nearer graphics; `source` names which, and `"caption-only"` or `"fallback"` says
nothing better was found.

Scanned PDFs (a page covered by one image, its text layer made by OCR) are a known trap:
the text layer’s boxes can sit tens of pixels off the glyphs. `find_passage` detects
such pages and, unless it is given an `ocr_words` function to read word boxes off the
rendered pixels (`ocracy_words` is one, built on `ocracy`), returns the page with no
boxes rather than a highlight in the wrong place. A figure on a scanned page has no
drawings to find it by, and an OCR layer splits prose into one block per line, so it is
read off the pixels instead (`source="pixels"`, see `pixel_figure_box`): the ink
above the caption, up to the first prose or caption above it. Best effort still: the
`scan_strategy` keyword of `figure_box` takes another strategy, or `"layout"` to
treat the scan like any page.

Needs PyMuPDF, the `figures` extra of pdfdol, imported only when called. PyMuPDF is
AGPL-3.0: whoever distributes or serves pdfdol together with it takes on its terms.

The caption-matching rule (a caption is text that *starts* with the given caption, not a
mention of it, and not a longer label) needs no PDF to check:

```pycon
>>> _starts_caption("Figure 1: Growth of the thing", "Figure 1:")
True
>>> _starts_caption("Figure 10: Another one", "Figure 1")
False
>>> _starts_caption("TABLE II Results", "Table I")
False
>>> _starts_caption("As Figure 1: shows", "Figure 1:")
False
```

and neither does the matching `find_passage` uses (case, curly quotes, punctuation,
dashes and hyphens do not matter):

```pycon
>>> _match_tokens([("The", 1), ("AI’s", 2), ("repos-", 3), ("itories,", 4)], "ai's repositories")
[2, 3, 4]
```

### Functions

| [`figure`](#pdfdol.figures.figure)(pdf, caption, \*[, page, kind, zoom])    | The figure or table captioned `caption`, as PNG bytes.                                                                                                        |
|--------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`figure_box`](#pdfdol.figures.figure_box)(pdf, caption, \*[, page, kind, ...]) | Where the figure or table captioned `caption` is: `FigureBox(page, box, source)`.                                                                             |
| [`find_passage`](#pdfdol.figures.find_passage)(pdf, quote, \*[, page, ...])       | The page and boxes of `quote` in `pdf`, or None when it is not there.                                                                                         |
| [`is_scanned`](#pdfdol.figures.is_scanned)(page, \*[, coverage])                | Whether a PyMuPDF page is a scan: one image covers at least `coverage` of it.                                                                                 |
| [`ocracy_words`](#pdfdol.figures.ocracy_words)(png, \*\*ocr_kwargs)               | Word boxes of an image with `ocracy`: an `ocr_words` for `find_passage`.                                                                                      |
| [`pixel_figure_box`](#pdfdol.figures.pixel_figure_box)(page, caption_box, \*[, ...])  | The box of the figure above `caption_box` on a scanned PyMuPDF `page`, read off its pixels, without the caption; None when there is no ink above the caption. |

### Classes

| [`FigureBox`](#pdfdol.figures.FigureBox)(page, box, source)   | Where a figure or table is: its page, its box, and how the box was found.    |
|---------------------------------------------------------------------------------|------------------------------------------------------------------------------|
| [`Passage`](#pdfdol.figures.Passage)(page, boxes, source)   | Where a quote was found: its page, its boxes, and where the boxes came from. |

### *class* pdfdol.figures.FigureBox(page, box, source)

Bases: [`NamedTuple`](https://docs.python.org/3/library/typing.html#typing.NamedTuple)

Where a figure or table is: its page, its box, and how the box was found.

`source` is one of `"graphics"`, `"text"` (a figure drawn as text), `"beside"`
(a side caption), `"pixels"` (the ink above the caption on a scanned page), `"table"` (a table PyMuPDF detected), `"rules"` (a booktabs
table), `"caption-only"` (nothing found next to the caption) or `"fallback"` (a
share of the page below a table caption).

#### box *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)*

Alias for field number 1

#### page *: [int](https://docs.python.org/3/builtins/functions.html#int)*

Alias for field number 0

#### source *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

Alias for field number 2

### *class* pdfdol.figures.Passage(page, boxes, source)

Bases: [`NamedTuple`](https://docs.python.org/3/library/typing.html#typing.NamedTuple)

Where a quote was found: its page, its boxes, and where the boxes came from.

`source` is `"text"` (the PDF’s text layer, the whole quote), `"text-head"`
(only the quote’s first words matched), `"ocr"` (OCR of the rendered page),
`"ocr-head"` (OCR, the first words only), or
`"none"` (a scanned page whose text layer holds the quote but whose boxes cannot be
trusted, and OCR was not given or did not find it): then `boxes` is empty.

#### boxes *: [tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)*

Alias for field number 1

#### page *: [int](https://docs.python.org/3/builtins/functions.html#int)*

Alias for field number 0

#### source *: [str](https://docs.python.org/3/builtins/stdtypes.html#str)*

Alias for field number 2

### pdfdol.figures.figure(pdf, caption, , page=None, kind=None, zoom=4.0, \*\*box_kwargs)

The figure or table captioned `caption`, as PNG bytes.

`zoom` scales the rendering (1.0 is 72 dpi; the default 4.0 is 288 dpi). Every other
keyword is passed to `figure_box`, which says how the box is found.

```pycon
>>> png = figure("paper.pdf", "Figure 3:")
>>> png = figure("paper.pdf", "Table 2")  # a table: kind is inferred
```

* **Return type:**
  [`bytes`](https://docs.python.org/3/builtins/stdtypes.html#bytes)

### pdfdol.figures.figure_box(pdf, caption, , page=None, kind=None, with_caption=True, margin=6.0, max_up=0.65, max_gap=40.0, table_height=0.35, rule_gap=0.3, body_words=25, scan_strategy='pixels')

Where the figure or table captioned `caption` is: `FigureBox(page, box, source)`.

* **Parameters:**
  * **pdf** – path, bytes, file object, or an open PyMuPDF document.
  * **caption** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – the start of the caption, e.g. `"Figure 3:"` or `"Table 2"`.
    Matched case-insensitively at the start of a text block or line, and only where
    the label reads as a caption (“Table 2 shows” and “Table 2)” are prose). Of several
    matches, the first whose figure or table is found is used.
  * **page** ([`int`](https://docs.python.org/3/builtins/functions.html#int) | [`None`](https://docs.python.org/3/builtins/constants.html#None)) – 0-based page to look on; every page when None.
  * **kind** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`None`](https://docs.python.org/3/builtins/constants.html#None)) – `"figure"` or `"table"`; when None, `"table"` if the caption starts
    with “Tab”, else `"figure"`.
  * **with_caption** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – include the caption in the box. Without it, a caption with
    nothing found next to it raises `LookupError` (there is no figure to return).
  * **margin** ([`float`](https://docs.python.org/3/builtins/functions.html#float)) – white space (points) kept around the box.
  * **max_up** ([`float`](https://docs.python.org/3/builtins/functions.html#float)) – how far from the caption, as a fraction of the page height, a figure’s
    graphics may reach.
  * **max_gap** ([`float`](https://docs.python.org/3/builtins/functions.html#float)) – gap (points) that separates a figure from other graphics.
  * **table_height** ([`float`](https://docs.python.org/3/builtins/functions.html#float)) – fraction of the page taken below a table caption when nothing is
    found next to it (`source="fallback"`).
  * **rule_gap** ([`float`](https://docs.python.org/3/builtins/functions.html#float)) – fraction of the page height two consecutive rules of one table may be
    apart.
  * **body_words** ([`int`](https://docs.python.org/3/builtins/functions.html#int)) – a text block with at least this many words is body text: a figure
    never grows across it.
  * **scan_strategy** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`Callable`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Callable)[[`...`](https://docs.python.org/3/builtins/constants.html#Ellipsis), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]) – how a figure on a scanned page (see `is_scanned`) is found:
    `"pixels"` (`pixel_figure_box`, `source="pixels"`), `"layout"` (as on any
    page), or a callable with `pixel_figure_box`’s signature. It runs only when
    the layout finds no graphics for the figure (a scan has none to find; a page
    with drawings over a page-sized image keeps its `"graphics"` box), and when
    it finds nothing the layout’s result stands. Tables are always found from the
    layout.
* **Raises:**
  * [**LookupError**](https://docs.python.org/3/builtins/exceptions.html#LookupError) – no caption starts with `caption` (or, `with_caption=False`,
    nothing was found next to it).
  * [**IndexError**](https://docs.python.org/3/builtins/exceptions.html#IndexError) – `page` is not a page of the PDF.
* **Return type:**
  [`FigureBox`](#pdfdol.figures.FigureBox)

### pdfdol.figures.find_passage(pdf, quote, , page=None, ocr_words=None, ocr_zoom=3.0, scan_coverage=0.8, head_words=6)

The page and boxes of `quote` in `pdf`, or None when it is not there.

Matches the quote against the page’s words by their letters and digits, so case,
curly quotes, punctuation, dashes and hyphens (compounds, and words broken at a line
end) do not matter. Every page is
searched for the whole quote before any is searched for its first `head_words`
words (`source="text-head"`). On a scanned page (images cover `scan_coverage`
of it) the text layer’s boxes are not trusted: they are read off the rendered page
with `ocr_words` when given (accepted only if the OCR’d words spell the quote),
else the page is returned with no boxes (`source="none"`). With `ocr_words`, a
scanned page with no text layer at all is OCR’d too (only those: OCR is slow).

* **Parameters:**
  * **pdf** – path, bytes, file object, or an open PyMuPDF document.
  * **quote** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – the text to find.
  * **page** ([`int`](https://docs.python.org/3/builtins/functions.html#int) | [`None`](https://docs.python.org/3/builtins/constants.html#None)) – 0-based page to look on; every page when None.
  * **ocr_words** ([`Callable`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Callable)[[[`bytes`](https://docs.python.org/3/builtins/stdtypes.html#bytes)], [`Iterable`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Iterable)[[`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)]] | [`None`](https://docs.python.org/3/builtins/constants.html#None)) – `png_bytes -> [(word, (x0, y0, x1, y1)), ...]` in pixels of that
    image, for scanned pages. `ocracy_words` is one.
  * **ocr_zoom** ([`float`](https://docs.python.org/3/builtins/functions.html#float)) – rendering scale of the page given to `ocr_words`.
* **Return type:**
  [`Passage`](#pdfdol.figures.Passage) | [`None`](https://docs.python.org/3/builtins/constants.html#None)

```pycon
>>> p = find_passage("paper.pdf", "the results hold across models")
>>> p.page, p.boxes[0]
(4, (72.0, 310.2, 523.1, 322.0))
```

### pdfdol.figures.is_scanned(page, , coverage=0.8)

Whether a PyMuPDF page is a scan: one image covers at least `coverage` of it.

* **Return type:**
  [`bool`](https://docs.python.org/3/builtins/functions.html#bool)

### pdfdol.figures.ocracy_words(png, \*\*ocr_kwargs)

Word boxes of an image with `ocracy`: an `ocr_words` for `find_passage`.

Uses `ocracy`’s default backend unless `backend=` is given. A backend that reports
only lines has each line split into words, with boxes in proportion to their length.
Needs `ocracy` and an OCR backend.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)

### pdfdol.figures.pixel_figure_box(page, caption_box, , max_up=0.65, max_gap=40.0, body_words=25, zoom=2.0, ink=128)

The box of the figure above `caption_box` on a scanned PyMuPDF `page`, read off
its pixels, without the caption; None when there is no ink above the caption.

The page is rendered in gray above the caption and cut into bands of rows holding
ink. The figure is the bands climbed from the caption upwards, each within
`max_gap` points of the last, up to the first that is text: another caption or a
prose line in the text layer, or a run of printed lines in the pixels (a band one
line tall that inks most of its span, under a full line). Boxes, arrows and labels
inside a figure are ink like any other, so a figure of separate boxes comes whole.
The default `scan_strategy` of `figure_box`; its signature is the one a
replacement takes (`page, caption_box, *, max_up, max_gap`).

* **Parameters:**
  * **page** – a PyMuPDF page; its rotation must be 0 (else None: use the layout).
  * **caption_box** ([`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)) – the caption’s `(x0, y0, x1, y1)`, from the page’s text layer.
  * **zoom** ([`float`](https://docs.python.org/3/builtins/functions.html#float)) – rendering scale (2.0 is 144 dpi).
  * **ink** ([`int`](https://docs.python.org/3/builtins/functions.html#int)) – gray level (0 to 255) below which a pixel is ink.
* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple) | [`None`](https://docs.python.org/3/builtins/constants.html#None)
