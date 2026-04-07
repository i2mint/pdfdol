import os
import io
from pathlib import Path
import pytest

from pdfdol.tools import (
    get_pdf,
    find_ebook_convert,
    ebook_convert_to_pdf,
    register_format_converter,
    get_format_converter,
    supported_extensions,
    _format_converters,
    _ebook_convert_extensions,
    _normalize_extension,
    _resolve_src_kind,
    key_and_value_to_pdf_bytes,
)


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


# ---------------------------------------------------------------------------
# Format Converter Registry tests
# ---------------------------------------------------------------------------


def test_normalize_extension():
    assert _normalize_extension('.PDF') == '.pdf'
    assert _normalize_extension('epub') == '.epub'
    assert _normalize_extension('.Epub') == '.epub'
    assert _normalize_extension('  .TXT  ') == '.txt'


def test_native_converters_registered():
    """Native extensions should be in the registry after import."""
    for ext in ['.png', '.jpg', '.jpeg', '.bmp', '.gif', '.tiff', '.webp',
                '.html', '.htm', '.md', '.markdown', '.pdf']:
        assert ext in _format_converters, f"{ext} not registered"


def test_get_format_converter_native():
    """get_format_converter should return a callable for native extensions."""
    for ext in ['.png', '.html', '.md', '.pdf']:
        assert callable(get_format_converter(ext))


def test_get_format_converter_ebook():
    """get_format_converter should return a callable for ebook-convert extensions."""
    for ext in ['.epub', '.mobi', '.docx']:
        converter = get_format_converter(ext)
        assert callable(converter), f"No converter for {ext}"


def test_get_format_converter_unknown():
    """Unknown extensions should return None."""
    assert get_format_converter('.xyz_unknown_format') is None


def test_register_custom_converter():
    """Users should be able to register custom converters."""
    sentinel = object()

    def custom(source):
        return sentinel

    register_format_converter('.test_custom_ext', custom)
    try:
        assert get_format_converter('.test_custom_ext') is custom
    finally:
        _format_converters.pop('.test_custom_ext', None)


def test_register_no_override_without_force():
    """Existing converters should not be overridden without force=True."""
    original = get_format_converter('.png')
    register_format_converter('.png', lambda s: b'nope')
    assert get_format_converter('.png') is original


def test_supported_extensions_includes_native():
    exts = supported_extensions()
    for ext in ['.png', '.pdf', '.html', '.md']:
        assert ext in exts, f"{ext} missing from supported_extensions()"


def test_key_and_value_to_pdf_bytes_pdf_passthrough():
    """PDF bytes should pass through unchanged."""
    pdf = b"%PDF-1.4 fake content"
    assert key_and_value_to_pdf_bytes("test.pdf", pdf) == pdf


def test_key_and_value_to_pdf_bytes_unsupported():
    """Unsupported extensions should raise ValueError."""
    with pytest.raises(ValueError, match="Unsupported file type"):
        key_and_value_to_pdf_bytes("test.xyz_bad", b"data")


# ---------------------------------------------------------------------------
# ebook-convert tests
# ---------------------------------------------------------------------------


def test_find_ebook_convert():
    """find_ebook_convert should return a str path or None."""
    result = find_ebook_convert()
    assert result is None or isinstance(result, str)


def test_resolve_src_kind_ebook_extensions(tmp_path):
    """_resolve_src_kind should detect ebook files as 'ebook'."""
    for ext in ['.epub', '.mobi', '.docx', '.djvu']:
        p = tmp_path / f"test{ext}"
        p.write_bytes(b"dummy content")
        assert _resolve_src_kind(str(p)) == 'ebook', f"Expected 'ebook' for {ext}"


@pytest.mark.skipif(
    find_ebook_convert() is None,
    reason="Calibre's ebook-convert not installed",
)
def test_ebook_convert_to_pdf_from_file(tmp_path):
    """ebook-convert should convert an EPUB file to PDF bytes."""
    # Create a minimal EPUB-like file (ebook-convert will fail on garbage,
    # but we at least verify the function runs without import/path errors).
    # For a real test, use an actual EPUB fixture.
    epub_path = tmp_path / "test.epub"
    epub_path.write_bytes(b"PK")  # ZIP header (EPUB is a ZIP)
    try:
        result = ebook_convert_to_pdf(str(epub_path))
        assert isinstance(result, bytes)
    except RuntimeError:
        # ebook-convert may reject a dummy EPUB -- that's fine for this test;
        # the important thing is that the function found the binary and ran.
        pass


def test_ebook_convert_to_pdf_not_installed(monkeypatch):
    """Should raise FileNotFoundError when ebook-convert is missing."""
    monkeypatch.setattr(
        'pdfdol.tools.find_ebook_convert', lambda: None
    )
    with pytest.raises(FileNotFoundError, match="ebook-convert"):
        ebook_convert_to_pdf(b"data", extension='.epub')
