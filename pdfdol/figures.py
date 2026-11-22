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
boxes rather than a highlight in the wrong place. A figure on a scanned page has no
drawings to find it by, and an OCR layer splits prose into one block per line, so it is
read off the pixels instead (``source="pixels"``, see ``pixel_figure_box``): the ink
above the caption, up to the first prose or caption above it. Best effort still: the
``scan_strategy`` keyword of ``figure_box`` takes another strategy, or ``"layout"`` to
treat the scan like any page.

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

and neither does the matching ``find_passage`` uses (case, curly quotes, punctuation,
dashes and hyphens do not matter):

>>> _match_tokens([("The", 1), ("AI’s", 2), ("repos-", 3), ("itories,", 4)], "ai's repositories")
[2, 3, 4]
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable, Iterable, Sequence
from contextlib import contextmanager
from typing import Any, NamedTuple

Box = tuple  # (x0, y0, x1, y1) in PDF points
OcrWords = Callable[[bytes], Iterable[tuple]]  # png -> [(text, (x0, y0, x1, y1)), ...]
# (page, caption box, *, max_up, max_gap) -> the figure's box without its caption, or None
ScanStrategy = Callable[..., Any]

DFLT_ZOOM = 4.0
DFLT_MARGIN = 6.0  # points of white space kept around a crop
DFLT_MAX_UP = (
    0.65  # a figure's graphics reach at most this fraction of a page from its caption
)
DFLT_MAX_GAP = (
    40.0  # points: graphics further apart than this belong to different things
)
DFLT_TABLE_HEIGHT = (
    0.35  # fraction of the page taken below a table caption when nothing is found
)
DFLT_RULE_GAP = (
    0.3  # fraction of the page: consecutive rules of one table are at most this apart
)
DFLT_BODY_WORDS = (
    25  # a text block with this many words is body text, not part of a figure
)
DFLT_SCAN_COVERAGE = 0.8  # a page whose images cover this fraction of it is a scan
DFLT_OCR_ZOOM = 3.0
DFLT_QUOTE_HEAD_WORDS = 6  # retry a long quote on its first words
DFLT_SCAN_ZOOM = 2.0  # rendering scale of a scanned page read for its figures' pixels
DFLT_INK_LEVEL = 128  # gray level (0 to 255) below which a scanned pixel is ink
DFLT_SCAN_STRATEGY = "pixels"
_SCAN_EDGE = 0.02  # fraction of the page: scanner borders and edge shadows live here
_PROSE_WORDS = 6  # a text-layer line with this many words, mostly words, is prose
_PROSE_WORDISH = (
    0.6  # share of a prose line's tokens that are words (OCR of a drawing is not)
)
_LINE_FILL = 0.6  # a printed line inks at least this share of the columns it spans
_LINE_WIDTH = 0.5  # a full printed line spans at least this share of the column
_LINE_HEIGHT = (0.3, 1.6)  # a printed line's ink is this many body font sizes tall
_DFLT_BODY_SIZE = (
    10.0  # points: the body font size assumed when a page has no text layer
)
_GUTTER_WIDTH = (
    1.0  # body font sizes: a blank strip this wide between columns is a gutter
)
_GUTTER_WINDOW = 0.15  # fraction of the page width: a gutter's distance from the middle
_MARGIN_BAND = (
    0.06  # fraction of the page height: running headers and footers live here
)
_LABEL_MAX_HEIGHT = (
    40.0  # points: taller text blocks inside a figure area are not axis labels
)
_LABEL_X_SLACK = 30.0  # points: axis labels may stick out of the graphics this much
_MIN_GRAPHIC_SPAN = 2.0  # points: drawings smaller than this both ways are specks
_HAIRLINE_PAD = 0.5  # points added around a zero-width or zero-height drawing
_RULE_X_TOL = (
    3.0  # points: table rules whose ends differ less than this are one table's
)
_COL_SLACK = 20.0  # points: graphics this close to the caption's column count as in it
_SIDE_CAPTION_MAX_WIDTH = 0.35  # fraction of the page width: a side caption is narrower
_CAPTION_LIKE = re.compile(
    r"^\s*(fig(ure)?|tab(le)?)\.?\s*([a-z]?\d+|[ivxlc]+)\b", re.IGNORECASE
)


class Passage(NamedTuple):
    """Where a quote was found: its page, its boxes, and where the boxes came from.

    ``source`` is ``"text"`` (the PDF's text layer, the whole quote), ``"text-head"``
    (only the quote's first words matched), ``"ocr"`` (OCR of the rendered page),
    ``"ocr-head"`` (OCR, the first words only), or
    ``"none"`` (a scanned page whose text layer holds the quote but whose boxes cannot be
    trusted, and OCR was not given or did not find it): then ``boxes`` is empty.
    """

    page: int
    boxes: tuple
    source: str


