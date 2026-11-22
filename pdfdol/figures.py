"""Crop a figure or table out of a PDF by its caption, and locate a quoted passage.

Two things a caller illustrating a paper needs:

- ``figure(pdf, "Figure 3:")`` returns the figure as PNG bytes, found by its caption.
  ``figure_box`` returns where it is (page index and box) without rendering it.
- ``find_passage(pdf, quote)`` returns the page and the boxes of a quoted passage, so it
  can be highlighted.

Pages are 0-based (like the page lists ``PdfFilesReader`` gives) and boxes are
``(x0, y0, x1, y1)`` in PDF points, origin at the top left of the page.

Scanned PDFs (a page covered by one image, its text layer made by OCR) are a known trap:
the text layer's boxes can sit tens of pixels off the glyphs. ``find_passage`` detects
such pages and, unless it is given an ``ocr_words`` function to read word boxes off the
rendered pixels (``ocracy_words`` is one, built on ``ocracy``), it returns the page with
no boxes rather than a highlight in the wrong place.

Figures on scanned pages are best effort: with no drawings to go by, a figure is
the text blocks of the OCR layer above its caption, which may miss parts of a
drawing. Needs PyMuPDF, the ``figures`` extra of pdfdol. It is imported only when called.

The caption-matching rule (a caption is a text block that *starts* with the given
caption, not a mention of it in body text) needs no PDF to check:

>>> _starts_caption("Figure 1: Growth of the thing", "Figure 1:")
True
>>> _starts_caption("Figure 10: Another one", "Figure 1")
False
>>> _starts_caption("As Figure 1: shows", "Figure 1:")
False
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable, Iterable
from contextlib import contextmanager
from typing import NamedTuple, Optional

Box = tuple  # (x0, y0, x1, y1) in PDF points
OcrWords = Callable[[bytes], Iterable[tuple]]  # png -> [(text, (x0, y0, x1, y1)), ...]

DFLT_ZOOM = 4.0
DFLT_MARGIN = 6.0  # points of white space kept around a crop
DFLT_MAX_UP = 0.65  # a figure's graphics start at most this fraction of a page above its caption
DFLT_MAX_GAP = 40.0  # points: graphics further apart than this belong to different things
DFLT_TABLE_HEIGHT = 0.35  # fraction of the page taken below a table caption when no table is detected
DFLT_BODY_WORDS = 25  # a text block with this many words is body text, not part of a figure
DFLT_SCAN_COVERAGE = 0.8  # a page whose images cover this fraction of it is a scan
DFLT_OCR_ZOOM = 3.0
DFLT_QUOTE_HEAD_WORDS = 6  # retry a long quote on its first words (PDFs hyphenate and break lines)
_LABEL_MAX_HEIGHT = 40.0  # points: taller text blocks inside a figure area are not axis labels
_LABEL_X_SLACK = 30.0  # points: axis labels may stick out of the graphics this much
_MIN_GRAPHIC_SPAN = 2.0  # points: drawings smaller than this both ways are specks
_HAIRLINE_PAD = 0.5  # points added around a zero-width or zero-height drawing
_RULE_X_TOL = 3.0  # points: table rules whose ends differ less than this are one table's


class Passage(NamedTuple):
    """Where a quote was found: its page, its boxes, and where the boxes came from.

    ``source`` is ``"text"`` (the PDF's text layer), ``"ocr"`` (OCR of the rendered
    page) or ``"none"`` (a scanned page whose text layer holds the quote but whose boxes
    cannot be trusted, and no OCR was given): then ``boxes`` is empty.
    """

    page: int
    boxes: tuple
    source: str


# --------------------------------------------------------------------------- opening


@contextmanager
def _opened(pdf):
    """An open PyMuPDF document for ``pdf`` (path, bytes or open document), closed after
    use only if it was opened here."""
    from pdfdol.checks import _open_pdf

    doc = _open_pdf(pdf)
    try:
        yield doc
    finally:
        if doc is not pdf:
            doc.close()


def _norm(s: str) -> str:
    """Normalise text for matching: NFKC, plain quotes and dashes, soft hyphens gone,
    whitespace collapsed, lower case."""
    s = unicodedata.normalize("NFKC", s)
    s = re.sub("[‘’‛]", "'", s)
    s = re.sub("[“”„]", '"', s)
    s = re.sub("[–—]", "-", s).replace("­", "")
    return re.sub(r"\s+", " ", s).strip().lower()


def _starts_caption(block_text: str, caption: str) -> bool:
    """Whether a text block starts with ``caption`` (and not with a longer number)."""
    text, cap = _norm(block_text), _norm(caption)
    if not text.startswith(cap):
        return False
    rest = text[len(cap) :]
    return not (cap[-1:].isdigit() and rest[:1].isdigit())


def _as_box(rect) -> Box:
    return (float(rect.x0), float(rect.y0), float(rect.x1), float(rect.y1))


# --------------------------------------------------------------------------- figures


def _caption_block(page, caption):
    """The rect of the text block on ``page`` that starts with ``caption``, or None."""
    import fitz

    for b in page.get_text("blocks"):
        if b[6] == 0 and _starts_caption(b[4], caption):
            return fitz.Rect(b[:4])
    return None


def _find_caption(doc, caption, page):
    """(page index, caption block rect). Prefers a block that starts with the caption on
    any page; falls back to the first mention of it anywhere."""
    import fitz

    pages = [page] if page is not None else range(len(doc))
    for i in pages:
        blk = _caption_block(doc[i], caption)
        if blk is not None:
            return i, blk
    for i in pages:
        hits = doc[i].search_for(caption)
        if hits:
            hit = hits[0]
            blocks = [fitz.Rect(b[:4]) for b in doc[i].get_text("blocks")]
            return i, next((r for r in blocks if r.intersects(hit)), hit)
    where = f"page {page}" if page is not None else "any page"
    raise LookupError(f"caption {caption!r} not found on {where}")


def _gap(a, b, *, horizontal=False):
    """The vertical (or, if ``horizontal``, the larger of both) gap between two rects."""
    v = max(a.y0 - b.y1, b.y0 - a.y1, 0)
    return max(v, a.x0 - b.x1, b.x0 - a.x1, 0) if horizontal else v


def _grow(seed, candidates, *, max_gap, horizontal=False):
    """Union ``seed`` with every candidate reachable from it through gaps of at most
    ``max_gap`` (so a figure does not swallow the one above it); None if none is."""
    box, pending, grown, reached = seed, list(candidates), True, False
    while grown:
        grown = False
        for r in list(pending):
            if _gap(r, box, horizontal=horizontal) <= max_gap:
                box = box | r
                pending.remove(r)
                grown = reached = True
    return box if reached else None


def _graphics(page):
    """Drawings and images of a page, specks and a scan's page image left out."""
    import fitz

    rects = [fitz.Rect(d["rect"]) for d in page.get_drawings()]
    page_area = page.rect.get_area() or 1
    rects += [
        fitz.Rect(i["bbox"])
        for i in page.get_image_info()
        # a scan's page image is the page, not a figure on it
        if (fitz.Rect(i["bbox"]) & page.rect).get_area() / page_area < DFLT_SCAN_COVERAGE
    ]
    out = []
    for r in rects:
        if max(r.width, r.height) < _MIN_GRAPHIC_SPAN:
            continue
        # hairlines (table rules, axes) have no area: pad them so unions keep them
        pad_x = _HAIRLINE_PAD if r.width < 2 * _HAIRLINE_PAD else 0
        pad_y = _HAIRLINE_PAD if r.height < 2 * _HAIRLINE_PAD else 0
        out.append(fitz.Rect(r.x0 - pad_x, r.y0 - pad_y, r.x1 + pad_x, r.y1 + pad_y))
    return out


