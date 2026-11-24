"""Tests for pdfdol.figures, on PDFs drawn here with PyMuPDF (skipped without it)."""

import io

import pytest

fitz = pytest.importorskip("fitz")

from pdfdol.figures import (  # noqa: E402
    FigureBox,
    Passage,
    _match_tokens,
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


def _pdf(*pages) -> bytes:
    """A PDF with one page per callable, each drawing on a 600 x 800 page."""
    doc = fitz.open()
    for draw in pages:
        draw(doc.new_page(width=600, height=800))
    return doc.tobytes()


def _paper_p0(p):
    """Body, a chart (graphics + axis label), its caption, body, a table caption and rows."""
    p.insert_textbox(fitz.Rect(50, 40, 550, 120), BODY, fontsize=10)
    p.draw_rect(fitz.Rect(150, 200, 450, 380), color=(0, 0, 0))  # chart frame
    p.draw_line((170, 360), (430, 220), color=(1, 0, 0))  # a series
    p.insert_text((280, 395), "time (s)", fontsize=9)  # axis label below the frame
    p.insert_textbox(
        fitz.Rect(100, 410, 500, 440), "Figure 1: A rising line.", fontsize=10
    )
    p.insert_textbox(fitz.Rect(50, 470, 550, 550), BODY, fontsize=10)
    p.insert_textbox(
        fitz.Rect(100, 580, 500, 600), "Table 1: Some numbers.", fontsize=10
    )
    for k, row in enumerate(["a 1", "b 2", "c 3"]):
        p.insert_text((150, 620 + 15 * k), row, fontsize=10)


def _paper_p1(q):
    """A figure drawn as positioned text, then its caption."""
    q.insert_textbox(fitz.Rect(50, 40, 550, 120), BODY, fontsize=10)
    for k, step in enumerate(
        ["REQUIREMENTS", "  DESIGN", "    CODING", "      TESTING"]
    ):
        q.insert_text((150, 200 + 30 * k), step, fontsize=10)
    q.insert_textbox(
        fitz.Rect(100, 330, 500, 350), "Figure 2: A waterfall.", fontsize=10
    )


def _paper() -> bytes:
    return _pdf(_paper_p0, _paper_p1)


def _ml_paper() -> bytes:
    """A booktabs table above its caption (under a running header rule), and a side caption."""

    def draw(p):
        p.insert_text((50, 30), "Published as a conference paper", fontsize=8)
        p.draw_line((50, 36), (550, 36), color=(0, 0, 0))  # header rule
        p.insert_textbox(fitz.Rect(50, 45, 550, 125), BODY, fontsize=10)
        for y in (150, 168, 220):  # top, mid and bottom rules
            p.draw_line((120, y), (480, y), color=(0, 0, 0))
        p.insert_text((130, 162), "Level   Variants", fontsize=9)
        for k, row in enumerate(["L0   8", "L1   12", "L2   20"]):
            p.insert_text((130, 182 + 13 * k), row, fontsize=9)
        p.insert_textbox(fitz.Rect(100, 228, 500, 250), "Table 3: Levels.", fontsize=10)
        p.insert_textbox(fitz.Rect(50, 260, 550, 340), BODY, fontsize=10)
        p.draw_rect(
            fitz.Rect(190, 400, 550, 600), color=(0, 0, 0)
        )  # chart right of caption
        p.insert_textbox(
            fitz.Rect(50, 450, 180, 520), "Figure 4. A side caption.", fontsize=10
        )

    return _pdf(draw)


def _scan(text=None) -> bytes:
    """A page covered by an image, with ``text`` as an invisible text layer if given."""
    doc = fitz.open()
    p = doc.new_page(width=300, height=200)
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 300, 200), False)
    pix.clear_with(255)
    p.insert_image(p.rect, pixmap=pix)
    if text:
        p.insert_text((20, 100), text, fontsize=10, render_mode=3)
    return doc.tobytes()


# --------------------------------------------------------------------------- figures


