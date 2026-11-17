"""Tests for the Chromium engine and the text_overlaps check (synthetic pages only)."""

import io
import sys

import pytest

from pdfdol import get_pdf
from pdfdol import chromium as chromium_mod
from pdfdol.chromium import (
    PdfTextOverlapError,
    html_to_pdf_w_chromium,
    parse_margin,
    printable_width_px,
)

GRID_PAGE = (
    "<html><head><style>body{font:14px sans-serif;margin:0}"
    ".grid{display:grid;gap:12px}.card{border:1px solid #888;padding:10px;height:230px}"
    "</style></head><body><h1>Title</h1><div class='grid'>"
    + "".join(
        f"<div class='card'><h2>Card {i}</h2><p>Line of card {i}</p></div>"
        for i in range(14)
    )
    + "</div><p>After the grid</p></body></html>"
)


def _chromium_available():
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as pw:
            pw.chromium.launch().close()
        import fitz  # noqa: F401
    except Exception:
        return False
    return True


needs_chromium = pytest.mark.skipif(
    not _chromium_available(), reason="playwright+chromium+pymupdf not available"
)


def test_parse_margin_forms():
    assert parse_margin("10px") == (10, 10, 10, 10)
    assert parse_margin("10px 20px") == (10, 20, 10, 20)
    assert parse_margin("1px 2px 3px") == (1, 2, 3, 2)
    assert parse_margin("1px 2px 3px 4px") == (1, 2, 3, 4)
    with pytest.raises(ValueError):
        parse_margin("1px 2px 3px 4px 5px")
    with pytest.raises(ValueError):
        parse_margin("wide")
    assert round(printable_width_px("A4", "12mm 10mm")) == 718


def test_get_pdf_engine_validation():
    with pytest.raises(ValueError, match="Unknown engine"):
        get_pdf("<html></html>", engine="nope")
    with pytest.raises(ValueError, match="html, or file|url, html or file"):
        get_pdf(b"\x89PNG\r\n\x1a\n" + b"0" * 20, src_kind="image", engine="chromium")


def test_missing_playwright_gives_install_hint(monkeypatch):
    monkeypatch.setitem(sys.modules, "playwright", None)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", None)
    with pytest.raises(ImportError, match="chromium extra"):
        html_to_pdf_w_chromium("<html></html>")


def test_text_overlaps_catches_overlapping_text():
    pytest.importorskip("fitz")
    pytest.importorskip("reportlab")
    from reportlab.pdfgen import canvas
    from pdfdol import text_overlaps

    def make(y2):
        buf = io.BytesIO()
        c = canvas.Canvas(buf)
        c.drawString(72, 700, "first line of text")
        c.drawString(72, y2, "second line of text")
        c.save()
        return buf.getvalue()

    assert text_overlaps(make(100)) == {}
    assert list(text_overlaps(make(699))) == [1]


@needs_chromium
def test_chromium_engine_grid_of_tall_cards_has_no_overlaps(tmp_path):
    out = get_pdf(GRID_PAGE, engine="chromium", egress=str(tmp_path / "o.pdf"))
    from pdfdol import text_overlaps

    assert text_overlaps(out) == {}
    pdf = get_pdf(GRID_PAGE, engine="chromium")
    assert pdf[:4] == b"%PDF"


@needs_chromium
def test_chromium_engine_raises_or_warns_on_overlap(monkeypatch):
    monkeypatch.setattr(
        chromium_mod, "text_overlaps", lambda *a, **k: {1: [("a", "b")]}
    )
    with pytest.raises(PdfTextOverlapError) as err:
        html_to_pdf_w_chromium(GRID_PAGE)
    assert err.value.overlaps == {1: [("a", "b")]}
    with pytest.warns(UserWarning, match="overlapping"):
        html_to_pdf_w_chromium(GRID_PAGE, on_overlap="warn")