def _text_blocks(page):
    import fitz

    return [(fitz.Rect(b[:4]), b[4]) for b in page.get_text("blocks") if b[6] == 0]


def _with_inner_text(page, box, blk, *, max_height=_LABEL_MAX_HEIGHT):
    """``box`` grown by the text blocks (axis labels, legends, cells) lying inside it,
    the caption block ``blk`` aside."""
    for r, _ in _text_blocks(page):
        if (
            r != blk
            and r.y0 >= box.y0 - 2
            and r.y1 <= box.y1 + 2
            and r.x0 >= box.x0 - _LABEL_X_SLACK
            and r.x1 <= box.x1 + _LABEL_X_SLACK
            and r.height < max_height
        ):
            box |= r
    return box


def _graphics_beside(page, blk, side, *, max_up, max_gap):
    """The graphics reached from the caption block ``blk`` going ``side`` ("above",
    "below", or "beside" for a side caption), or None."""
    import fitz

    H = page.rect.height
    if side == "beside":
        cands = [r for r in _graphics(page) if r.y0 < blk.y1 and r.y1 > blk.y0]
        seed = _grow(fitz.Rect(blk), cands, max_gap=max_gap, horizontal=True)
        if seed is None:
            return None
        reach = max_up * H
        rest = [
            r
            for r in _graphics(page)
            if not seed.contains(r) and r.y0 >= blk.y0 - reach and r.y1 <= blk.y1 + reach
        ]
        return _grow(seed, rest, max_gap=max_gap, horizontal=True) or seed
    col = fitz.Rect(blk.x0 - 20, 0, blk.x1 + 20, H)
    if side == "above":
        lim = blk.y0 - max_up * H
        cands = [r for r in _graphics(page) if r.y1 <= blk.y0 + 2 and r.y0 >= lim]
        seed = fitz.Rect(blk.x0, blk.y0, blk.x1, blk.y0)  # the caption's top edge
    else:
        lim = blk.y1 + max_up * H
        cands = [r for r in _graphics(page) if r.y0 >= blk.y1 - 2 and r.y1 <= lim]
        seed = fitz.Rect(blk.x0, blk.y1, blk.x1, blk.y1)  # the caption's bottom edge
    return _grow(seed, [r for r in cands if r.intersects(col)], max_gap=max_gap)