def test_figure_box_takes_graphics_label_and_caption_but_not_body():
    got = figure_box(_paper(), "Figure 1:", margin=0)
    assert isinstance(got, FigureBox) and got.page == 0 and got.source == "graphics"
    x0, y0, x1, y1 = got.box
    assert x0 <= 150 and x1 >= 450  # the chart frame
    assert 195 <= y0 <= 200  # starts at the chart, not the body text at 40-120
    assert y1 >= 420  # includes the caption (its line ends near 424)


def test_figure_box_without_caption_stops_above_it():
    _, (_, _, _, y1), _ = figure_box(
        _paper(), "Figure 1:", margin=0, with_caption=False
    )
    assert y1 < 412


def test_figure_drawn_as_text_is_cropped_from_its_text():
    pno, (_, y0, _, y1), source = figure_box(_paper(), "Figure 2:", margin=0)
    assert (pno, source) == (1, "text")
    assert 180 <= y0 <= 195  # the REQUIREMENTS line, not the body paragraph
    assert y1 >= 340


def test_table_box_goes_below_caption_and_kind_is_inferred():
    pno, (_, y0, _, y1), _ = figure_box(_paper(), "Table 1", margin=0)
    assert pno == 0
    assert y0 <= 585 and y1 >= 650


def test_table_above_its_caption_is_found_by_its_rules_and_not_the_header():
    _, (x0, y0, x1, y1), source = figure_box(_ml_paper(), "Table 3:", margin=0)
    assert source == "rules"
    assert 145 <= y0 <= 151 and 236 <= y1 < 262  # rules through caption, not body below
    assert x0 <= 120 and x1 >= 480


def test_side_caption_takes_the_graphics_beside_it():
    _, (x0, y0, x1, y1), source = figure_box(_ml_paper(), "Figure 4.", margin=0)
    assert source == "beside"
    assert x0 <= 55 and x1 >= 550 and y0 <= 400 and y1 >= 600


def test_a_figure_does_not_grow_across_the_caption_of_the_figure_above():
    def draw(p):
        p.draw_rect(fitz.Rect(150, 100, 450, 250), color=(0, 0, 0))  # figure 5
        p.insert_textbox(fitz.Rect(150, 255, 450, 275), "Figure 5: Above.", fontsize=10)
        p.draw_rect(
            fitz.Rect(150, 285, 450, 400), color=(0, 0, 0)
        )  # figure 6, 35 pt below 5
        p.insert_textbox(fitz.Rect(150, 405, 450, 425), "Figure 6: Below.", fontsize=10)

    _, (_, y0, _, _), _ = figure_box(_pdf(draw), "Figure 6:", margin=0)
    assert y0 >= 280


def test_a_full_width_figure_with_a_short_caption_is_kept_whole():
    def draw(p):
        p.draw_rect(
            fitz.Rect(40, 100, 280, 250), color=(0, 0, 0)
        )  # left half of a diagram
        p.draw_rect(fitz.Rect(300, 100, 560, 250), color=(0, 0, 0))  # right half
        p.insert_textbox(fitz.Rect(40, 260, 120, 280), "Fig. 2.", fontsize=10)

    _, (x0, _, x1, _), _ = figure_box(_pdf(draw), "Fig. 2.", margin=0)
    assert x0 <= 40 and x1 >= 560


def test_side_by_side_figures_each_keep_their_own_half():
    def draw(p):
        p.draw_rect(fitz.Rect(40, 100, 280, 250), color=(0, 0, 0))
        p.draw_rect(fitz.Rect(300, 100, 560, 250), color=(0, 0, 0))
        p.insert_textbox(fitz.Rect(40, 260, 280, 280), "Figure 1: Left.", fontsize=10)
        p.insert_textbox(fitz.Rect(300, 260, 560, 280), "Figure 2: Right.", fontsize=10)

    _, (x0, _, x1, _), _ = figure_box(_pdf(draw), "Figure 2:", margin=0)
    assert x0 >= 285 and x1 >= 560