class FigureBox(NamedTuple):
    """Where a figure or table is: its page, its box, and how the box was found.

    ``source`` is one of ``"graphics"``, ``"text"`` (a figure drawn as text), ``"beside"``
    (a side caption), ``"pixels"`` (the ink above the caption on a scanned page), ``"table"`` (a table PyMuPDF detected), ``"rules"`` (a booktabs
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


def _pages(doc, page: int | None) -> Sequence[int]:
    if page is None:
        return range(len(doc))
    if not isinstance(page, int) or not 0 <= page < len(doc):
        raise IndexError(
            f"page {page!r} is out of range: the PDF has {len(doc)} pages, 0-based"
        )
    return [page]


def _norm(s: str) -> str:
    """Normalise text for matching: NFKC, plain quotes and dashes, soft hyphens gone,
    whitespace collapsed, lower case."""
    s = unicodedata.normalize("NFKC", s)
    s = re.sub("[‘’‛]", "'", s)
    s = re.sub("[“”„]", '"', s)
    s = re.sub("[–—]", "-", s).replace("­", "")
    return re.sub(r"\s+", " ", s).strip().lower()


def _starts_caption(text: str, caption: str) -> bool:
    """Whether ``text`` starts with ``caption`` (and not with a longer label)."""
    text, cap = _norm(text), _norm(caption)
    if not cap or not text.startswith(cap):
        return False
    rest = text[len(cap) :]
    return not (cap[-1].isalnum() and rest[:1].isalnum())


def _is_label(text: str) -> bool:
    """Whether ``text`` starts with a figure or table label used as a caption, not in prose.

    >>> [_is_label(t) for t in ("Figure 3: Growth", "TABLE II Results", "Fig. 2.", "Table 4)",
    ...                          "Figure 14 shows that", "Table 2, and")]
    [True, True, True, False, False, False]
    """
    m = _CAPTION_LIKE.match(text)
    if not m:
        return False
    rest = text[m.end() :].lstrip()
    return not rest or not (rest[0].islower() or rest[0] in "),;")


class _TextBlock(NamedTuple):
    rect: Any
    text: str
    size: float  # mean font size, weighted by characters
    split: bool  # starts mid-way through a PyMuPDF block


def _as_box(rect) -> Box:
    return (float(rect.x0), float(rect.y0), float(rect.x1), float(rect.y1))


def _text_blocks(page) -> list:
    """The page's text blocks (:class:`_TextBlock`), each PyMuPDF block split before
    every line that starts with a caption label: PyMuPDF merges a caption into the axis
    labels above it, or two side-by-side captions into one block."""
    import fitz

    out = []

    def flush(rect, lines, chars, weight, split):
        if lines:
            out.append(
                _TextBlock(
                    rect, "\n".join(lines), weight / chars if chars else 0.0, split
                )
            )

    for block in page.get_text("dict")["blocks"]:
        if block.get("type", 0) != 0:
            continue
        rect, lines, chars, weight, split = None, [], 0, 0.0, False
        for line in block.get("lines", []):
            text = "".join(s["text"] for s in line["spans"])
            if lines and _is_label(text):
                flush(rect, lines, chars, weight, split)
                rect, lines, chars, weight, split = None, [], 0, 0.0, True
            r = fitz.Rect(line["bbox"])
            rect = r if rect is None else rect | r
            lines.append(text)
            for sp in line["spans"]:
                n = len(sp["text"].strip())
                chars, weight = chars + n, weight + n * sp["size"]
        flush(rect, lines, chars, weight, split)
    return out


def _unrotated_rect(page):
    """The page's rectangle in the unrotated coordinates text and drawings use."""
    return page.rect * page.derotation_matrix


# --------------------------------------------------------------------------- page layout


class _Layout:
    """The text blocks and graphics of one page, read once."""

    def __init__(self, page, *, body_words: int, running=frozenset()):
        self.page = page
        self.rect = _unrotated_rect(page)
        self.W, self.H = self.rect.width, self.rect.height
        self.body_words = body_words
        self.blocks = _text_blocks(page)
        self.graphics = self._graphics()
        self.running = running
        sizes: dict[float, int] = {}
        for b in self.blocks:
            key = round(b.size * 2) / 2
            sizes[key] = sizes.get(key, 0) + len(b.text)
        self.body_size = max(sizes, key=sizes.get) if sizes else 0.0

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
        return _is_label(text)

    def is_body(self, block) -> bool:
        """A paragraph of body text: many words, in the page's body font size (a legend or
        a sub-caption in a smaller size belongs to its figure)."""
        return (
            len(block.text.split()) >= self.body_words
            and block.size >= self.body_size - 0.6
        )

    def barriers(self, blk):
        """Text a figure never grows across: other captions, and body paragraphs."""
        return [
            b.rect
            for b in self.blocks
            if not b.rect.intersects(blk)
            and (self.is_caption_like(b.text) or self.is_body(b))
        ]

    def in_band(self, r) -> bool:
        """In the top or bottom strip of the page, where running headers and footers sit."""
        band = _MARGIN_BAND * self.H
        return r.y1 <= self.rect.y0 + band or r.y0 >= self.rect.y1 - band

    def is_running(self, r) -> bool:
        """A rule repeated at the same place on neighbouring pages: a running header's or footer's."""
        return _rule_key(r) in self.running