def _text_figure_box(page, blk, *, max_up, max_gap, body_words):
    """A figure drawn as positioned text (no graphics): the short text blocks climbed
    from the caption upwards, up to the first body paragraph or gap; None if none."""
    import fitz

    H = page.rect.height
    col = fitz.Rect(blk.x0 - 20, 0, blk.x1 + 20, H)
    above = sorted(
        (
            (r, t)
            for r, t in _text_blocks(page)
            if r.y1 <= blk.y0 + 1 and r.intersects(col)
        ),
        key=lambda rt: -rt[0].y1,
    )
    box = None
    for r, t in above:
        top = blk.y0 if box is None else box.y0
        if top - r.y1 > max_gap or r.y0 < blk.y0 - max_up * H:
            break
        if len(t.split()) >= body_words:
            break
        box = r if box is None else box | r
    return box


def _detected_table(page, blk, *, max_gap):
    """The table PyMuPDF detects nearest above or below ``blk``, within ``max_gap``."""
    import fitz

    try:
        tables = [fitz.Rect(t.bbox) for t in page.find_tables().tables]
    except Exception:  # find_tables needs PyMuPDF >= 1.23; any failure means "none found"
        return None
    col = fitz.Rect(blk.x0, 0, blk.x1, page.rect.height)
    near = [t for t in tables if t.intersects(col) and _gap(t, blk) <= max_gap]
    return min(near, key=lambda t: _gap(t, blk), default=None)


def _figure_body_box(page, blk, *, max_up, max_gap, body_words):
    """A figure's box without its caption: graphics above the caption, else beside it
    (a side caption), else text above it (a figure drawn as text)."""
    import fitz

    box = _graphics_beside(page, blk, "above", max_up=max_up, max_gap=max_gap)
    if box is not None:
        return _with_inner_text(page, box, blk)
    box = _graphics_beside(page, blk, "beside", max_up=max_up, max_gap=max_gap)
    if box is not None:
        return _with_inner_text(page, box, blk)
    box = _text_figure_box(page, blk, max_up=max_up, max_gap=max_gap, body_words=body_words)
    return box if box is not None else fitz.Rect(blk.x0, blk.y0, blk.x1, blk.y0)


def _ruled_block(page, blk, *, max_up, max_gap):
    """A table drawn with horizontal rules (booktabs style), above or below ``blk``:
    the rule nearest the caption (within ``max_gap``) and every rule of the same width
    on that side within ``max_up`` of the page; None if there is no such rule."""
    import fitz

    col = fitz.Rect(blk.x0 - 20, 0, blk.x1 + 20, page.rect.height)
    rules = [
        r for r in _graphics(page) if r.height <= 2 * _HAIRLINE_PAD + 1 and r.intersects(col)
    ]
    near = [r for r in rules if _gap(r, blk) <= max_gap]
    if not near:
        return None
    first = min(near, key=lambda r: _gap(r, blk))
    above = first.y1 <= blk.y0 + 2
    reach = max_up * page.rect.height
    box = fitz.Rect(first)
    for r in rules:
        same_width = abs(r.x0 - first.x0) <= _RULE_X_TOL and abs(r.x1 - first.x1) <= _RULE_X_TOL
        on_side = (r.y1 <= blk.y0 + 2) if above else (r.y0 >= blk.y1 - 2)
        if same_width and on_side and _gap(r, blk) <= reach:
            box |= r
    return box


