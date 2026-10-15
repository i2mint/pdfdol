"""Bundle several PDFs into one, with a contents page, per-document headers and bookmarks.

``concat_pdfs`` just joins documents. ``bundle_pdf_bytes`` keeps track of which
page each document starts on while joining, which is what makes these possible:

- ``toc``: a contents page (several pages if needed) whose lines link to the
  documents' first pages;
- ``doc_header``: a band naming the document, added *above* its first page, so
  no content is covered;
- ``outline``: one bookmark per document.

Rendering text needs ``reportlab`` (``pip install pdfdol[bundle]``). Without
``toc`` and ``doc_header``, only ``pypdf`` is used.

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
"""

from __future__ import annotations

import io
from collections.abc import Callable, Iterable, Mapping
from typing import NamedTuple, Union

import pypdf
from pypdf.generic import (
    ArrayObject,
    DictionaryObject,
    FloatObject,
    NameObject,
    NumberObject,
    RectangleObject,
)

#: Page sizes in points (1/72 inch), portrait.
PAGE_SIZES = {
    "A3": (841.89, 1190.55),
    "A4": (595.28, 841.89),
    "A5": (419.53, 595.28),
    "letter": (612.0, 792.0),
    "legal": (612.0, 1008.0),
}

DFLT_MARGIN = 36
DFLT_HEADER_HEIGHT = 30
DFLT_TOC_TITLE = "Contents"
DFLT_FONT, DFLT_FONT_BOLD = "Helvetica", "Helvetica-Bold"

PageSize = Union[str, tuple]


class Entry(NamedTuple):
    """One document in a bundle. ``start_page`` is 1-based, in the final PDF."""

    key: str
    start_page: int
    n_pages: int


#: A contents renderer maps ``(entries, title)`` to the contents PDF bytes, or to
#: ``(pdf_bytes, link_rects)`` where ``link_rects[i]`` is ``(toc_page_index, (x0, y0, x1, y1))``
#: for entry ``i``, making that region a link to the entry's first page.
TocRenderer = Callable[[list, str], Union[bytes, tuple]]


def _require_reportlab(feature):
    try:
        import reportlab  # noqa: F401
    except ImportError as e:
        raise ImportError(
            f"{feature} needs reportlab: pip install reportlab (or pdfdol[bundle])"
        ) from e


def resolve_page_size(page_size: PageSize) -> tuple[float, float]:
    """Name (case-insensitive, see ``PAGE_SIZES``) or ``(w, h)`` points -> ``(w, h)``.

    >>> resolve_page_size('a4')
    (595.28, 841.89)
    >>> resolve_page_size((100, 200))
    (100.0, 200.0)
    """
    if isinstance(page_size, str):
        by_lower = {k.lower(): v for k, v in PAGE_SIZES.items()}
        try:
            return by_lower[page_size.lower()]
        except KeyError:
            raise ValueError(
                f"Unknown page size {page_size!r}; use one of {sorted(PAGE_SIZES)} or (w, h)"
            ) from None
    w, h = page_size
    return float(w), float(h)


