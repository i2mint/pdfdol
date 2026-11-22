"""Crop a figure or table out of a PDF by its caption, and locate a quoted passage.

Two things a caller illustrating a paper needs:

- ``figure(pdf, "Figure 3:")`` returns the figure as PNG bytes, found by its caption.
  ``figure_box`` says where it is (``FigureBox(page, box, source)``) without rendering it.
- ``find_passage(pdf, quote)`` returns the page and the boxes of a quoted passage, so it
  can be highlighted (``Passage(page, boxes, source)``).

Pages are 0-based (like the page lists ``PdfFilesReader`` gives; ``checks.text_overlaps``
reports 1-based page numbers for people). Boxes are ``(x0, y0, x1, y1)`` in PDF points,
origin at the top left of the *unrotated* page, which is how PyMuPDF reports text and
drawings; ``figure`` converts for a rotated page when it renders.

How a figure is found, in order: the graphics above its caption, else short text blocks
above it (a figure drawn as text), else the graphics beside it (a side caption). Growth
from the caption joins graphics no more than ``max_gap`` apart, and never across another
caption or a body paragraph, so a figure does not swallow its neighbour. A table is the
table PyMuPDF detects next to its caption, else its horizontal rules (booktabs), else the
nearer graphics; ``source`` names which, and ``"caption-only"`` or ``"fallback"`` says
nothing better was found.

Scanned PDFs (a page covered by one image, its text layer made by OCR) are a known trap:
the text layer's boxes can sit tens of pixels off the glyphs. ``find_passage`` detects
such pages and, unless it is given an ``ocr_words`` function to read word boxes off the
rendered pixels (``ocracy_words`` is one, built on ``ocracy``), returns the page with no
boxes rather than a highlight in the wrong place. Figures on scanned pages are best
effort.

Needs PyMuPDF, the ``figures`` extra of pdfdol, imported only when called. PyMuPDF is
AGPL-3.0: whoever distributes or serves pdfdol together with it takes on its terms.

The caption-matching rule (a caption is text that *starts* with the given caption, not a
mention of it, and not a longer label) needs no PDF to check:

>>> _starts_caption("Figure 1: Growth of the thing", "Figure 1:")
True
>>> _starts_caption("Figure 10: Another one", "Figure 1")
False
>>> _starts_caption("TABLE II Results", "Table I")
False
>>> _starts_caption("As Figure 1: shows", "Figure 1:")
False

and neither does the token matching ``find_passage`` uses (case, curly quotes, attached
punctuation and end-of-line hyphens do not matter):

>>> _match_tokens([("The", 1), ("AI’s", 2), ("repos-", 3), ("itories,", 4)], "ai's repositories")
[2, 3, 4]
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable, Iterable, Sequence
from contextlib import contextmanager
from typing import Any, NamedTuple, Optional

Box = tuple  # (x0, y0, x1, y1) in PDF points
OcrWords = Callable[[bytes], Iterable[tuple]]  # png -> [(text, (x0, y0, x1, y1)), ...]

DFLT_ZOOM = 4.0
DFLT_MARGIN = 6.0  # points of white space kept around a crop
DFLT_MAX_UP = 0.65  # a figure's graphics reach at most this fraction of a page from its caption
DFLT_MAX_GAP = 40.0  # points: graphics further apart than this belong to different things
DFLT_TABLE_HEIGHT = 0.35  # fraction of the page taken below a table caption when nothing is found
DFLT_RULE_GAP = 0.3  # fraction of the page: consecutive rules of one table are at most this apart
DFLT_BODY_WORDS = 25  # a text block with this many words is body text, not part of a figure
DFLT_SCAN_COVERAGE = 0.8  # a page whose images cover this fraction of it is a scan
DFLT_OCR_ZOOM = 3.0
DFLT_QUOTE_HEAD_WORDS = 6  # retry a long quote on its first words
_MARGIN_BAND = 0.06  # fraction of the page height: running headers and footers live here
_LABEL_MAX_HEIGHT = 40.0  # points: taller text blocks inside a figure area are not axis labels
_LABEL_X_SLACK = 30.0  # points: axis labels may stick out of the graphics this much
_MIN_GRAPHIC_SPAN = 2.0  # points: drawings smaller than this both ways are specks
_HAIRLINE_PAD = 0.5  # points added around a zero-width or zero-height drawing
_RULE_X_TOL = 3.0  # points: table rules whose ends differ less than this are one table's
_COL_SLACK = 20.0  # points: graphics this close to the caption's column count as in it
_CAPTION_LIKE = re.compile(
    r"^\s*(fig(ure)?|tab(le)?)\.?\s*([a-z]?\d+|[ivxlc]+)\b", re.IGNORECASE
)


class Passage(NamedTuple):
    """Where a quote was found: its page, its boxes, and where the boxes came from.

    ``source`` is ``"text"`` (the PDF's text layer, the whole quote), ``"text-head"``
    (only the quote's first words matched), ``"ocr"`` (OCR of the rendered page), or
    ``"none"`` (a scanned page whose text layer holds the quote but whose boxes cannot be
    trusted, and OCR was not given or did not find it): then ``boxes`` is empty.
    """

    page: int
    boxes: tuple
    source: str


class FigureBox(NamedTuple):
    """Where a figure or table is: its page, its box, and how the box was found.

    ``source`` is one of ``"graphics"``, ``"text"`` (a figure drawn as text), ``"beside"``
    (a side caption), ``"table"`` (a table PyMuPDF detected), ``"rules"`` (a booktabs
    table), ``"caption-only"`` (nothing found next to the caption) or ``"fallback"`` (a
    share of the page below a table caption).
    """

    page: int
    box: Box
    source: str


# --------------------------------------------------------------------------- shared


@contextmanager
def _opened(pdf):
    """An open PyMuPDF document for ``pdf`` (path, bytes, file object or open document),
    closed after use only if it was opened here."""
    from pdfdol.checks import _open_pdf

    doc = _open_pdf(pdf)
    try:
        yield doc
    finally:
        if doc is not pdf:
            doc.close()


def _pages(doc, page: Optional[int]) -> Sequence[int]:
    if page is None:
        return range(len(doc))
    if not isinstance(page, int) or not 0 <= page < len(doc):
        raise IndexError(f"page {page!r} is out of range: the PDF has {len(doc)} pages, 0-based")
    return [page]


def _norm(s: str) -> str:
    """Normalise text for matching: NFKC, plain quotes and dashes, soft hyphens gone,
    whitespace collapsed, lower case."""
    s = unicodedata.normalize("NFKC", s)
    s = re.sub("[‘’‛]", "'", s)
    s = re.sub("[“”„]", '"', s)
    s = re.sub("[–—]", "-", s).replace("­", "")
    return re.sub(r"\s+", " ", s).strip().lower()


def _token(word: str) -> str:
    """A word as matching sees it: normalised, punctuation stripped from both ends."""
    return re.sub(r"^[\W_]+|[\W_]+$", "", _norm(word))


def _starts_caption(text: str, caption: str) -> bool:
    """Whether ``text`` starts with ``caption`` (and not with a longer label)."""
    text, cap = _norm(text), _norm(caption)
    if not cap or not text.startswith(cap):
        return False
    rest = text[len(cap) :]
    return not (cap[-1].isalnum() and rest[:1].isalnum())


def _as_box(rect) -> Box:
    return (float(rect.x0), float(rect.y0), float(rect.x1), float(rect.y1))


def _text_blocks(page) -> list:
    """The page's text blocks as ``(rect, text)``, each PyMuPDF block split before every
    line that starts like a caption: PyMuPDF merges a caption into the axis labels above
    it, or two side-by-side captions into one block."""
    import fitz

    out = []
    for block in page.get_text("dict")["blocks"]:
        if block.get("type", 0) != 0:
            continue
        rect, lines = None, []
        for line in block.get("lines", []):
            text = "".join(s["text"] for s in line["spans"])
            if lines and _CAPTION_LIKE.match(text):
                out.append((rect, "\n".join(lines)))
                rect, lines = None, []
            r = fitz.Rect(line["bbox"])
            rect = r if rect is None else rect | r
            lines.append(text)
        if lines:
            out.append((rect, "\n".join(lines)))
    return out


def _unrotated_rect(page):
    """The page's rectangle in the unrotated coordinates text and drawings use."""
    return page.rect * page.derotation_matrix


# --------------------------------------------------------------------------- page layout


class _Layout:
    """The text blocks and graphics of one page, read once."""

    def __init__(self, page, *, body_words: int):
        import fitz

        self.page = page
        self.rect = _unrotated_rect(page)
        self.W, self.H = self.rect.width, self.rect.height
        self.body_words = body_words
        self.blocks = _text_blocks(page)
        self.graphics = self._graphics()

    def _graphics(self):
        import fitz

        area = self.rect.get_area() or 1
        rects = [fitz.Rect(d["rect"]) for d in self.page.get_drawings()]
        rects += [
            fitz.Rect(i["bbox"])
            for i in self.page.get_image_info()
            # a scan's page image is the page, not a figure on it
            if (fitz.Rect(i["bbox"]) & self.rect).get_area() / area < DFLT_SCAN_COVERAGE
        ]
        out = []
        for r in rects:
            if max(r.width, r.height) < _MIN_GRAPHIC_SPAN:
                continue
            # hairlines (table rules, axes) have no area: pad them so unions keep them
            px = _HAIRLINE_PAD if r.width < 2 * _HAIRLINE_PAD else 0
            py = _HAIRLINE_PAD if r.height < 2 * _HAIRLINE_PAD else 0
            out.append(fitz.Rect(r.x0 - px, r.y0 - py, r.x1 + px, r.y1 + py))
        return out

    def is_caption_like(self, text: str) -> bool:
        return bool(_CAPTION_LIKE.match(text))

    def is_body(self, text: str) -> bool:
        return len(text.split()) >= self.body_words

    def barriers(self, blk):
        """Text a figure never grows across: other captions, and body paragraphs."""
        return [
            r
            for r, t in self.blocks
            if not r.intersects(blk) and (self.is_caption_like(t) or self.is_body(t))
        ]

    def in_margin(self, r) -> bool:
        band = _MARGIN_BAND * self.H
        return r.y1 <= self.rect.y0 + band or r.y0 >= self.rect.y1 - band


def _between(a, b):
    """The empty region separating two rects, or None if they touch or overlap."""
    import fitz

    x0, x1 = max(a.x0, b.x0), min(a.x1, b.x1)
    y0, y1 = max(a.y0, b.y0), min(a.y1, b.y1)
    if x0 <= x1 and y0 <= y1:
        return None
    if x0 <= x1:  # stacked: the strip between them, as wide as both
        return fitz.Rect(min(a.x0, b.x0), y1, max(a.x1, b.x1), y0)
    if y0 <= y1:  # side by side: the strip between them, as tall as their overlap
        return fitz.Rect(x1, y0, x0, y1)
    return fitz.Rect(x1, y1, x0, y0)  # diagonal: the corner gap


def _gap(a, b) -> float:
    return max(a.x0 - b.x1, b.x0 - a.x1, a.y0 - b.y1, b.y0 - a.y1, 0)


def _grow(seed, candidates, *, max_gap, barriers=()):
    """The union of the candidates reachable from ``seed`` through gaps of at most
    ``max_gap`` whose separating region holds no barrier; None if none is reachable."""
    box, reached, pending, grown = seed, None, list(candidates), True
    while grown:
        grown = False
        for r in list(pending):
            if _gap(r, box) > max_gap:
                continue
            region = _between(r, box)
            if region is not None and any(
                (b & region).get_area() > 1 for b in barriers
            ):
                continue
            box = box | r
            reached = r if reached is None else reached | r
            pending.remove(r)
            grown = True
    return reached


def _with_inner_text(lay, box, blk, *, max_height=_LABEL_MAX_HEIGHT):
    """``box`` grown by the text blocks (axis labels, legends, cells) lying inside it,
    captions and body paragraphs aside."""
    for r, t in lay.blocks:
        if (
            not r.intersects(blk)
            and not lay.is_caption_like(t)
            and r.y0 >= box.y0 - 2
            and r.y1 <= box.y1 + 2
            and r.x0 >= box.x0 - _LABEL_X_SLACK
            and r.x1 <= box.x1 + _LABEL_X_SLACK
            and r.height < max_height
        ):
            box |= r
    return box


# --------------------------------------------------------------------------- captions


def _find_caption(doc, caption, page):
    """(page index, caption rect): the text block (split at caption-like lines, see
    ``_text_blocks``) that starts with ``caption``."""
    pages = _pages(doc, page)
    for i in pages:
        for rect, text in _text_blocks(doc[i]):
            if _starts_caption(text, caption):
                return i, rect
    mentioned = [i for i in pages if doc[i].search_for(caption)]
    where = f"page {page}" if page is not None else "any page"
    raise LookupError(
        f"no caption starts with {caption!r} on {where}"
        + (f"; it is only mentioned in text on page(s) {mentioned}" if mentioned else "")
    )


def _column_limits(lay, blk):
    """The x-range a figure captioned ``blk`` may use: the page, unless sibling captions
    sit beside it (side-by-side figures), then the share of the page nearest to it."""
    lo, hi = lay.rect.x0, lay.rect.x1
    c = (blk.x0 + blk.x1) / 2
    for r, t in lay.blocks:
        same_row = abs(r.y0 - blk.y0) < max(blk.height, 12) and not r.intersects(blk)
        if same_row and lay.is_caption_like(t):
            mid = (c + (r.x0 + r.x1) / 2) / 2
            if mid < c:
                lo = max(lo, mid)
            else:
                hi = min(hi, mid)
    return lo, hi


# --------------------------------------------------------------------------- figures


def _graphics_from_caption(lay, blk, side, *, max_up, max_gap):
    """The graphics reached from the caption going ``side`` ("above" or "below"), or None.

    Seeds are graphics in the caption's own column; growth from them is free in x (a
    full-width figure with a short caption), bounded by the sibling captions' share of
    the page, by ``max_up`` and by the barriers.
    """
    import fitz

    lo, hi = _column_limits(lay, blk)
    reach = max_up * lay.H
    if side == "above":
        cands = [r for r in lay.graphics if r.y1 <= blk.y0 + 2 and r.y0 >= blk.y0 - reach]
        seed = fitz.Rect(blk.x0, blk.y0 - 1, blk.x1, blk.y0)
    else:
        cands = [r for r in lay.graphics if r.y0 >= blk.y1 - 2 and r.y1 <= blk.y1 + reach]
        seed = fitz.Rect(blk.x0, blk.y1, blk.x1, blk.y1 + 1)
    cands = [r for r in cands if r.x0 >= lo - 1 and r.x1 <= hi + 1]
    col = fitz.Rect(blk.x0 - _COL_SLACK, lay.rect.y0, blk.x1 + _COL_SLACK, lay.rect.y1)
    barriers = lay.barriers(blk)
    first = _grow(seed, [r for r in cands if r.intersects(col)], max_gap=max_gap, barriers=barriers)
    if first is None:
        return None
    rest = [r for r in cands if not first.contains(r)]
    return first | (_grow(first, rest, max_gap=max_gap, barriers=barriers) or first)


def _text_figure_box(lay, blk, *, max_up, max_gap):
    """A figure drawn as positioned text: the short text blocks climbed from the caption
    upwards, up to the first caption, body paragraph or gap; None if none."""
    import fitz

    col = fitz.Rect(blk.x0 - _COL_SLACK, lay.rect.y0, blk.x1 + _COL_SLACK, lay.rect.y1)
    above = sorted(
        ((r, t) for r, t in lay.blocks if r.y1 <= blk.y0 + 1 and r.intersects(col)),
        key=lambda rt: -rt[0].y1,
    )
    box = None
    for r, t in above:
        top = blk.y0 if box is None else box.y0
        if top - r.y1 > max_gap or r.y0 < blk.y0 - max_up * lay.H:
            break
        if lay.is_body(t) or lay.is_caption_like(t) or lay.in_margin(r):
            break
        box = r if box is None else box | r
    return box


def _graphics_beside(lay, blk, *, max_up, max_gap):
    """The graphics beside a side caption, grown from those level with it; None if none."""
    level = [r for r in lay.graphics if r.y0 < blk.y1 and r.y1 > blk.y0]
    barriers = lay.barriers(blk)
    first = _grow(blk, level, max_gap=max_gap, barriers=barriers)
    if first is None:
        return None
    reach = max_up * lay.H
    rest = [
        r
        for r in lay.graphics
        if not first.contains(r) and r.y0 >= blk.y0 - reach and r.y1 <= blk.y1 + reach
    ]
    return first | (_grow(first, rest, max_gap=max_gap, barriers=barriers) or first)


def _figure_body(lay, blk, *, max_up, max_gap):
    """(box, source) of a figure without its caption."""
    box = _graphics_from_caption(lay, blk, "above", max_up=max_up, max_gap=max_gap)
    if box is not None:
        return _with_inner_text(lay, box, blk), "graphics"
    box = _text_figure_box(lay, blk, max_up=max_up, max_gap=max_gap)
    if box is not None:
        return box, "text"
    box = _graphics_beside(lay, blk, max_up=max_up, max_gap=max_gap)
    if box is not None:
        return _with_inner_text(lay, box, blk), "beside"
    return None, "caption-only"


# --------------------------------------------------------------------------- tables


def _detected_table(lay, blk, *, max_gap):
    """The table PyMuPDF detects nearest above or below ``blk``, within ``max_gap``."""
    import fitz

    try:
        tables = [fitz.Rect(t.bbox) for t in lay.page.find_tables().tables]
    except Exception:  # find_tables needs PyMuPDF >= 1.23; any failure means "none found"
        return None
    near = [
        t for t in tables if t.x0 < blk.x1 and t.x1 > blk.x0 and _gap(t, blk) <= max_gap
    ]
    return min(near, key=lambda t: _gap(t, blk), default=None)


def _ruled_table(lay, blk, *, max_gap, rule_gap):
    """A table drawn with horizontal rules (booktabs): the rule nearest the caption
    (within ``max_gap``), then the rules of the same width chained away from it, each
    within ``rule_gap`` of the last, never across another caption, never into the
    header or footer band; None if there is no such rule."""
    rules = [
        r
        for r in lay.graphics
        if r.height <= 2 * _HAIRLINE_PAD + 1
        and r.x0 < blk.x1
        and r.x1 > blk.x0
        and not lay.in_margin(r)
    ]
    near = [r for r in rules if _gap(r, blk) <= max_gap]
    if not near:
        return None
    first = min(near, key=lambda r: _gap(r, blk))
    above = first.y1 <= blk.y0 + 2
    same = sorted(
        (
            r
            for r in rules
            if abs(r.x0 - first.x0) <= _RULE_X_TOL
            and abs(r.x1 - first.x1) <= _RULE_X_TOL
            and ((r.y1 <= first.y1) if above else (r.y0 >= first.y0))
        ),
        key=lambda r: -r.y0 if above else r.y0,
    )
    captions = [r for r, t in lay.blocks if lay.is_caption_like(t) and not r.intersects(blk)]
    box, last = first, first
    for r in same:
        if r is first:
            continue
        if abs(r.y0 - last.y0) > rule_gap * lay.H:
            break
        region = _between(r, last)
        if region is not None and any((c & region).get_area() > 1 for c in captions):
            break
        box, last = box | r, r
    return box


def _table_body(lay, blk, *, max_up, max_gap, table_height, rule_gap):
    """(box, source) of a table without its caption."""
    import fitz

    inner = dict(max_height=lay.H)
    box = _detected_table(lay, blk, max_gap=max_gap)
    if box is not None:
        return _with_inner_text(lay, box, blk, **inner), "table"
    box = _ruled_table(lay, blk, max_gap=max_gap, rule_gap=rule_gap)
    if box is not None:
        return _with_inner_text(lay, box, blk, **inner), "rules"
    sides = [
        b
        for b in (
            _graphics_from_caption(lay, blk, s, max_up=max_up, max_gap=max_gap)
            for s in ("above", "below")
        )
        if b is not None
    ]
    if sides:
        box = min(sides, key=lambda b: _gap(b, blk))
        return _with_inner_text(lay, box, blk, **inner), "graphics"
    y1 = min(lay.rect.y1, blk.y1 + table_height * lay.H)
    return fitz.Rect(blk.x0, blk.y1, blk.x1, y1), "fallback"


# --------------------------------------------------------------------------- public


def figure_box(
    pdf,
    caption: str,
    *,
    page: Optional[int] = None,
    kind: Optional[str] = None,
    with_caption: bool = True,
    margin: float = DFLT_MARGIN,
    max_up: float = DFLT_MAX_UP,
    max_gap: float = DFLT_MAX_GAP,
    table_height: float = DFLT_TABLE_HEIGHT,
    rule_gap: float = DFLT_RULE_GAP,
    body_words: int = DFLT_BODY_WORDS,
) -> FigureBox:
    """Where the figure or table captioned ``caption`` is: ``FigureBox(page, box, source)``.

    :param pdf: path, bytes, file object, or an open PyMuPDF document.
    :param caption: the start of the caption, e.g. ``"Figure 3:"`` or ``"Table 2"``.
        Matched case-insensitively at the start of a text block or line; a mention in
        running text is never taken for it.
    :param page: 0-based page to look on; every page when None.
    :param kind: ``"figure"`` or ``"table"``; when None, ``"table"`` if the caption starts
        with "Tab", else ``"figure"``.
    :param with_caption: include the caption in the box.
    :param margin: white space (points) kept around the box.
    :param max_up: how far from the caption, as a fraction of the page height, a figure's
        graphics may reach.
    :param max_gap: gap (points) that separates a figure from other graphics.
    :param table_height: fraction of the page taken below a table caption when nothing is
        found next to it (``source="fallback"``).
    :param rule_gap: fraction of the page height two consecutive rules of one table may be
        apart.
    :param body_words: a text block with at least this many words is body text: a figure
        never grows across it.
    :raises LookupError: no caption starts with ``caption``.
    :raises IndexError: ``page`` is not a page of the PDF.
    """
    import fitz

    if kind is None:
        kind = "table" if _norm(caption).startswith("tab") else "figure"
    if kind not in ("figure", "table"):
        raise ValueError(f"kind must be 'figure' or 'table', not {kind!r}")
    with _opened(pdf) as doc:
        pno, blk = _find_caption(doc, caption, page)
        lay = _Layout(doc[pno], body_words=body_words)
        if kind == "figure":
            body, source = _figure_body(lay, blk, max_up=max_up, max_gap=max_gap)
        else:
            body, source = _table_body(
                lay, blk, max_up=max_up, max_gap=max_gap, table_height=table_height,
                rule_gap=rule_gap,
            )
        if body is None:
            box = fitz.Rect(blk)
        elif with_caption:
            box = body | blk
        else:
            box = fitz.Rect(body)
        box = fitz.Rect(box.x0 - margin, box.y0 - margin, box.x1 + margin, box.y1 + margin)
        return FigureBox(pno, _as_box(box & lay.rect), source)


def figure(
    pdf,
    caption: str,
    *,
    page: Optional[int] = None,
    kind: Optional[str] = None,
    zoom: float = DFLT_ZOOM,
    **box_kwargs,
) -> bytes:
    """The figure or table captioned ``caption``, as PNG bytes.

    ``zoom`` scales the rendering (1.0 is 72 dpi; the default 4.0 is 288 dpi). Every other
    keyword is passed to ``figure_box``, which says how the box is found.

    >>> png = figure("paper.pdf", "Figure 3:")  # doctest: +SKIP
    >>> png = figure("paper.pdf", "Table 2")  # a table: kind is inferred  # doctest: +SKIP
    """
    import fitz

    with _opened(pdf) as doc:
        pno, box, _ = figure_box(doc, caption, page=page, kind=kind, **box_kwargs)
        pg = doc[pno]
        clip = (fitz.Rect(box) * pg.rotation_matrix) & pg.rect
        return pg.get_pixmap(matrix=fitz.Matrix(zoom, zoom), clip=clip).tobytes("png")


# --------------------------------------------------------------------------- passages


def is_scanned(page, *, coverage: float = DFLT_SCAN_COVERAGE) -> bool:
    """Whether a PyMuPDF page is a scan: one image covers at least ``coverage`` of it."""
    import fitz

    rect = _unrotated_rect(page)
    area = rect.get_area() or 1
    covered = max(
        ((fitz.Rect(i["bbox"]) & rect).get_area() for i in page.get_image_info()),
        default=0,
    )
    return covered / area >= coverage


def _merge_lines(rects, *, tol=4.0):
    """Merge word boxes on the same line into one box per line, top to bottom."""
    rows = []
    for r in sorted(rects, key=lambda r: (round(r[1]), r[0])):
        for row in rows:
            if abs(row[1] - r[1]) < tol and abs(row[3] - r[3]) < tol:
                row[0], row[1] = min(row[0], r[0]), min(row[1], r[1])
                row[2], row[3] = max(row[2], r[2]), max(row[3], r[3])
                break
        else:
            rows.append([float(c) for c in r])
    return tuple(tuple(row) for row in rows)


def _match_tokens(words: Sequence[tuple], quote: str) -> Optional[list]:
    """The payloads of the words spelling ``quote``, in order, or None.

    ``words`` are ``(word, payload)`` in reading order; a word ending in a hyphen is
    joined to the next one (a word broken at a line end), and both payloads are kept.
    """
    target = [t for t in (_token(w) for w in quote.split()) if t]
    if not target:
        return None
    seq: list[tuple[str, list]] = []
    i = 0
    while i < len(words):
        word, payload = words[i]
        if word.rstrip().endswith("-") and i + 1 < len(words):
            joined = _token(word.rstrip()[:-1] + words[i + 1][0])
            seq.append((joined, [payload, words[i + 1][1]]))
            i += 2
            continue
        tok = _token(word)
        if tok:
            seq.append((tok, [payload]))
        i += 1
    toks = [t for t, _ in seq]
    for start in range(len(toks) - len(target) + 1):
        if toks[start : start + len(target)] == target:
            return [p for _, ps in seq[start : start + len(target)] for p in ps]
    return None


def _text_words(page):
    return [(w[4], tuple(w[:4])) for w in page.get_text("words")]


def _ocr_words(page, ocr_words, zoom):
    import fitz

    png = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom)).tobytes("png")
    # OCR boxes are pixels of the rendered (rotated) page: back to unrotated points
    back = fitz.Matrix(1 / zoom, 1 / zoom) * page.derotation_matrix
    return [(t, _as_box(fitz.Rect(b) * back)) for t, b in ocr_words(png)]