def _rule_key(r) -> tuple:
    return (round(r.x0 / 4), round(r.y0 / 4), round(r.x1 / 4))


def _running_rules(doc, pno: int, *, span: int = 3) -> frozenset:
    """Hairlines found at the same place on at least two of the pages around ``pno``."""
    import fitz

    counts: dict[tuple, int] = {}
    for i in range(max(0, pno - span), min(len(doc), pno + span + 1)):
        if i == pno:
            continue
        keys = {
            _rule_key(fitz.Rect(d["rect"]))
            for d in doc[i].get_drawings()
            if fitz.Rect(d["rect"]).height <= 2 * _HAIRLINE_PAD + 1
        }
        for k in keys:
            counts[k] = counts.get(k, 0) + 1
    return frozenset(k for k, n in counts.items() if n >= 2)


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
    for r, t, *_ in lay.blocks:
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


def _caption_candidates(doc, caption, page) -> list:
    """``(page index, caption rect)`` of every text block that starts with ``caption`` as a
    label (see ``_is_label``): first those that start a PyMuPDF block, then those split
    out of one, each group in page order and top to bottom."""
    pages = _pages(doc, page)
    found = [
        (b.split, i, b.rect.y0, b.rect.x0, b.rect)
        for i in pages
        for b in _text_blocks(doc[i])
        if _is_label(b.text) and _starts_caption(b.text, caption)
    ]
    if found:
        found.sort(key=lambda f: f[:4])
        return [(i, rect) for _split, i, _y, _x, rect in found]
    mentioned = [i for i in pages if doc[i].search_for(caption)]
    where = f"page {page}" if page is not None else "any page"
    raise LookupError(
        f"no caption starts with {caption!r} on {where}"
        + (
            f"; it is only mentioned in text on page(s) {mentioned}"
            if mentioned
            else ""
        )
    )


def _column_limits(lay, blk):
    """The x-range a figure captioned ``blk`` may use: the page, unless sibling captions
    sit beside it (side-by-side figures), then the share of the page nearest to it."""
    lo, hi = lay.rect.x0, lay.rect.x1
    c = (blk.x0 + blk.x1) / 2
    for r, t, *_ in lay.blocks:
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
        cands = [
            r for r in lay.graphics if r.y1 <= blk.y0 + 2 and r.y0 >= blk.y0 - reach
        ]
        seed = fitz.Rect(blk.x0, blk.y0 - 1, blk.x1, blk.y0)
    else:
        cands = [
            r for r in lay.graphics if r.y0 >= blk.y1 - 2 and r.y1 <= blk.y1 + reach
        ]
        seed = fitz.Rect(blk.x0, blk.y1, blk.x1, blk.y1 + 1)
    graphics = [r for r in cands if r.x0 >= lo - 1 and r.x1 <= hi + 1]
    # legends and sub-captions (text smaller than the body's) bridge a figure to its caption
    small = [
        b.rect
        for b in lay.blocks
        if b.size < lay.body_size - 0.6
        and not lay.is_caption_like(b.text)
        and not b.rect.intersects(blk)
        and b.rect.x0 >= lo - 1
        and b.rect.x1 <= hi + 1
        and (
            (b.rect.y1 <= blk.y0 + 2 and b.rect.y0 >= blk.y0 - reach)
            if side == "above"
            else (b.rect.y0 >= blk.y1 - 2 and b.rect.y1 <= blk.y1 + reach)
        )
    ]
    cands = graphics + small
    col = fitz.Rect(blk.x0 - _COL_SLACK, lay.rect.y0, blk.x1 + _COL_SLACK, lay.rect.y1)
    barriers = lay.barriers(blk)
    first = _grow(
        seed,
        [r for r in cands if r.intersects(col)],
        max_gap=max_gap,
        barriers=barriers,
    )
    if first is None:
        return None
    rest = [r for r in cands if not first.contains(r)]
    box = first | (_grow(first, rest, max_gap=max_gap, barriers=barriers) or first)
    # small text alone is not a figure
    return box if any(box.contains(g) for g in graphics) else None