def test_a_text_figure_wins_over_a_chart_in_the_other_column():
    def draw(p):
        for k, step in enumerate(["INPUT", "  PARSE", "    OUTPUT"]):
            p.insert_text((60, 270 + 25 * k), step, fontsize=10)
        p.insert_textbox(fitz.Rect(50, 340, 280, 360), "Figure 3: Steps.", fontsize=10)
        p.draw_rect(
            fitz.Rect(320, 250, 550, 420), color=(0, 0, 0)
        )  # unrelated, right column

    _, (_, _, x1, _), source = figure_box(_pdf(draw), "Figure 3:", margin=0)
    assert source == "text" and x1 < 300


def test_a_caption_merged_into_a_block_is_found_by_its_line_and_a_mention_is_never_taken():
    def mention(p):
        p.insert_textbox(
            fitz.Rect(50, 50, 550, 100), "As Figure 10 shows, things grow.", fontsize=10
        )

    def merged(p):
        p.draw_rect(fitz.Rect(150, 100, 450, 300), color=(0, 0, 0))
        p.insert_textbox(
            fitz.Rect(150, 305, 450, 340),
            "x axis label\nFigure 1: Growth.",
            fontsize=10,
        )

    assert figure_box(_pdf(mention, merged), "Figure 1").page == 1
    with pytest.raises(LookupError, match="only mentioned"):
        figure_box(_pdf(mention), "Figure 10")


def test_nothing_next_to_the_caption_says_so():
    def draw(p):
        p.insert_textbox(fitz.Rect(50, 50, 550, 130), BODY, fontsize=10)
        p.insert_textbox(fitz.Rect(100, 140, 500, 160), "Figure 7: Lost.", fontsize=10)

    assert figure_box(_pdf(draw), "Figure 7:").source == "caption-only"


def test_a_rotated_page_is_cropped_where_the_figure_is():
    def draw(p):
        p.draw_rect(fitz.Rect(100, 100, 300, 250), color=(0, 0, 0), fill=(0, 0, 0))
        p.insert_textbox(fitz.Rect(100, 255, 300, 275), "Figure 1: Dark.", fontsize=10)
        p.set_rotation(90)

    png = figure(_pdf(draw), "Figure 1:", zoom=1, margin=0, with_caption=False)
    pix = fitz.Pixmap(png)
    dark = sum(1 for i in range(0, len(pix.samples), pix.n) if pix.samples[i] < 50)
    assert dark / (pix.width * pix.height) > 0.8


def test_figure_returns_png_and_takes_a_file_object():
    png = figure(io.BytesIO(_paper()), "figure 1:", zoom=2)
    assert png[:8] == b"\x89PNG\r\n\x1a\n"


def test_bad_arguments_are_refused():
    with pytest.raises(LookupError):
        figure_box(_paper(), "Figure 9:")
    with pytest.raises(ValueError):
        figure_box(_paper(), "Figure 1:", kind="chart")
    for page in (-1, 2):
        with pytest.raises(IndexError, match="out of range"):
            figure_box(_paper(), "Figure 1:", page=page)


# --------------------------------------------------------------------------- passages


def test_find_passage_in_text_layer():
    p = find_passage(_paper(), "Figure 2: A waterfall.")
    assert isinstance(p, Passage)
    assert p.page == 1 and p.source == "text" and p.boxes
    assert find_passage(_paper(), "not in this paper at all") is None


def test_quotes_match_across_curly_quotes_case_and_hyphenated_line_ends():
    def draw(p):
        p.insert_text((50, 100), "The AI's impact on agents and repos-", fontsize=10)
        p.insert_text((50, 114), "itories using context.", fontsize=10)

    pdf = _pdf(draw)
    assert (
        find_passage(pdf, "the AI’s Impact").source == "text"
    )  # curly quote in the quote
    p = find_passage(pdf, "agents and repositories using context")
    assert p.source == "text" and len(p.boxes) == 2  # one box per line