def find_passage(
    pdf,
    quote: str,
    *,
    page: Optional[int] = None,
    ocr_words: Optional[OcrWords] = None,
    ocr_zoom: float = DFLT_OCR_ZOOM,
    scan_coverage: float = DFLT_SCAN_COVERAGE,
    head_words: int = DFLT_QUOTE_HEAD_WORDS,
) -> Optional[Passage]:
    """The page and boxes of ``quote`` in ``pdf``, or None when it is not there.

    Matches the quote's words against the page's words, ignoring case, curly quotes,
    attached punctuation and words broken by an end-of-line hyphen. Every page is
    searched for the whole quote before any is searched for its first ``head_words``
    words (``source="text-head"``). On a scanned page (images cover ``scan_coverage``
    of it) the text layer's boxes are not trusted: they are read off the rendered page
    with ``ocr_words`` when given (accepted only if the OCR'd words spell the quote),
    else the page is returned with no boxes (``source="none"``). With ``ocr_words``, a
    scanned page with no text layer is OCR'd too.

    :param pdf: path, bytes, file object, or an open PyMuPDF document.
    :param quote: the text to find.
    :param page: 0-based page to look on; every page when None.
    :param ocr_words: ``png_bytes -> [(word, (x0, y0, x1, y1)), ...]`` in pixels of that
        image, for scanned pages. ``ocracy_words`` is one.
    :param ocr_zoom: rendering scale of the page given to ``ocr_words``.

    >>> p = find_passage("paper.pdf", "the results hold across models")  # doctest: +SKIP
    >>> p.page, p.boxes[0]  # doctest: +SKIP
    (4, (72.0, 310.2, 523.1, 322.0))
    """
    words = quote.split()
    head = " ".join(words[:head_words]) if len(words) > head_words else None
    with _opened(pdf) as doc:
        pages = _pages(doc, page)
        ocr_cache: dict[int, list] = {}

        def ocr_boxes(i, text):
            if ocr_words is None:
                return None
            if i not in ocr_cache:
                ocr_cache[i] = _ocr_words(doc[i], ocr_words, ocr_zoom)
            hit = _match_tokens(ocr_cache[i], text)
            return _merge_lines(hit) if hit else None

        for text, source in ((quote, "text"), (head, "text-head")):
            if text is None:
                continue
            for i in pages:
                hit = _match_tokens(_text_words(doc[i]), text)
                if not hit:
                    continue
                if not is_scanned(doc[i], coverage=scan_coverage):
                    return Passage(i, _merge_lines(hit), source)
                boxes = ocr_boxes(i, quote) or ocr_boxes(i, text)
                return Passage(i, boxes, "ocr") if boxes else Passage(i, (), "none")
        if ocr_words is not None:
            for i in pages:
                if is_scanned(doc[i], coverage=scan_coverage):
                    boxes = ocr_boxes(i, quote)
                    if boxes:
                        return Passage(i, boxes, "ocr")
    return None