def _text_figure_box(lay, blk, *, max_up, max_gap):
    """A figure drawn as positioned text: the short text blocks climbed from the caption
    upwards, up to the first caption, body paragraph or gap; None if none."""
    import fitz

    col = fitz.Rect(blk.x0 - _COL_SLACK, lay.rect.y0, blk.x1 + _COL_SLACK, lay.rect.y1)
    above = sorted(
        (b for b in lay.blocks if b.rect.y1 <= blk.y0 + 1 and b.rect.intersects(col)),
        key=lambda b: -b.rect.y1,
    )
    box, lines = None, 0
    for b in above:
        r = b.rect
        top = blk.y0 if box is None else box.y0
        if top - r.y1 > max_gap or r.y0 < blk.y0 - max_up * lay.H:
            break
        if lay.is_body(b) or lay.is_caption_like(b.text) or lay.in_band(r):
            break
        box = r if box is None else box | r
        lines += b.text.count("\n") + 1
    # one line above a caption is a heading or a stray label, not a figure
    return box if lines >= 2 else None


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
    # a narrow caption with graphics level with it is a side caption, whatever is above it
    narrow = blk.width < _SIDE_CAPTION_MAX_WIDTH * lay.W
    beside = _graphics_beside(lay, blk, max_up=max_up, max_gap=max_gap)
    if beside is not None and narrow:
        return _with_inner_text(lay, beside, blk), "beside"
    box = _text_figure_box(lay, blk, max_up=max_up, max_gap=max_gap)
    if box is not None:
        return box, "text"
    if beside is not None:
        return _with_inner_text(lay, beside, blk), "beside"
    return None, "caption-only"


# --------------------------------------------------------------------------- scanned pages


class _Band(NamedTuple):
    """A run of rows holding ink, in page points, with the share of its span it inks."""

    x0: float
    y0: float
    x1: float
    y1: float
    fill: float


def _ink_bands(page, clip, *, zoom, ink) -> list:
    """The :class:`_Band` s of ``clip`` on ``page``, top to bottom: maximal runs of rows
    holding ink (a pixel darker than ``ink``), split by blank rows."""
    import fitz

    pix = page.get_pixmap(
        matrix=fitz.Matrix(zoom, zoom), clip=clip, colorspace=fitz.csGRAY, alpha=False
    )
    w, h, stride, data = pix.width, pix.height, pix.stride, pix.samples
    ox, oy = pix.x, pix.y  # the clip's top left, in pixels of the zoomed page
    dark = bytes(1 if v < ink else 0 for v in range(256))
    min_ink = max(1, round(zoom))  # fewer dark pixels than this in a row is noise
    bands, run = [], None

    def close(run):
        r0, r1, c0, c1, cols = run
        # every byte of a row is 0 or 1, so each inked column is one set bit
        inked = bin(cols).count("1")  # noqa: FURB161 - int.bit_count needs 3.10
        bands.append(
            _Band(
                (ox + c0) / zoom,
                (oy + r0) / zoom,
                (ox + c1 + 1) / zoom,
                (oy + r1 + 1) / zoom,
                inked / (c1 - c0 + 1),
            )
        )

    for r in range(h):
        row = data[r * stride : r * stride + w].translate(dark)
        if row.count(1) < min_ink:
            if run is not None:
                close(run)
                run = None
            continue
        c0, c1, cols = row.find(1), row.rfind(1), int.from_bytes(row, "big")
        if run is None:
            run = [r, r, c0, c1, cols]
        else:
            run[1], run[2], run[3], run[4] = (
                r,
                min(run[2], c0),
                max(run[3], c1),
                run[4] | cols,
            )
    if run is not None:
        close(run)
    return bands


def _is_prose_line(lay, block) -> bool:
    """Whether a text block is prose: a body paragraph, or (an OCR layer gives one block per
    line) one line of several words that read as words, not as OCR of a drawing."""
    if lay.is_body(block):
        return True
    tokens = block.text.split()
    if "\n" in block.text.strip() or len(tokens) < _PROSE_WORDS:
        return False
    wordish = sum(1 for t in tokens if re.fullmatch(r"[^\W\d_]{2,}[.,;:]?", t))
    return wordish >= _PROSE_WORDISH * len(tokens)


def _scan_columns(lay, blk, top):
    """The x-range to read for the figure above ``blk``: the caption's share of the page,
    less the prose beside it (the other column of a two-column page) and the scan's edges.
    """
    lo, hi = _column_limits(lay, blk)
    edge = _SCAN_EDGE * lay.W
    lo, hi = max(lo, lay.rect.x0 + edge), min(hi, lay.rect.x1 - edge)
    for b in lay.blocks:
        r = b.rect
        if r.y1 <= top or r.y0 >= blk.y0 or not _is_prose_line(lay, b):
            continue
        if r.x0 >= blk.x1:
            hi = min(hi, r.x0 - 1)
        elif r.x1 <= blk.x0:
            lo = max(lo, r.x1 + 1)
    return lo, hi