def fit_pdf_to_page(
    pdf_bytes: bytes,
    page_size: PageSize = "A4",
    *,
    margin: float = DFLT_MARGIN,
    landscape_if_wider: bool = True,
) -> bytes:
    """Put each page of ``pdf_bytes`` on a ``page_size`` page, scaled to fit and centered.

    A page wider than tall gets a landscape page when ``landscape_if_wider``.

    >>> import io, pypdf
    >>> w = pypdf.PdfWriter(); _ = w.add_blank_page(width=1000, height=500)
    >>> buf = io.BytesIO(); _ = w.write(buf)
    >>> out = fit_pdf_to_page(buf.getvalue(), 'A4')
    >>> [round(float(v)) for v in pypdf.PdfReader(io.BytesIO(out)).pages[0].mediabox[2:]]
    [842, 595]
    """
    pw0, ph0 = resolve_page_size(page_size)
    writer = pypdf.PdfWriter()
    for src in pypdf.PdfReader(io.BytesIO(pdf_bytes)).pages:
        src.transfer_rotation_to_content()
        sw, sh = float(src.mediabox.width), float(src.mediabox.height)
        pw, ph = (max(pw0, ph0), min(pw0, ph0)) if (landscape_if_wider and sw > sh) else (
            min(pw0, ph0),
            max(pw0, ph0),
        )
        scale = min((pw - 2 * margin) / sw, (ph - 2 * margin) / sh)
        dx = (pw - sw * scale) / 2 - float(src.mediabox.left) * scale
        dy = (ph - sh * scale) / 2 - float(src.mediabox.bottom) * scale
        page = writer.add_blank_page(width=pw, height=ph)
        page.merge_transformed_page(
            src, pypdf.Transformation().scale(scale).translate(dx, dy)
        )
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def add_header_band(
    page,
    text: str,
    *,
    height: float = DFLT_HEADER_HEIGHT,
    margin: float = DFLT_MARGIN,
    font: str = DFLT_FONT_BOLD,
    font_size: float = 9,
    gray: float = 0.92,
) -> None:
    """Extend ``page`` upward by ``height`` and draw ``text`` in the new band (in place)."""
    _require_reportlab("Document headers")
    from reportlab.pdfgen import canvas

    page.transfer_rotation_to_content()
    box = page.mediabox
    left, bottom, right, top = (
        float(v) for v in (box.left, box.bottom, box.right, box.top)
    )
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(right - left, height))
    c.setFillGray(gray)
    c.rect(0, 0, right - left, height, stroke=0, fill=1)
    c.setFillGray(0)
    c.setFont(font, font_size)
    c.drawString(margin / 2, height / 2 - font_size / 3, text)
    c.save()
    band = pypdf.PdfReader(io.BytesIO(buf.getvalue())).pages[0]
    page.merge_translated_page(band, left, top, expand=True)
    page.mediabox = RectangleObject([left, bottom, right, top + height])
    page.cropbox = page.mediabox


def render_contents_pdf(
    entries: list,
    title: str = DFLT_TOC_TITLE,
    *,
    page_size: PageSize = "A4",
    margin: float = DFLT_MARGIN,
    line_height: float = 18,
    font: str = DFLT_FONT,
    title_font: str = DFLT_FONT_BOLD,
    font_size: float = 10,
    title_size: float = 16,
) -> tuple:
    """Default ``TocRenderer``: a title, then one line per entry with its page range at right.

    Returns ``(pdf_bytes, link_rects)``.
    """
    _require_reportlab("A contents page")
    from reportlab.pdfgen import canvas

    pw, ph = resolve_page_size(page_size)
    left, right = margin * 1.5, pw - margin * 1.5
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(pw, ph))
    y = ph - 2 * margin
    c.setFont(title_font, title_size)
    c.drawString(left, y, title)
    y -= 2 * line_height
    page_idx, rects = 0, []
    for i, (key, start, n_pages) in enumerate(entries, 1):
        if y < 2 * margin:
            c.showPage()
            page_idx += 1
            y = ph - 2 * margin
        c.setFont(font, font_size)
        c.drawString(left, y, f"{i:>2}.  {key}")
        last = start + n_pages - 1
        c.drawRightString(right, y, f"p. {start}" + (f"–{last}" if n_pages > 1 else ""))
        rects.append((page_idx, (left, y - 4, right, y + font_size + 2)))
        y -= line_height
    c.save()
    return buf.getvalue(), rects


def _header_text_func(doc_header) -> Callable | None:
    if doc_header is None or doc_header is False:
        return None
    if doc_header is True:
        doc_header = "{key}"
    if isinstance(doc_header, str):
        template = doc_header
        return lambda entry: template.format(
            key=entry.key,
            start_page=entry.start_page,
            n_pages=entry.n_pages,
        )
    return lambda entry: doc_header(entry.key)


def _layout(toc_renderer, readers, keys, title):
    """Render the contents so that its own length is consistent with the start pages."""
    toc_n = 1
    for _ in range(10):
        entries, start = [], toc_n + 1
        for key, reader in zip(keys, readers):
            entries.append(Entry(key, start, len(reader.pages)))
            start += len(reader.pages)
        rendered = toc_renderer(entries, title)
        toc_bytes, rects = rendered if isinstance(rendered, tuple) else (rendered, [])
        n = len(pypdf.PdfReader(io.BytesIO(toc_bytes)).pages)
        if n == toc_n:
            return entries, toc_bytes, rects
        toc_n = n
    raise RuntimeError("Contents page length did not converge")


