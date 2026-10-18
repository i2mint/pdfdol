"""Tests for pdfdol.examples.aggregations."""

import io

import pypdf
from PIL import Image

from pdfdol.examples.aggregations import images_to_pdf


def _png_bytes(w=1620, h=900):  # drawn at 810x450pt: scaled down, never up
    buf = io.BytesIO()
    Image.new("RGB", (w, h), "teal").save(buf, "PNG")
    return buf.getvalue()


def test_caption_in_a_tight_footer_is_rendered():
    """A caption that fits only once Frame padding is ignored used to vanish silently."""
    page_w, img_h, footer = 842.0, 450.0, 46.0
    pdf = images_to_pdf(
        [_png_bytes()],
        captions=["first line of the footer\nsecond line of the footer"],
        mk_page_kwargs=dict(
            page_size=(page_w, 16 + img_h + footer),
            image_fraction=img_h / (16 + img_h + footer),
            horizontal_margin=16,
            top_margin=16,
            bottom_margin=8,
            gap=8,
            start_font=10,
        ),
    )
    text = pypdf.PdfReader(io.BytesIO(pdf)).pages[0].extract_text()
    assert "second line of the footer" in text