def _column_gutter(page, clip, *, zoom, ink, min_width, window):
    """The x (points) of the middle of the blank vertical strip, at least ``min_width``
    points wide, running the whole height of ``clip`` with ink on both sides, within
    ``window`` of the page's middle and nearest to it: a two-column page's gutter.
    None if there is none."""
    import fitz

    pix = page.get_pixmap(
        matrix=fitz.Matrix(zoom, zoom), clip=clip, colorspace=fitz.csGRAY, alpha=False
    )
    data, dark, cols = pix.samples, bytes(1 if v < ink else 0 for v in range(256)), 0
    for r in range(pix.height):
        row = data[r * pix.stride : r * pix.stride + pix.width]
        cols |= int.from_bytes(row.translate(dark), "big")
    inked = cols.to_bytes(pix.width, "big")
    mid = (page.rect.x0 + page.rect.x1) / 2
    best, c = None, 0
    while c < pix.width:
        if inked[c]:
            c += 1
            continue
        end = inked.find(1, c)
        end = pix.width if end < 0 else end
        x0, x1 = (pix.x + c) / zoom, (pix.x + end) / zoom
        centre = (x0 + x1) / 2
        inner = c > 0 and end < pix.width  # ink on both sides: a gutter, not a margin
        if inner and x1 - x0 >= min_width and abs(centre - mid) <= window:
            if best is None or abs(centre - mid) < abs(best - mid):
                best = centre
        c = end
    return best


def _caption_ink(lay, blk, *, zoom=DFLT_SCAN_ZOOM, ink=DFLT_INK_LEVEL):
    """``blk`` widened to the ink of its own line on a scan (an OCR box can stop short of
    the glyphs): the runs of inked columns in its rows that it overlaps, joined across
    gaps narrower than a few letters."""
    import fitz

    edge = _SCAN_EDGE * lay.W
    clip = fitz.Rect(lay.rect.x0 + edge, blk.y0, lay.rect.x1 - edge, blk.y1)
    if clip.is_empty:
        return blk
    pix = lay.page.get_pixmap(
        matrix=fitz.Matrix(zoom, zoom), clip=clip, colorspace=fitz.csGRAY, alpha=False
    )
    dark = bytes(1 if v < ink else 0 for v in range(256))
    cols = 0
    data = pix.samples  # a copy: read it once
    for r in range(pix.height):
        row = data[r * pix.stride : r * pix.stride + pix.width]
        cols |= int.from_bytes(row.translate(dark), "big")
    inked = cols.to_bytes(pix.width, "big")
    size = lay.body_size if lay.body_size >= 4 else _DFLT_BODY_SIZE
    join = size * zoom  # a gap this wide (pixels) is inside a line, not between columns
    w = pix.width
    x0 = min(w, max(0, int(blk.x0 * zoom) - pix.x))
    x1 = min(w, max(0, int(blk.x1 * zoom) - pix.x))
    while True:  # rightwards, word by word, while the next ink is near
        nxt = inked.find(1, x1)
        if nxt < 0 or nxt - x1 > join:
            break
        end = inked.find(0, nxt)
        x1 = w if end < 0 else end
    while True:  # leftwards
        prv = inked.rfind(1, 0, x0)
        if prv < 0 or x0 - prv > join:
            break
        x0 = inked.rfind(0, 0, prv) + 1
    return fitz.Rect((x0 + pix.x) / zoom, blk.y0, (x1 + pix.x) / zoom, blk.y1) | blk


def pixel_figure_box(
    page,
    caption_box: Box,
    *,
    max_up: float = DFLT_MAX_UP,
    max_gap: float = DFLT_MAX_GAP,
    body_words: int = DFLT_BODY_WORDS,
    zoom: float = DFLT_SCAN_ZOOM,
    ink: int = DFLT_INK_LEVEL,
) -> Box | None:
    """The box of the figure above ``caption_box`` on a scanned PyMuPDF ``page``, read off
    its pixels, without the caption; None when there is no ink above the caption.

    The page is rendered in gray above the caption and cut into bands of rows holding
    ink. The figure is the bands climbed from the caption upwards, each within
    ``max_gap`` points of the last, up to the first that is text: another caption or a
    prose line in the text layer, or a run of printed lines in the pixels (a band one
    line tall that inks most of its span, under a full line). Boxes, arrows and labels
    inside a figure are ink like any other, so a figure of separate boxes comes whole.
    The default ``scan_strategy`` of ``figure_box``; its signature is the one a
    replacement takes (``page, caption_box, *, max_up, max_gap``).

    :param page: a PyMuPDF page; its rotation must be 0 (else None: use the layout).
    :param caption_box: the caption's ``(x0, y0, x1, y1)``, from the page's text layer.
    :param zoom: rendering scale (2.0 is 144 dpi).
    :param ink: gray level (0 to 255) below which a pixel is ink.
    """
    import fitz

    lay = _Layout(page, body_words=body_words)
    return _pixel_body(
        lay, fitz.Rect(caption_box), max_up=max_up, max_gap=max_gap, zoom=zoom, ink=ink
    )