def _add_internal_link(writer, page_idx, rect, target_idx):
    """Link ``rect`` on page ``page_idx`` to page ``target_idx``.

    The destination is an indirect reference to the page, as viewers require
    (an integer page index is only valid for links to other files).
    """
    annot = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Annot"),
            NameObject("/Subtype"): NameObject("/Link"),
            NameObject("/Rect"): ArrayObject(FloatObject(v) for v in rect),
            NameObject("/Border"): ArrayObject(NumberObject(0) for _ in range(3)),
            NameObject("/Dest"): ArrayObject(
                [writer.pages[target_idx].indirect_reference, NameObject("/Fit")]
            ),
        }
    )
    page = writer.pages[page_idx]
    if "/Annots" not in page:
        page[NameObject("/Annots")] = ArrayObject()
    page["/Annots"].append(writer._add_object(annot))


def bundle_pdf_bytes(
    items: Mapping | Iterable,
    *,
    toc: bool | TocRenderer = False,
    doc_header: None | bool | str | Callable[[str], str] = None,
    outline: bool = False,
    title: str | None = None,
    toc_title: str = DFLT_TOC_TITLE,
    header_height: float = DFLT_HEADER_HEIGHT,
) -> bytes:
    """Join PDFs, optionally adding a contents page, document headers and bookmarks.

    :param items: ``{key: pdf_bytes}`` or an iterable of ``(key, pdf_bytes)``, in order.
    :param toc: ``True`` for the default contents page (``render_contents_pdf``), or a
        ``TocRenderer`` callable ``(entries, title) -> bytes | (bytes, link_rects)``.
    :param doc_header: Text of the band added above each document's first page.
        ``True`` -> the key; a format string using ``{key}``, ``{start_page}``,
        ``{n_pages}``; or a callable ``key -> str``.
    :param outline: Add one bookmark per document.
    :param title: PDF title metadata; also the contents page title if ``toc_title`` is
        left at its default.
    :param toc_title: Title of the contents page.
    :param header_height: Height in points of the header band.

    >>> import io, pypdf
    >>> w = pypdf.PdfWriter(); _ = w.add_blank_page(width=200, height=300)
    >>> buf = io.BytesIO(); _ = w.write(buf); one = buf.getvalue()
    >>> out = bundle_pdf_bytes({'a.pdf': one, 'b.pdf': one}, toc=True, doc_header='{key}')
    >>> reader = pypdf.PdfReader(io.BytesIO(out))
    >>> len(reader.pages)  # 1 contents page + 2 documents
    3
    >>> float(reader.pages[1].mediabox.height)  # 300 + header band
    330.0
    """
    pairs = list(items.items() if isinstance(items, Mapping) else items)
    keys = [str(k) for k, _ in pairs]
    readers = [pypdf.PdfReader(io.BytesIO(b)) for _, b in pairs]
    header_text = _header_text_func(doc_header)
    if toc is True:
        toc = render_contents_pdf
    if toc:
        entries, toc_bytes, rects = _layout(
            toc, readers, keys, title if title and toc_title == DFLT_TOC_TITLE else toc_title
        )
        toc_pages = pypdf.PdfReader(io.BytesIO(toc_bytes)).pages
    else:
        entries, start, toc_pages, rects = [], 1, [], []
        for key, reader in zip(keys, readers):
            entries.append(Entry(key, start, len(reader.pages)))
            start += len(reader.pages)

    writer = pypdf.PdfWriter()
    for page in toc_pages:
        writer.add_page(page)
    for entry, reader in zip(entries, readers):
        for j, page in enumerate(reader.pages):
            if j == 0 and header_text is not None:
                add_header_band(page, header_text(entry), height=header_height)
            writer.add_page(page)
        if outline:
            writer.add_outline_item(entry.key, entry.start_page - 1)
    for (toc_idx, rect), entry in zip(rects, entries):
        _add_internal_link(writer, toc_idx, rect, entry.start_page - 1)
    if title:
        writer.add_metadata({"/Title": title})
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()