def _table_body_box(page, blk, *, max_up, max_gap, table_height):
    """A table's box without its caption: a detected table next to the caption, else
    its rules, else the nearer of the graphics above or below it, else a fixed share of the page
    below it."""
    import fitz

    box = _detected_table(page, blk, max_gap=max_gap)
    if box is None:
        box = _ruled_block(page, blk, max_up=max_up, max_gap=max_gap)
    if box is not None:
        return _with_inner_text(page, box, blk, max_height=page.rect.height)
    sides = [
        b
        for b in (
            _graphics_beside(page, blk, s, max_up=max_up, max_gap=max_gap)
            for s in ("above", "below")
        )
        if b is not None
    ]
    if sides:
        box = min(sides, key=lambda b: _gap(b, blk))
        return _with_inner_text(page, box, blk, max_height=page.rect.height)
    H = page.rect.height
    return fitz.Rect(blk.x0, blk.y1, blk.x1, min(H, blk.y1 + table_height * H))


def figure_box(
    pdf,
    caption: str,
    *,
    page: Optional[int] = None,
    kind: str = "figure",
    with_caption: bool = True,
    margin: float = DFLT_MARGIN,
    max_up: float = DFLT_MAX_UP,
    max_gap: float = DFLT_MAX_GAP,
    table_height: float = DFLT_TABLE_HEIGHT,
    body_words: int = DFLT_BODY_WORDS,
) -> tuple:
    """Where the figure or table captioned ``caption`` is: ``(page_index, box)``.

    :param pdf: path, bytes, or an open PyMuPDF document.
    :param caption: the start of the caption, e.g. ``"Figure 3:"`` or ``"Table 2"``.
        Matched case-insensitively at the start of a text block, so a mention in body
        text is used only when no caption block starts with it.
    :param page: 0-based page to look on; every page when None.
    :param kind: ``"figure"`` or ``"table"``. A figure is the graphics above its
        caption, else beside it (a side caption), else the short text blocks above it
        (a figure drawn as text). A table is the table PyMuPDF detects next to its
        caption, else the rules of equal width next to it (booktabs), else the nearer
        graphics above or below it, else ``table_height``
        of the page below it.
    :param with_caption: include the caption in the box.
    :param margin: white space (points) kept around the box.
    :param max_up: how far from the caption, as a fraction of the page height, a
        figure's or table's graphics may reach.
    :param max_gap: gap (points) that separates a figure from other graphics.
    :param table_height: fraction of the page taken below a table caption when neither a
        table nor ruled graphics are found next to it.
    :param body_words: a text block with at least this many words is body text; it ends
        a figure drawn as text (no graphics).
    :raises LookupError: the caption is not in the PDF.
    """
    import fitz

    if kind not in ("figure", "table"):
        raise ValueError(f"kind must be 'figure' or 'table', not {kind!r}")
    with _opened(pdf) as doc:
        pno, blk = _find_caption(doc, caption, page)
        pg = doc[pno]
        if kind == "figure":
            box = _figure_body_box(
                pg, blk, max_up=max_up, max_gap=max_gap, body_words=body_words
            )
        else:
            box = _table_body_box(
                pg, blk, max_up=max_up, max_gap=max_gap, table_height=table_height
            )
        if with_caption:
            box |= blk
        box = fitz.Rect(box.x0 - margin, box.y0 - margin, box.x1 + margin, box.y1 + margin)
        return pno, _as_box(box & pg.rect)


def figure(
    pdf,
    caption: str,
    *,
    page: Optional[int] = None,
    kind: str = "figure",
    zoom: float = DFLT_ZOOM,
    **box_kwargs,
) -> bytes:
    """The figure or table captioned ``caption``, as PNG bytes.

    ``zoom`` scales the rendering (1.0 is 72 dpi; the default 4.0 is 288 dpi). Every other
    keyword is passed to ``figure_box``, which says how the box is found.

    >>> png = figure("paper.pdf", "Figure 3:")  # doctest: +SKIP
    >>> png = figure("paper.pdf", "Table 2", kind="table")  # doctest: +SKIP
    """
    import fitz

    with _opened(pdf) as doc:
        pno, box = figure_box(doc, caption, page=page, kind=kind, **box_kwargs)
        pix = doc[pno].get_pixmap(matrix=fitz.Matrix(zoom, zoom), clip=fitz.Rect(box))
        return pix.tobytes("png")