def _pixel_body(lay, blk, *, max_up, max_gap, zoom=DFLT_SCAN_ZOOM, ink=DFLT_INK_LEVEL):
    """``pixel_figure_box`` on a page already read into a ``_Layout``."""
    import fitz

    page = lay.page
    if page.rotation:  # the pixels would not be in the text layer's coordinates
        return None
    top = max(lay.rect.y0 + _SCAN_EDGE * lay.H, blk.y0 - max_up * lay.H)
    lo, hi = _scan_columns(lay, blk, top)
    if blk.y1 <= top or hi <= lo:
        return None
    # a caption on one side of a two-column page's gutter: its figure stays on that side
    size = lay.body_size if lay.body_size >= 4 else _DFLT_BODY_SIZE
    gutter = _column_gutter(
        page,
        fitz.Rect(lo, top, hi, blk.y0),
        zoom=zoom,
        ink=ink,
        min_width=_GUTTER_WIDTH * size,
        window=_GUTTER_WINDOW * lay.W,
    )
    if gutter is not None and blk.x1 <= gutter:
        hi = gutter
    elif gutter is not None and blk.x0 >= gutter:
        lo = gutter
    bands = _ink_bands(page, fitz.Rect(lo, top, hi, blk.y1), zoom=zoom, ink=ink)
    # the caption's own ink tells where its glyphs start (an OCR box can be points off)
    cap = [b for b in bands if b.y1 > blk.y0 and b.y0 < blk.y1]
    cap_top = min((b.y0 for b in cap), default=blk.y0)
    if cap_top < blk.y0 - blk.height:  # the caption's ink runs into the figure's:
        cap_top = blk.y0  # read again, cut at the caption's top
        bands = _ink_bands(page, fitz.Rect(lo, top, hi, cap_top), zoom=zoom, ink=ink)
    # (a band cut at the caption's top may end a pixel below it)
    above = sorted(
        (b for b in bands if b.y1 <= cap_top + 1 / zoom), key=lambda b: -b.y1
    )

    width = hi - lo
    text = [
        b.rect
        for b in lay.blocks
        if not b.rect.intersects(blk)
        and (lay.is_caption_like(b.text) or _is_prose_line(lay, b))
    ]

    def line_tall(b):
        return _LINE_HEIGHT[0] * size <= b.y1 - b.y0 <= _LINE_HEIGHT[1] * size

    def full_line(b):
        return (
            line_tall(b) and b.fill >= _LINE_FILL and b.x1 - b.x0 >= _LINE_WIDTH * width
        )

    def is_text(i):
        b = above[i]
        # text-layer prose covering most of the band's height (a sentence-like label
        # inside a tall figure band does not make the band text)
        covered = sum(
            max(0.0, min(b.y1, r.y1) - max(b.y0, r.y0))
            for r in text
            if r.x0 < b.x1 and r.x1 > b.x0
        )
        if covered > 0.5 * (b.y1 - b.y0):
            return True
        if not (line_tall(b) and b.fill >= _LINE_FILL) or i + 1 >= len(above):
            return False
        up = above[i + 1]  # a printed line under another one is a paragraph
        return full_line(up) and b.y0 - up.y1 <= size

    def speck(b):
        return max(b.x1 - b.x0, b.y1 - b.y0) < _MIN_GRAPHIC_SPAN

    box, reach = None, cap_top
    for i, b in enumerate(above):
        if reach - b.y1 > max_gap or is_text(i):
            break
        if speck(b):
            continue
        r = fitz.Rect(b.x0, b.y0, b.x1, b.y1)
        box = r if box is None else box | r
        reach = b.y0
    return None if box is None else _as_box(box)


# --------------------------------------------------------------------------- tables


def _detected_table(lay, blk, *, max_gap):
    """The table PyMuPDF detects nearest above or below ``blk``, within ``max_gap``."""
    import fitz

    try:
        tables = [fitz.Rect(t.bbox) for t in lay.page.find_tables().tables]
    except (
        Exception
    ):  # noqa: BLE001 - find_tables needs PyMuPDF >= 1.23; any failure: none found
        return None
    near = [
        t for t in tables if t.x0 < blk.x1 and t.x1 > blk.x0 and _gap(t, blk) <= max_gap
    ]
    return min(near, key=lambda t: _gap(t, blk), default=None)


