"""Headless Chromium engine: print web pages designed for the screen.

wkhtmltopdf and WeasyPrint cannot print CSS grid, flex, ``env()``, sticky headers or
scripts. ``html_to_pdf_w_chromium`` renders the page in Chromium with the viewport set
to the printable width, so the screen layout is the print layout, then fixes what
paginated output gets wrong:

- sticky/fixed elements become static (or are removed);
- single-track grids become flex columns with the same gap, *before* any keep-together
  rule. Without this, ``break-inside: avoid`` on grid items makes Chromium push an item
  to the next page without growing its grid row, and the next block is drawn on top of
  it;
- keep-together (``break-inside: avoid``) is applied to a configurable list of
  selectors, and headings keep with what follows.

The PDF is then checked with ``pdfdol.checks.text_overlaps``, so a broken pagination is
never silent. Needs the ``chromium`` extra of pdfdol (playwright and PyMuPDF), then
``playwright install chromium``.

>>> top, right, bottom, left = parse_margin("12mm 10mm")
>>> round(top), round(right), round(bottom), round(left)
(45, 38, 45, 38)
>>> round(printable_width_px("A4", "12mm 10mm"))
718
"""

from __future__ import annotations

import re
import tempfile
import warnings
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

from pdfdol.bundle import resolve_page_size
from pdfdol.checks import DFLT_OVERLAP_MIN_FRAC, text_overlaps

DFLT_KEEP_TOGETHER = ".screen,.card,figure,table,tr,blockquote,li,h1,h2,h3,h4"
DFLT_KEEP_WITH_NEXT = "h1,h2,h3,h4"
DFLT_MARGIN = "12mm 10mm"
DFLT_VIEWPORT_HEIGHT = 1000
CSS_PX_PER_POINT = 96 / 72
_PX_PER_UNIT = {"px": 1.0, "mm": 96 / 25.4, "cm": 96 / 2.54, "in": 96.0, "pt": 96 / 72}

_GRID_TO_FLEX_JS = """() => {
  for (const el of document.querySelectorAll('body *')) {
    const cs = getComputedStyle(el);
    if (cs.display === 'grid' && cs.gridTemplateColumns.trim().split(/\\s+/).length === 1) {
      const gap = cs.rowGap;
      el.style.display = 'flex'; el.style.flexDirection = 'column'; el.style.gap = gap;
    }
  }
}"""
_STATICIZE_JS = """() => {
  for (const el of document.querySelectorAll('body *')) {
    const p = getComputedStyle(el).position;
    if (p === 'sticky' || p === 'fixed') el.style.position = 'static';
  }
}"""
_REMOVE_JS = "(sels) => { for (const s of sels) document.querySelectorAll(s).forEach(e => e.remove()); }"
_ADD_STYLE_JS = "(css) => { const s = document.createElement('style'); s.textContent = css; document.head.appendChild(s); }"


class PdfTextOverlapError(ValueError):
    """The PDF has overlapping text; ``.overlaps`` maps page -> overlapping line pairs."""

    def __init__(self, overlaps: dict):
        self.overlaps = overlaps
        n = sum(map(len, overlaps.values()))
        super().__init__(
            f"{n} overlapping text line pair(s) on page(s) {sorted(overlaps)}; "
            "the pagination is broken (see .overlaps). Adjust keep_together/remove, "
            "or pass on_overlap='warn' to get the PDF anyway."
        )


def _css_length_to_px(token: str) -> float:
    m = re.fullmatch(r"([\d.]+)(px|mm|cm|in|pt)?", token)
    if not m:
        raise ValueError(f"Cannot parse margin value {token!r}")
    return float(m.group(1)) * _PX_PER_UNIT[m.group(2) or "px"]


def parse_margin(margin: str) -> tuple[float, float, float, float]:
    """CSS-style margin (1 to 4 values; px, mm, cm, in, pt) -> (top, right, bottom, left) in px."""
    values = [_css_length_to_px(t) for t in str(margin).split()]
    if not 1 <= len(values) <= 4:
        raise ValueError(f"margin needs 1 to 4 values, got {margin!r}")
    top = values[0]
    right = values[1] if len(values) > 1 else top
    bottom = values[2] if len(values) > 2 else top
    left = values[3] if len(values) > 3 else right
    return top, right, bottom, left


def printable_width_px(page_format="A4", margin: str = DFLT_MARGIN) -> float:
    """Width in CSS px of the area inside the margins."""
    width_pt, _ = resolve_page_size(page_format)
    _, right, _, left = parse_margin(margin)
    return width_pt * CSS_PX_PER_POINT - left - right