def test_the_whole_quote_on_a_later_page_beats_its_head_on_an_earlier_one():
    quote = "we found that the results hold in general across all of the models"

    def head_only(p):
        p.insert_text(
            (50, 100), "we found that the results hold in general, mostly.", fontsize=10
        )

    def whole(p):
        p.insert_text((50, 100), quote, fontsize=10)

    got = find_passage(_pdf(head_only, whole), quote)
    assert (got.page, got.source) == (1, "text")
    assert find_passage(_pdf(head_only), quote).source == "text-head"


def test_find_passage_on_a_scan_needs_ocr():
    pdf = _scan("the quoted words are here")
    with fitz.open(stream=pdf, filetype="pdf") as doc:
        assert is_scanned(doc[0])
    assert find_passage(pdf, "quoted words") == Passage(0, (), "none")

    def fake_ocr(png):  # words and pixel boxes, with the punctuation OCR attaches
        return [
            ("the", (60, 280, 90, 300)),
            ("“quoted", (100, 280, 160, 300)),
            ("words,", (170, 280, 220, 300)),
        ]

    p = find_passage(pdf, "quoted words", ocr_words=fake_ocr, ocr_zoom=2)
    assert p.source == "ocr"
    assert p.boxes == ((50.0, 140.0, 110.0, 150.0),)

    def wrong_ocr(png):
        return [("other", (0, 0, 10, 10))]

    assert find_passage(pdf, "quoted words", ocr_words=wrong_ocr).source == "none"


def test_a_scan_with_no_text_layer_is_ocrd_when_ocr_is_given():
    calls = []

    def fake_ocr(png):
        calls.append(png)
        return [("quoted", (100, 280, 160, 300)), ("words", (170, 280, 220, 300))]

    pdf = _scan()
    assert find_passage(pdf, "quoted words") is None
    assert (
        find_passage(pdf, "quoted words", ocr_words=fake_ocr, ocr_zoom=2).source
        == "ocr"
    )
    assert len(calls) == 1


# --------------------------------------------------------------------------- second review


def test_a_bare_caption_skips_prose_that_starts_with_its_label():
    def prose(p):
        p.insert_textbox(
            fitz.Rect(50, 50, 550, 120),
            BODY + "\nTable 2 shows the totals, and\n" "Table 2) is long.",
            fontsize=10,
        )

    def real(p):
        for y in (100, 118, 170):
            p.draw_line((120, y), (480, y), color=(0, 0, 0))
        p.insert_text((130, 112), "Level   Count", fontsize=9)
        p.insert_textbox(fitz.Rect(100, 178, 500, 200), "Table 2: Totals.", fontsize=10)

    got = figure_box(_pdf(prose, real), "Table 2")
    assert (got.page, got.source) == (1, "rules")


def test_a_heading_above_a_side_caption_does_not_hide_the_chart_beside_it():
    def draw(p):
        p.insert_textbox(fitz.Rect(50, 425, 180, 445), "3.2 Results", fontsize=12)
        p.insert_textbox(
            fitz.Rect(50, 450, 180, 520), "Figure 4. A side caption.", fontsize=10
        )
        p.draw_rect(fitz.Rect(190, 400, 550, 600), color=(0, 0, 0))

    _, (x0, _, x1, _), source = figure_box(_pdf(draw), "Figure 4.", margin=0)
    assert source == "beside" and x1 >= 550


def test_a_long_legend_in_a_small_font_stays_part_of_its_figure():
    legend = " ".join(f"K{i}: key entry number {i}," for i in range(12))  # 40+ words

    def draw(p):
        p.insert_textbox(fitz.Rect(50, 40, 550, 120), BODY, fontsize=10)
        p.insert_textbox(fitz.Rect(50, 130, 550, 200), BODY, fontsize=10)
        p.draw_rect(fitz.Rect(150, 250, 450, 400), color=(0, 0, 0))
        p.insert_textbox(fitz.Rect(150, 410, 450, 470), legend, fontsize=6)
        p.insert_textbox(fitz.Rect(150, 445, 450, 465), "Figure 3: Bars.", fontsize=10)

    _, (_, y0, _, _), source = figure_box(_pdf(draw), "Figure 3:", margin=0)
    assert source == "graphics" and y0 <= 250