def _joined_rules(graphics) -> list:
    """The horizontal hairlines, with collinear segments that touch joined into one rule
    (tables often draw a row's rule one cell at a time)."""
    segs = sorted(
        (r for r in graphics if r.height <= 2 * _HAIRLINE_PAD + 1),
        key=lambda r: (round(r.y0), r.x0),
    )
    out = []
    for r in segs:
        last = out[-1] if out else None
        if last is not None and abs(last.y0 - r.y0) < 1 and r.x0 <= last.x1 + 2:
            out[-1] = last | r
        else:
            out.append(r)
    return out


def _ruled_table(lay, blk, *, max_gap, rule_gap):
    """A table drawn with horizontal rules (booktabs): the rule nearest the caption
    (within ``max_gap``), then the rules of the same width chained away from it, each
    within ``rule_gap`` of the last, never across another caption, never a running
    header's or footer's rule; then the frames (shaded or boxed panels) it cuts through.
    None if there is no such rule."""
    rules = [
        r
        for r in _joined_rules(lay.graphics)
        if r.x0 < blk.x1 and r.x1 > blk.x0 and not lay.is_running(r)
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
    captions = [
        r for r, t, *_ in lay.blocks if lay.is_caption_like(t) and not r.intersects(blk)
    ]
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
    page_area = lay.rect.get_area() or 1
    for g in lay.graphics:
        if (
            g.height > 3
            and g.width > 3
            and g.intersects(box)
            and g.get_area() < 0.5 * page_area
        ):
            box |= g
    return box


def _table_body(lay, blk, *, max_up, max_gap, table_height, rule_gap):
    """(box, source) of a table without its caption."""
    import fitz

    inner = {"max_height": lay.H}
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
    page: int | None = None,
    kind: str | None = None,
    with_caption: bool = True,
    margin: float = DFLT_MARGIN,
    max_up: float = DFLT_MAX_UP,
    max_gap: float = DFLT_MAX_GAP,
    table_height: float = DFLT_TABLE_HEIGHT,
    rule_gap: float = DFLT_RULE_GAP,
    body_words: int = DFLT_BODY_WORDS,
    scan_strategy: str | ScanStrategy = DFLT_SCAN_STRATEGY,
) -> FigureBox:
    """Where the figure or table captioned ``caption`` is: ``FigureBox(page, box, source)``.

    :param pdf: path, bytes, file object, or an open PyMuPDF document.
    :param caption: the start of the caption, e.g. ``"Figure 3:"`` or ``"Table 2"``.
        Matched case-insensitively at the start of a text block or line, and only where
        the label reads as a caption ("Table 2 shows" and "Table 2)" are prose). Of several
        matches, the first whose figure or table is found is used.
    :param page: 0-based page to look on; every page when None.
    :param kind: ``"figure"`` or ``"table"``; when None, ``"table"`` if the caption starts
        with "Tab", else ``"figure"``.
    :param with_caption: include the caption in the box. Without it, a caption with
        nothing found next to it raises ``LookupError`` (there is no figure to return).
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
    :param scan_strategy: how a figure on a scanned page (see ``is_scanned``) is found:
        ``"pixels"`` (``pixel_figure_box``, ``source="pixels"``), ``"layout"`` (as on any
        page), or a callable with ``pixel_figure_box``'s signature. It runs only when
        the layout finds no graphics for the figure (a scan has none to find; a page
        with drawings over a page-sized image keeps its ``"graphics"`` box), and when
        it finds nothing the layout's result stands. Tables are always found from the
        layout.
    :raises LookupError: no caption starts with ``caption`` (or, ``with_caption=False``,
        nothing was found next to it).
    :raises IndexError: ``page`` is not a page of the PDF.
    """
    import fitz

    if kind is None:
        kind = "table" if _norm(caption).startswith("tab") else "figure"
    if kind not in ("figure", "table"):
        raise ValueError(f"kind must be 'figure' or 'table', not {kind!r}")
    if scan_strategy == "pixels":
        scan_strategy = pixel_figure_box
    elif scan_strategy != "layout" and not callable(scan_strategy):
        raise ValueError(
            "scan_strategy must be 'pixels', 'layout' or a callable, "
            f"not {scan_strategy!r}"
        )
    weak = ("caption-only", "fallback")
    with _opened(pdf) as doc:
        tried = []
        for pno, blk in _caption_candidates(doc, caption, page):
            lay = _Layout(
                doc[pno], body_words=body_words, running=_running_rules(doc, pno)
            )
            if kind == "figure":
                body, source = _figure_body(lay, blk, max_up=max_up, max_gap=max_gap)
                # graphics found: the page has drawings, whatever image lies under them
                if (
                    callable(scan_strategy)
                    and source not in ("graphics", "beside")
                    and is_scanned(doc[pno])
                ):
                    if scan_strategy is pixel_figure_box:  # the page is read already
                        found = _pixel_body(lay, blk, max_up=max_up, max_gap=max_gap)
                    else:
                        found = scan_strategy(
                            doc[pno], _as_box(blk), max_up=max_up, max_gap=max_gap
                        )
                    if found is not None and not fitz.Rect(found).is_empty:
                        body, source = fitz.Rect(found), "pixels"
                        blk = _caption_ink(lay, blk)
            else:
                body, source = _table_body(
                    lay,
                    blk,
                    max_up=max_up,
                    max_gap=max_gap,
                    table_height=table_height,
                    rule_gap=rule_gap,
                )
            tried.append((pno, blk, lay, body, source))
            if source not in weak:
                break
        pno, blk, lay, body, source = next(
            (t for t in tried if t[4] not in weak), tried[0]
        )
        if body is None and not with_caption:
            raise LookupError(
                f"nothing found next to the caption {caption!r} on page {pno}; "
                "with_caption=True returns the caption's own box"
            )
        if body is None:
            box = fitz.Rect(blk)
        elif with_caption:
            box = body | blk
        else:
            box = fitz.Rect(body)
        box = fitz.Rect(
            box.x0 - margin, box.y0 - margin, box.x1 + margin, box.y1 + margin
        )
        return FigureBox(pno, _as_box(box & lay.rect), source)


