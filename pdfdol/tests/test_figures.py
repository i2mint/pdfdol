"""Tests for pdfdol.figures, on PDFs drawn here with PyMuPDF (skipped without it)."""

import pytest

fitz = pytest.importorskip("fitz")

from pdfdol.figures import (  # noqa: E402
    Passage,
    figure,
    figure_box,
    find_passage,
    is_scanned,
)

BODY = (
    "This is a long paragraph of body text that talks about the results in some "
    "detail, so that it has well over twenty five words in it and cannot be mistaken "
    "for a label or a legend of a figure on this page."
)


def _paper() -> bytes:
    """Page 0: body, a chart (graphics + axis label), its caption, body, a table caption.
    Page 1: a figure drawn as positioned text, then its caption."""
    doc = fitz.open()
    p = doc.new_page(width=600, height=800)
    p.insert_textbox(fitz.Rect(50, 40, 550, 120), BODY, fontsize=10)
    p.draw_rect(fitz.Rect(150, 200, 450, 380), color=(0, 0, 0))  # chart frame
    p.draw_line((170, 360), (430, 220), color=(1, 0, 0))  # a series
    p.insert_text((280, 395), "time (s)", fontsize=9)  # axis label below the frame
    p.insert_textbox(fitz.Rect(100, 410, 500, 440), "Figure 1: A rising line.", fontsize=10)
    p.insert_textbox(fitz.Rect(50, 470, 550, 550), BODY, fontsize=10)
    p.insert_textbox(fitz.Rect(100, 580, 500, 600), "Table 1: Some numbers.", fontsize=10)
    for k, row in enumerate(["a 1", "b 2", "c 3"]):
        p.insert_text((150, 620 + 15 * k), row, fontsize=10)
    q = doc.new_page(width=600, height=800)
    q.insert_textbox(fitz.Rect(50, 40, 550, 120), BODY, fontsize=10)
    for k, step in enumerate(["REQUIREMENTS", "  DESIGN", "    CODING", "      TESTING"]):
        q.insert_text((150, 200 + 30 * k), step, fontsize=10)
    q.insert_textbox(fitz.Rect(100, 330, 500, 350), "Figure 2: A waterfall.", fontsize=10)
    return doc.tobytes()


def _ml_paper() -> bytes:
    """A booktabs table above its caption, and a figure with a side caption."""
    doc = fitz.open()
    p = doc.new_page(width=600, height=800)
    p.insert_textbox(fitz.Rect(50, 40, 550, 120), BODY, fontsize=10)
    for y in (150, 168, 220):  # top, mid and bottom rules
        p.draw_line((120, y), (480, y), color=(0, 0, 0))
    p.insert_text((130, 162), "Level   Variants", fontsize=9)
    for k, row in enumerate(["L0   8", "L1   12", "L2   20"]):
        p.insert_text((130, 182 + 13 * k), row, fontsize=9)
    p.insert_textbox(fitz.Rect(100, 228, 500, 250), "Table 3: Levels.", fontsize=10)
    p.insert_textbox(fitz.Rect(50, 260, 550, 340), BODY, fontsize=10)
    p.draw_rect(fitz.Rect(190, 400, 550, 600), color=(0, 0, 0))  # chart right of caption
    p.insert_textbox(fitz.Rect(50, 450, 180, 520), "Figure 4. A side caption.", fontsize=10)
    return doc.tobytes()


def test_table_above_its_caption_is_found_by_its_rules():
    pno, (x0, y0, x1, y1) = figure_box(_ml_paper(), "Table 3:", kind="table", margin=0)
    assert pno == 0
    assert 145 <= y0 <= 151 and y1 >= 236  # rules through caption, not body below
    assert y1 < 262
    assert x0 <= 120 and x1 >= 480


def test_side_caption_takes_the_graphics_beside_it():
    _, (x0, y0, x1, y1) = figure_box(_ml_paper(), "Figure 4.", margin=0)
    assert x0 <= 55 and x1 >= 550
    assert y0 <= 400 and y1 >= 600


def _scan(text: str) -> bytes:
    """A page covered by an image, with ``text`` as an invisible text layer."""
    doc = fitz.open()
    p = doc.new_page(width=300, height=200)
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 300, 200), False)
    pix.clear_with(255)
    p.insert_image(p.rect, pixmap=pix)
    p.insert_text((20, 100), text, fontsize=10, render_mode=3)
    return doc.tobytes()


def test_figure_box_takes_graphics_label_and_caption_but_not_body():
    pno, (x0, y0, x1, y1) = figure_box(_paper(), "Figure 1:", margin=0)
    assert pno == 0
    assert x0 <= 150 and x1 >= 450  # the chart frame
    assert 195 <= y0 <= 200  # starts at the chart, not the body text at 40-120
    assert y1 >= 420  # includes the caption (its line ends near 424)


def test_figure_box_without_caption_stops_above_it():
    _, (_, _, _, y1) = figure_box(_paper(), "Figure 1:", margin=0, with_caption=False)
    assert y1 < 412


def test_figure_drawn_as_text_is_cropped_from_its_text():
    pno, (_, y0, _, y1) = figure_box(_paper(), "Figure 2:", margin=0)
    assert pno == 1
    assert 180 <= y0 <= 195  # the REQUIREMENTS line, not the body paragraph
    assert y1 >= 340  # includes the caption line


def test_table_box_goes_below_caption():
    pno, (_, y0, _, y1) = figure_box(_paper(), "Table 1", kind="table", margin=0)
    assert pno == 0
    assert y0 <= 585 and y1 >= 650


def test_figure_returns_png():
    png = figure(_paper(), "figure 1:", zoom=2)
    assert png[:8] == b"\x89PNG\r\n\x1a\n"


def test_missing_caption_raises():
    with pytest.raises(LookupError):
        figure_box(_paper(), "Figure 9:")


def test_bad_kind_raises():
    with pytest.raises(ValueError):
        figure_box(_paper(), "Figure 1:", kind="chart")


def test_find_passage_in_text_layer():
    p = find_passage(_paper(), "Figure 2: A waterfall.")
    assert isinstance(p, Passage)
    assert p.page == 1 and p.source == "text" and p.boxes
    assert find_passage(_paper(), "not in this paper at all") is None


def test_find_passage_on_a_scan_needs_ocr():
    pdf = _scan("the quoted words are here")
    with fitz.open(stream=pdf, filetype="pdf") as doc:
        assert is_scanned(doc[0])
    assert find_passage(pdf, "quoted words") == Passage(0, (), "none")

    def fake_ocr(png):  # words and pixel boxes, as an OCR engine would give them
        return [("the", (60, 280, 90, 300)), ("quoted", (100, 280, 160, 300)),
                ("words", (170, 280, 220, 300))]

    p = find_passage(pdf, "quoted words", ocr_words=fake_ocr, ocr_zoom=2)
    assert p.source == "ocr"
    assert p.boxes == ((50.0, 140.0, 110.0, 150.0),)

    def wrong_ocr(png):
        return [("other", (0, 0, 10, 10))]

    assert find_passage(pdf, "quoted words", ocr_words=wrong_ocr).source == "none"