def test_a_running_header_rule_is_left_out_but_a_table_near_the_page_bottom_is_whole():
    def page(p, table=False):
        p.insert_text((50, 30), "Running header", fontsize=8)
        p.draw_line(
            (120, 36), (480, 36), color=(0, 0, 0)
        )  # same width as the table's rules
        p.insert_textbox(fitz.Rect(50, 45, 550, 125), BODY, fontsize=10)
        if table:
            p.insert_textbox(fitz.Rect(100, 60, 500, 80), "", fontsize=10)
            for y in (
                700,
                718,
                770,
            ):  # the bottom rule sits in the bottom 6 % of the page
                p.draw_line((120, y), (480, y), color=(0, 0, 0))
            p.insert_text((130, 712), "Level   Count", fontsize=9)
            p.insert_textbox(
                fitz.Rect(100, 676, 500, 696), "Table 9: Bottom.", fontsize=10
            )

    pdf = _pdf(page, page, lambda p: page(p, table=True), page)
    got = figure_box(pdf, "Table 9:", margin=0)
    assert got.source == "rules" and got.box[3] >= 769 and got.box[1] >= 670


def test_without_caption_nothing_found_raises():
    def draw(p):
        p.insert_textbox(fitz.Rect(50, 50, 550, 130), BODY, fontsize=10)
        p.insert_textbox(fitz.Rect(100, 140, 500, 160), "Figure 7: Lost.", fontsize=10)

    with pytest.raises(LookupError, match="nothing found"):
        figure_box(_pdf(draw), "Figure 7:", with_caption=False)


def test_compound_and_suspended_hyphens_and_dashes_match():
    def draw(p):
        p.insert_text((50, 100), "LLM-generated and developer-", fontsize=10)
        p.insert_text(
            (50, 114),
            "committed files, pre- and post-training results-which hold.",
            fontsize=10,
        )

    pdf = _pdf(draw)
    for quote in (
        "LLM-generated and developer-committed files.",
        "pre- and post-training",
        "results \u2014 which hold",
    ):
        assert find_passage(pdf, quote).source == "text", quote


def test_a_head_only_ocr_match_says_so():
    quote = "the quoted words are here and then some more words"

    def fake_ocr(png):
        return [
            (w, (10 * i, 0, 10 * i + 8, 10))
            for i, w in enumerate("the quoted words are here and".split())
        ]

    p = find_passage(_scan("the quoted words are here and"), quote, ocr_words=fake_ocr)
    assert p.source == "ocr-head"


# --------------------------------------------------------------------------- scanned figures

PROSE = [
    "The design of the system was reviewed in detail by the whole team before",
    "any of the coding started, and every one of the steps below was agreed on",
    "in writing so that nobody could later claim that the plan had been unclear.",
]


def _rasterize(pdf: bytes, *, text_layer=lambda text: True, zoom=2) -> bytes:
    """``pdf`` as a scan: each page an image of itself, with an invisible text layer of
    the lines ``text_layer`` keeps, one block per line (as OCR gives)."""
    src = fitz.open(stream=pdf, filetype="pdf")
    out = fitz.open()
    for page in src:
        new = out.new_page(width=page.rect.width, height=page.rect.height)
        new.insert_image(
            new.rect, pixmap=page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
        )
        for block in page.get_text("dict")["blocks"]:
            for line in block.get("lines", []):
                text = "".join(s["text"] for s in line["spans"])
                if text.strip() and text_layer(text):
                    span = line["spans"][0]
                    new.insert_text(
                        span["origin"], text, fontsize=span["size"], render_mode=3
                    )
    return out.tobytes()


def _boxes_paper(p):
    """Prose, then a figure of three boxes that do not touch, its caption, then prose."""
    for k, line in enumerate(PROSE):
        p.insert_text((50, 70 + 14 * k), line, fontsize=10)
    for k, (x, y) in enumerate([(80, 150), (250, 215), (420, 280)]):
        p.draw_rect(fitz.Rect(x, y, x + 120, y + 45), color=(0, 0, 0), width=1.5)
        p.insert_text((x + 20, y + 27), f"STEP {k + 1}", fontsize=10)
    p.insert_text((80, 355), "Figure 1. Three steps that never touch.", fontsize=10)
    for k, line in enumerate(PROSE):
        p.insert_text((50, 400 + 14 * k), line, fontsize=10)