def figure(
    pdf,
    caption: str,
    *,
    page: int | None = None,
    kind: str | None = None,
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


def _alnum(text: str) -> str:
    """``text`` as matching sees it: normalised, every space, hyphen, dash and punctuation gone."""
    return re.sub(r"[\W_]+", "", _norm(text))


def _match_tokens(words: Sequence[tuple], quote: str) -> list | None:
    """The payloads of the words spelling ``quote``, in order, or None.

    ``words`` are ``(word, payload)`` in reading order. Both sides are compared as their
    letters and digits only, so case, curly quotes, attached punctuation, dashes, and
    hyphens (a compound, a suspended "pre-", or a word broken at a line end) do not
    matter.
    """
    target = _alnum(quote)
    if not target:
        return None
    stream, owner = [], []
    for k, (word, _) in enumerate(words):
        chars = _alnum(word)
        stream.append(chars)
        owner.extend([k] * len(chars))
    at = "".join(stream).find(target)
    if at < 0:
        return None
    hit = sorted(set(owner[at : at + len(target)]))
    return [words[k][1] for k in hit]


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
    page: int | None = None,
    ocr_words: OcrWords | None = None,
    ocr_zoom: float = DFLT_OCR_ZOOM,
    scan_coverage: float = DFLT_SCAN_COVERAGE,
    head_words: int = DFLT_QUOTE_HEAD_WORDS,
) -> Passage | None:
    """The page and boxes of ``quote`` in ``pdf``, or None when it is not there.

    Matches the quote against the page's words by their letters and digits, so case,
    curly quotes, punctuation, dashes and hyphens (compounds, and words broken at a line
    end) do not matter. Every page is
    searched for the whole quote before any is searched for its first ``head_words``
    words (``source="text-head"``). On a scanned page (images cover ``scan_coverage``
    of it) the text layer's boxes are not trusted: they are read off the rendered page
    with ``ocr_words`` when given (accepted only if the OCR'd words spell the quote),
    else the page is returned with no boxes (``source="none"``). With ``ocr_words``, a
    scanned page with no text layer at all is OCR'd too (only those: OCR is slow).

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
                boxes = ocr_boxes(i, quote)
                if boxes:
                    return Passage(i, boxes, "ocr")
                boxes = ocr_boxes(i, text) if text is not quote else None
                return (
                    Passage(i, boxes, "ocr-head") if boxes else Passage(i, (), "none")
                )
        if ocr_words is not None:
            # a scan with no text layer at all: nothing above could have found the quote
            for i in pages:
                pg = doc[i]
                if is_scanned(pg, coverage=scan_coverage) and not pg.get_text().strip():
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
        raise ImportError(
            "ocracy_words needs ocracy: install ocracy and a backend"
        ) from e
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
    out = []
    for m in re.finditer(r"\S+", text):
        a = x0 + (x1 - x0) * m.start() / n
        b = x0 + (x1 - x0) * m.end() / n
        out.append((m.group(), (a, y0, b, y1)))
    return out