def _as_selector_list(selectors: str | Iterable[str] | None) -> list[str]:
    if not selectors:
        return []
    if isinstance(selectors, str):
        return [s.strip() for s in selectors.split(",") if s.strip()]
    return list(selectors)


def _src_to_url(src: str, tmpdir: str) -> str:
    s = str(src).strip()
    if s.startswith(("http://", "https://", "file://")):
        return s
    if "<" in s:  # an HTML string
        path = Path(tmpdir) / "page.html"
        path.write_text(s, encoding="utf-8")
        return path.as_uri()
    return Path(s).expanduser().resolve().as_uri()


def html_to_pdf_w_chromium(
    src: str,
    egress: None | str | Callable = None,
    *,
    page_format: str | tuple = "A4",
    margin: str = DFLT_MARGIN,
    color_scheme: str = "light",
    media: str = "screen",
    remove: Iterable[str] = (),
    keep_together: str | Iterable[str] = DFLT_KEEP_TOGETHER,
    keep_with_next: str | Iterable[str] = DFLT_KEEP_WITH_NEXT,
    on_overlap: str = "raise",
    overlap_min_frac: float = DFLT_OVERLAP_MIN_FRAC,
    viewport_height: int = DFLT_VIEWPORT_HEIGHT,
    wait_until: str = "networkidle",
) -> Any:
    """Print a web page (URL, HTML file path or HTML string) to PDF with headless Chromium.

    :param src: URL, path to an HTML file, or an HTML string.
    :param egress: ``None`` -> bytes; a str -> save there and return the path; a callable
        -> applied to the bytes (as in ``get_pdf``).
    :param page_format: ``'A4'``, ``'letter'``, ... or ``(w, h)`` in points.
    :param margin: CSS-style margin, e.g. ``"12mm 10mm"``.
    :param color_scheme: ``'light'`` or ``'dark'`` (``prefers-color-scheme``).
    :param media: CSS media to emulate; ``'screen'`` prints the designed screen layout.
    :param remove: CSS selectors of elements to delete (navigation bars, cookie banners).
    :param keep_together: selectors that must not be split across pages.
    :param keep_with_next: selectors that must stay with the following content.
    :param on_overlap: what to do when text overlaps in the result: ``'raise'``
        (``PdfTextOverlapError``), ``'warn'``, or ``'ignore'`` (skips the check).
    :param overlap_min_frac: threshold passed to ``text_overlaps``.
    """
    if on_overlap not in ("raise", "warn", "ignore"):
        raise ValueError("on_overlap must be 'raise', 'warn' or 'ignore'")
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        raise ImportError(
            "The chromium engine needs playwright: install the chromium extra of "
            "pdfdol, then run: playwright install chromium"
        ) from e
    from pdfdol.tools import _resolve_bytes_egress

    top, right, bottom, left = parse_margin(margin)
    width = round(printable_width_px(page_format, margin))
    page_w, page_h = resolve_page_size(page_format)
    keep_css = ""
    if sel := _as_selector_list(keep_together):
        keep_css += f"{','.join(sel)}{{break-inside:avoid}}"
    if sel := _as_selector_list(keep_with_next):
        keep_css += f"{','.join(sel)}{{break-after:avoid}}"

    with tempfile.TemporaryDirectory() as tmpdir, sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            page = browser.new_page(
                color_scheme=color_scheme,
                viewport={"width": width, "height": viewport_height},
            )
            page.goto(_src_to_url(src, tmpdir), wait_until=wait_until)
            page.emulate_media(media=media, color_scheme=color_scheme)
            page.evaluate(_STATICIZE_JS)
            if remove:
                page.evaluate(_REMOVE_JS, list(remove))
            page.evaluate(_GRID_TO_FLEX_JS)  # before keep-together: see module docstring
            if keep_css:
                page.evaluate(_ADD_STYLE_JS, keep_css)
            pdf_bytes = page.pdf(
                width=f"{page_w * CSS_PX_PER_POINT}px",
                height=f"{page_h * CSS_PX_PER_POINT}px",
                print_background=True,
                margin=dict(
                    top=f"{top}px",
                    right=f"{right}px",
                    bottom=f"{bottom}px",
                    left=f"{left}px",
                ),
            )
        finally:
            browser.close()

    if on_overlap != "ignore":
        overlaps = text_overlaps(pdf_bytes, min_frac=overlap_min_frac)
        if overlaps:
            if on_overlap == "raise":
                raise PdfTextOverlapError(overlaps)
            warnings.warn(str(PdfTextOverlapError(overlaps)), stacklevel=2)
    return _resolve_bytes_egress(egress)(pdf_bytes)