def _two_figures(p):
    """A figure and its caption, then another figure (two boxes) and its caption."""
    p.draw_rect(fitz.Rect(100, 60, 300, 160), color=(0, 0, 0), width=1.5)
    p.insert_text((100, 180), "Figure 3. The first one.", fontsize=10)
    p.draw_rect(fitz.Rect(100, 205, 250, 260), color=(0, 0, 0), width=1.5)
    p.draw_rect(fitz.Rect(300, 280, 450, 335), color=(0, 0, 0), width=1.5)
    p.insert_text((100, 360), "Figure 4. The second one.", fontsize=10)


def _contains(outer, inner, slack=1.0):
    return (
        outer[0] <= inner[0] + slack
        and outer[1] <= inner[1] + slack
        and outer[2] >= inner[2] - slack
        and outer[3] >= inner[3] - slack
    )


@pytest.mark.parametrize(
    "text_layer",
    [lambda t: True, lambda t: t.startswith("Figure")],
    ids=["prose-in-text-layer", "caption-only-in-text-layer"],
)
def test_a_figure_on_a_scan_is_read_off_its_pixels_whole_and_without_the_prose(
    text_layer,
):
    pdf = _rasterize(_pdf(_boxes_paper), text_layer=text_layer)
    with fitz.open(stream=pdf, filetype="pdf") as doc:
        assert is_scanned(doc[0])
    got = figure_box(pdf, "Figure 1.", margin=0)
    assert got.source == "pixels"
    assert _contains(got.box, (80, 150, 540, 325))  # every box
    assert _contains(got.box, (80, 345, 270, 357))  # the caption
    assert got.box[1] > 70 + 14 * 2 + 2  # nothing of the prose above
    assert got.box[3] < 390  # nor below
    body = figure_box(pdf, "Figure 1.", margin=0, with_caption=False)
    assert body.box[3] < 345


def test_a_figure_on_a_scan_stops_at_the_caption_of_the_figure_above():
    pdf = _rasterize(_pdf(_two_figures))
    got = figure_box(pdf, "Figure 4.", margin=0)
    assert got.source == "pixels"
    assert _contains(got.box, (100, 205, 450, 335))
    assert got.box[1] > 180  # not the first figure's caption, nor the figure
    first = figure_box(pdf, "Figure 3.", margin=0)
    assert _contains(first.box, (100, 60, 300, 160)) and first.box[3] < 200


def test_scan_strategy_is_a_seam():
    pdf = _rasterize(_pdf(_boxes_paper))
    assert figure_box(pdf, "Figure 1.", scan_strategy="layout").source != "pixels"
    seen = []

    def mine(page, caption_box, *, max_up, max_gap):
        seen.append(caption_box)
        return (100.0, 100.0, 200.0, 200.0)

    got = figure_box(pdf, "Figure 1.", scan_strategy=mine, margin=0)
    assert got.source == "pixels" and len(seen) == 1
    assert _contains(got.box, (100, 100, 200, 200))

    def nothing(page, caption_box, *, max_up, max_gap):
        return None

    assert figure_box(pdf, "Figure 1.", scan_strategy=nothing).source != "pixels"
    # a page that is not a scan never asks the strategy
    figure_box(_pdf(_boxes_paper), "Figure 1.", scan_strategy=mine)
    assert len(seen) == 1
    with pytest.raises(ValueError):
        figure_box(pdf, "Figure 1.", scan_strategy="magic")


def test_pixel_figure_box_takes_a_page_and_a_caption_box():
    from pdfdol.figures import pixel_figure_box

    pdf = _rasterize(_pdf(_boxes_paper))
    with fitz.open(stream=pdf, filetype="pdf") as doc:
        box = pixel_figure_box(doc[0], (80, 345, 270, 357))
        assert _contains(box, (80, 150, 540, 325))
        assert pixel_figure_box(doc[0], (80, 40, 270, 50)) is None  # nothing above