# --------------------------------------------------------------------------- passages


def is_scanned(page, *, coverage: float = DFLT_SCAN_COVERAGE) -> bool:
    """Whether a PyMuPDF page is a scan: its images cover at least ``coverage`` of it."""
    import fitz

    area = page.rect.get_area() or 1
    covered = max(
        ((fitz.Rect(i["bbox"]) & page.rect).get_area() for i in page.get_image_info()),
        default=0,
    )
    return covered / area >= coverage


def _merge_lines(rects, *, tol=4.0):
    """Merge per-word rects on the same line into one box per line."""
    rows = []
    for r in sorted(rects, key=lambda r: (round(r[1]), r[0])):
        for row in rows:
            if abs(row[1] - r[1]) < tol and abs(row[3] - r[3]) < tol:
                row[0], row[2] = min(row[0], r[0]), max(row[2], r[2])
                break
        else:
            rows.append(list(r))
    return tuple(tuple(row) for row in rows)


def _ocr_boxes(page, quote, ocr_words, *, zoom):
    """Line boxes (PDF points) of ``quote`` among the OCR'd words of ``page``; () when
    the OCR words do not contain it."""
    import fitz

    png = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom)).tobytes("png")
    words = [(_norm(t), b) for t, b in ocr_words(png) if _norm(t)]
    target = _norm(quote).split()
    if not target:
        return ()
    texts = [w for w, _ in words]
    for start in range(len(texts) - len(target) + 1):
        if texts[start : start + len(target)] == target:
            hit = [b for _, b in words[start : start + len(target)]]
            pts = [tuple(c / zoom for c in b) for b in hit]
            return _merge_lines(pts)
    return ()


def _text_hits(page, quote, *, head_words):
    hits = page.search_for(quote)
    words = quote.split()
    if not hits and len(words) > head_words:
        hits = page.search_for(" ".join(words[:head_words]))
    return hits


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

    Searches the text layer, retrying a long quote on its first ``head_words`` words
    (PDFs hyphenate and break lines). On a scanned page (images cover ``scan_coverage``
    of it) the text layer's boxes are not trusted: the boxes are read off the rendered
    page with ``ocr_words`` when given (accepted only if the OCR words contain the
    quote), else the page is returned with no boxes (``source="none"``).

    :param pdf: path, bytes, or an open PyMuPDF document.
    :param quote: the text to find.
    :param page: 0-based page to look on; every page when None.
    :param ocr_words: ``png_bytes -> [(word, (x0, y0, x1, y1)), ...]`` in pixels of that
        image, for scanned pages. ``ocracy_words`` is one.
    :param ocr_zoom: rendering scale of the page given to ``ocr_words``.

    >>> p = find_passage("paper.pdf", "the results hold across models")  # doctest: +SKIP
    >>> p.page, p.boxes[0]  # doctest: +SKIP
    (4, (72.0, 310.2, 523.1, 322.0))
    """
    with _opened(pdf) as doc:
        pages = [page] if page is not None else range(len(doc))
        for i in pages:
            pg = doc[i]
            hits = _text_hits(pg, quote, head_words=head_words)
            if not hits:
                continue
            if not is_scanned(pg, coverage=scan_coverage):
                return Passage(i, tuple(_as_box(r) for r in hits), "text")
            if ocr_words is not None:
                boxes = _ocr_boxes(pg, quote, ocr_words, zoom=ocr_zoom)
                if boxes:
                    return Passage(i, boxes, "ocr")
            return Passage(i, (), "none")
    return None


def ocracy_words(png: bytes, **ocr_kwargs) -> list:
    """Word boxes of an image with ``ocracy`` (its default backend unless ``backend=`` is
    given): an ``ocr_words`` for ``find_passage``. Needs ``ocracy`` and an OCR backend."""
    try:
        import ocracy
    except ImportError as e:
        raise ImportError("ocracy_words needs ocracy: install ocracy and a backend") from e
    result = ocracy.ocr(png, **ocr_kwargs)
    return [
        (w.text, (w.bbox.x0, w.bbox.y0, w.bbox.x1, w.bbox.y1))
        for w in result.words
        if w.bbox is not None
    ]
