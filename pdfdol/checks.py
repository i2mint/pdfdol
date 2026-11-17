"""Checks that verify a PDF, rather than looking at a few of its pages.

``text_overlaps`` finds text lines whose boxes overlap, the signature of a broken
pagination (a block drawn on top of another). It needs PyMuPDF, which is part of the
``chromium`` extra of pdfdol.
"""

from __future__ import annotations

from pathlib import Path

DFLT_OVERLAP_MIN_FRAC = 0.3
DFLT_SNIPPET_LEN = 40


def _open_pdf(pdf):
    try:
        import fitz  # PyMuPDF
    except ImportError as e:
        raise ImportError(
            "text_overlaps needs PyMuPDF: install pymupdf (it is in the chromium extra)"
        ) from e
    if isinstance(pdf, (bytes, bytearray)):
        return fitz.open(stream=bytes(pdf), filetype="pdf")
    if isinstance(pdf, (str, Path)):
        return fitz.open(str(pdf))
    return pdf  # an already open fitz.Document


def text_overlaps(
    pdf,
    *,
    min_frac: float = DFLT_OVERLAP_MIN_FRAC,
    snippet_len: int = DFLT_SNIPPET_LEN,
) -> dict[int, list[tuple[str, str]]]:
    """Pages (1-based) with text lines that overlap, and the pairs of overlapping lines.

    Two lines overlap when the area they share is at least ``min_frac`` of the
    smaller line's area. An empty dict means no overlapping text.

    :param pdf: path, bytes, or an open PyMuPDF document.
    :param min_frac: overlap threshold, as a fraction of the smaller line box.
    :param snippet_len: how many characters of each line to report.

    >>> import io
    >>> from reportlab.pdfgen import canvas
    >>> def make(y2):
    ...     buf = io.BytesIO(); c = canvas.Canvas(buf)
    ...     c.drawString(72, 700, "first line of text"); c.drawString(72, y2, "second line of text")
    ...     c.save(); return buf.getvalue()
    >>> text_overlaps(make(100))  # doctest: +SKIP
    {}
    >>> text_overlaps(make(699))  # doctest: +SKIP
    {1: [('first line of text', 'second line of text')]}
    """
    import fitz

    doc = _open_pdf(pdf)
    out = {}
    for i, page in enumerate(doc):
        lines = []
        for block in page.get_text("dict")["blocks"]:
            for line in block.get("lines", []):
                text = "".join(s["text"] for s in line["spans"]).strip()
                if text:
                    lines.append((fitz.Rect(line["bbox"]), text))
        hits = []
        for a, (ra, ta) in enumerate(lines):
            for rb, tb in lines[a + 1 :]:
                shared = ra & rb
                if shared.is_empty:
                    continue
                smaller = min(ra.get_area(), rb.get_area()) or 1
                if shared.get_area() / smaller >= min_frac:
                    hits.append((ta[:snippet_len], tb[:snippet_len]))
        if hits:
            out[i + 1] = hits
    return out
