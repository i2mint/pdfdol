import os
import io
from pathlib import Path
import pytest

from pdfdol.tools import get_pdf


def _make_test_image(path: Path):
    try:
        from PIL import Image
    except Exception:
        pytest.skip("Pillow is not installed; skipping image tests")

    im = Image.new("RGB", (100, 100), color=(73, 109, 137))
    im.save(path, format="PNG")
    im.close()


def test_get_pdf_from_image_path(tmp_path):
    img_path = tmp_path / "img1.png"
    _make_test_image(img_path)

    out = get_pdf(str(img_path), egress=None)
    assert isinstance(out, (bytes, bytearray))
    # simple sanity: PDF header
    assert out[:4] == b"%PDF"


def test_get_pdf_from_image_bytes(tmp_path):
    img_path = tmp_path / "img2.png"
    _make_test_image(img_path)
    data = img_path.read_bytes()

    out = get_pdf(data, egress=None)
    assert isinstance(out, (bytes, bytearray))
    assert out[:4] == b"%PDF"


def test_get_pdf_save_to_file(tmp_path):
    img_path = tmp_path / "img3.png"
    _make_test_image(img_path)
    out_file = tmp_path / "out.pdf"

    res = get_pdf(str(img_path), egress=str(out_file))
    assert isinstance(res, str)
    assert Path(res).exists()
    data = Path(res).read_bytes()
    assert data[:4] == b"%PDF"