def test_a_sentence_like_label_inside_a_figure_on_a_scan_does_not_stop_it():
    def draw(p):
        _boxes_paper(p)
        p.draw_rect(fitz.Rect(80, 100, 540, 140), color=(0, 0, 0), width=1.5)
        p.insert_text(
            (90, 125), "Collect the readings from all of the sensors", fontsize=10
        )

    got = figure_box(_rasterize(_pdf(draw)), "Figure 1.", margin=0)
    assert got.source == "pixels" and _contains(got.box, (80, 100, 540, 325))


def test_a_vector_figure_over_a_page_sized_image_keeps_its_graphics_box():
    def draw(p):
        pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 60, 80), False)
        pix.clear_with(255)
        p.insert_image(p.rect, pixmap=pix)  # a white background image
        _paper_p0(p)

    got = figure_box(_pdf(draw), "Figure 1:")
    assert got.source == "graphics"


def test_a_column_caption_on_a_two_column_scan_keeps_its_figure_in_its_column():
    def draw(p):
        p.draw_rect(fitz.Rect(60, 150, 250, 300), color=(0, 0, 0), width=1.5)
        p.insert_text((60, 320), "Figure 2. Left column.", fontsize=10)
        for k in range(20):  # the right column's prose, beside the figure
            p.insert_text(
                (320, 100 + 14 * k), "words in the other column here", fontsize=10
            )

    pdf = _rasterize(_pdf(draw), text_layer=lambda t: t.startswith("Figure"))
    got = figure_box(pdf, "Figure 2.", margin=0)
    assert got.source == "pixels" and _contains(got.box, (60, 150, 250, 300))
    assert got.box[2] < 320


def test_a_figure_touching_its_caption_on_a_scan_is_still_found():
    def draw(p):
        p.draw_rect(fitz.Rect(80, 150, 300, 318), color=(0, 0, 0), width=1.5)
        p.draw_line(
            (150, 318), (150, 326), color=(0, 0, 0), width=1.5
        )  # into the caption
        p.insert_text((80, 330), "Figure 5. Touching.", fontsize=10)

    got = figure_box(_rasterize(_pdf(draw)), "Figure 5.", margin=0)
    assert got.source == "pixels" and _contains(got.box, (80, 150, 300, 318))


def test_an_empty_box_from_a_strategy_counts_as_nothing():
    pdf = _rasterize(_pdf(_boxes_paper))

    def empty(page, caption_box, *, max_up, max_gap):
        return (0.0, 0.0, 0.0, 0.0)

    assert figure_box(pdf, "Figure 1.", scan_strategy=empty).source != "pixels"


# --------------------------------------------------------------------------- word boundaries


def test_a_quote_does_not_match_inside_a_longer_word():
    """A hit starts and ends at a word (or word-part) boundary (pdfdol#22)."""

    def page(text):
        return lambda p: p.insert_text((72, 72), text, fontsize=11)

    pdf = _pdf(
        page("We restart the engine today."),
        page("Modern art is great."),
        page("Nothing here."),
    )
    assert find_passage(pdf, "art").page == 1
    assert find_passage(pdf, "art is").page == 1
    assert find_passage(pdf, "start the") is None
    assert find_passage(pdf, "restart the engine").page == 0
    assert find_passage(pdf, "here", page=0) is None


def test_match_tokens_searches_past_a_hit_inside_a_word():
    words = [("restart", 0), ("the", 1), ("art", 2), ("state-of-the-art", 3)]
    assert _match_tokens(words, "art") == [2]
    assert _match_tokens(words, "the art") == [1, 2]
    assert _match_tokens(words, "of the art") == [3]  # parts of a compound count
    assert _match_tokens(words, "tart") is None
    assert _match_tokens([("The", 0), ("AI’s", 1), ("impact", 2)], "the AI") == [0, 1]
