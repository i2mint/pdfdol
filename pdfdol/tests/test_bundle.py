"""Tests for bundling: contents page, document headers, bookmarks, image fitting (synthetic data only)."""

import io

import pypdf
import pytest

from pdfdol import concat_pdfs
from pdfdol.bundle import bundle_pdf_bytes, fit_pdf_to_page

pytest.importorskip("reportlab")


def _pdf(n_pages, w=200, h=300):
    writer = pypdf.PdfWriter()
    for _ in range(n_pages):
        writer.add_blank_page(width=w, height=h)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def _png(w, h):
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (w, h), (10, 120, 200)).save(buf, format="PNG")
    return buf.getvalue()


def _reader(b):
    return pypdf.PdfReader(io.BytesIO(b))


def _link_targets(reader):
    targets = []
    for page in reader.pages:
        for annot in page.get("/Annots", []):
            a = annot.get_object()
            if a.get("/Subtype") == "/Link":
                targets.append(reader.get_page_number(a["/Dest"][0].get_object()))
    return targets


def test_toc_links_and_outline():
    docs = {"a.pdf": _pdf(2), "b.pdf": _pdf(1), "c.pdf": _pdf(3)}
    out = _reader(bundle_pdf_bytes(docs, toc=True, outline=True, title="T"))
    assert len(out.pages) == 1 + 6
    assert [o.title for o in out.outline] == list(docs)
    assert [out.get_destination_page_number(o) for o in out.outline] == [1, 3, 4]
    assert _link_targets(out) == [1, 3, 4]
    assert out.metadata.title == "T"
    assert "a.pdf" in out.pages[0].extract_text()


def test_toc_spills_over_several_pages():
    docs = {f"doc{i:03d}.pdf": _pdf(1) for i in range(120)}
    out = _reader(bundle_pdf_bytes(docs, toc=True, outline=True))
    n_toc = len(out.pages) - 120
    assert n_toc > 1
    assert out.get_destination_page_number(out.outline[0]) == n_toc
    assert len(_link_targets(out)) == 120


def test_doc_header_adds_band_without_covering_content():
    docs = {"a.pdf": _pdf(2), "b.pdf": _pdf(1)}
    out = _reader(bundle_pdf_bytes(docs, doc_header="File: {key}", header_height=30))
    heights = [float(p.mediabox.height) for p in out.pages]
    assert heights == [330, 300, 330]
    assert "File: a.pdf" in out.pages[0].extract_text()
    assert float(out.pages[0].mediabox.bottom) == 0  # content area untouched


def test_doc_header_callable_and_rotated_page():
    page = _reader(_pdf(1)).pages[0]
    w = pypdf.PdfWriter()
    p = w.add_page(page)
    p.rotate(90)
    buf = io.BytesIO()
    w.write(buf)
    out = _reader(bundle_pdf_bytes({"r.pdf": buf.getvalue()}, doc_header=str.upper))
    assert "R.PDF" in out.pages[0].extract_text()


def test_custom_toc_renderer_without_links():
    out = _reader(
        bundle_pdf_bytes({"a.pdf": _pdf(1)}, toc=lambda entries, title: _pdf(2))
    )
    assert len(out.pages) == 3 and _link_targets(out) == []


def test_fit_pdf_to_page():
    wide = _reader(fit_pdf_to_page(_pdf(1, 1000, 500), "A4")).pages[0]
    tall = _reader(fit_pdf_to_page(_pdf(1, 500, 1000), (400, 600))).pages[0]
    assert (round(float(wide.mediabox.width)), round(float(wide.mediabox.height))) == (842, 595)
    assert (float(tall.mediabox.width), float(tall.mediabox.height)) == (400, 600)
    with pytest.raises(ValueError):
        fit_pdf_to_page(_pdf(1), "nope")


def test_concat_pdfs_with_images_and_options(tmp_path):
    pytest.importorskip("PIL")
    src = {"1.pdf": _pdf(1), "2.png": _png(300, 100), "3.png": _png(80, 160)}
    plain = _reader(concat_pdfs(src, key_order=sorted))
    assert len(plain.pages) == 3
    out = _reader(
        concat_pdfs(
            src, key_order=sorted, toc=True, doc_header=True, outline=True,
            image_page_size="A4",
        )
    )
    sizes = [(round(float(p.mediabox.width)), round(float(p.mediabox.height))) for p in out.pages]
    assert sizes[1] == (200, 330)
    assert sizes[2] == (842, 595 + 30)
    assert sizes[3] == (595, 842 + 30)
    assert _link_targets(out) == [1, 2, 3]


def test_concat_pdfs_dir_and_iterable(tmp_path):
    (tmp_path / "x.pdf").write_bytes(_pdf(1))
    (tmp_path / "y.pdf").write_bytes(_pdf(2))
    out = _reader(concat_pdfs(str(tmp_path), key_order=sorted, outline=True))
    assert [o.title for o in out.outline] == ["x.pdf", "y.pdf"]
    out = _reader(concat_pdfs([_pdf(1), _pdf(1)], outline=True))
    assert len(out.outline) == 2