def ocracy_words(png: bytes, **ocr_kwargs) -> list:
    """Word boxes of an image with ``ocracy``: an ``ocr_words`` for ``find_passage``.

    Uses ``ocracy``'s default backend unless ``backend=`` is given. A backend that reports
    only lines has each line split into words, with boxes in proportion to their length.
    Needs ``ocracy`` and an OCR backend.
    """
    try:
        import ocracy
    except ImportError as e:
        raise ImportError("ocracy_words needs ocracy: install ocracy and a backend") from e
    result = ocracy.ocr(png, **ocr_kwargs)
    words = [w for w in result.words if w.bbox is not None]
    if words:
        return [(w.text, (w.bbox.x0, w.bbox.y0, w.bbox.x1, w.bbox.y1)) for w in words]
    return [
        piece
        for line in result.lines
        if line.bbox is not None
        for piece in _split_line(line.text, _as_xyxy(line.bbox))
    ]


def _as_xyxy(bbox) -> Box:
    return (bbox.x0, bbox.y0, bbox.x1, bbox.y1)


def _split_line(text: str, box: Box) -> list:
    """A line's words, each with a share of the line's box proportional to its length.

    >>> _split_line("ab cd", (0, 0, 50, 10))
    [('ab', (0.0, 0, 20.0, 10)), ('cd', (30.0, 0, 50.0, 10))]
    """
    x0, y0, x1, y1 = box
    n = len(text) or 1
    out, pos = [], 0
    for m in re.finditer(r"\S+", text):
        a = x0 + (x1 - x0) * m.start() / n
        b = x0 + (x1 - x0) * m.end() / n
        out.append((m.group(), (a, y0, b, y1)))
        pos = m.end()
    return out
