"""Pdf Tools."""

from functools import partial
from typing import Literal, Callable, Union
import os
import io

import markdown
import pdfkit

from dol import Pipe

# Define the allowed source kinds (added 'image')
SrcKind = Literal["url", "html", "file", "md", "markdown", "text", "image"]


def _resolve_src_kind(src: str) -> SrcKind:
    """
    Heuristically determine the kind of source provided.

    Args:
        src (str): The source input which can be a URL, HTML string, or a file path.

    Returns:
        SrcKind: "url" if src starts with http:// or https://,
                 "html" if src appears to be HTML content,
                 "file" if src is a path to an existing file.

    Examples:

        >>> _resolve_src_kind("https://example.com")
        'url'
        >>> _resolve_src_kind("<html><body>Test</body></html>")
        'html'
        >>> import tempfile, os
        >>> with tempfile.NamedTemporaryFile(delete=False) as tmp:
        ...     _ = tmp.write(b"dummy")
        ...     tmp_name = tmp.name
        >>> _resolve_src_kind(tmp_name) == 'file'
        True
        >>> os.remove(tmp_name)
    """
    # Accept bytes input as well (image bytes)
    if isinstance(src, (bytes, bytearray)):
        # try to quickly detect image bytes
        try:
            import imghdr

            if imghdr.what(None, src) is not None:
                return "image"
        except Exception:
            pass
        # fallback to text
        return "text"

    s = src.strip()
    if s.startswith("http://") or s.startswith("https://"):
        return "url"
    elif "<html" in s.lower():
        return "html"
    elif os.path.exists(s):
        lower = s.lower()
        # Recognize image file extensions first
        image_exts = (".png", ".jpg", ".jpeg", ".tiff", ".bmp", ".gif", ".webp")
        if lower.endswith(image_exts):
            return "image"
        # Recognize markdown files explicitly
        if lower.endswith(".md") or lower.endswith(".markdown"):
            return "markdown"
        # Recognize html files explicitly
        if (
            lower.endswith(".html")
            or lower.endswith(".htm")
            or lower.endswith(".xhtml")
        ):
            return "file"
        # Default for existing files (including no-extension temp files) is 'file'
        return "file"
    else:
        # Fallback: if it doesn't look like a URL or a file exists, assume it's text.
        return "text"


def _resolve_bytes_egress(egress: Union[None, str, Callable]) -> Callable[[bytes], any]:
    """
    Return a callable that processes PDF bytes based on the given egress.

    Args:
        egress (Union[None, str, Callable]):
            - If None, the callable returns the PDF bytes as-is.
            - If a string, the callable writes the PDF bytes to that file path and returns the path.
            - If a callable, it is returned directly.

    Returns:
        Callable[[bytes], any]: A function that processes PDF bytes.

    Examples:

        >>> f = _resolve_bytes_egress(None)
        >>> f(b'pdf data') == b'pdf data'
        True
        >>> import tempfile, os
        >>> with tempfile.NamedTemporaryFile(delete=False) as tmp:
        ...     tmp_name = tmp.name
        >>> f = _resolve_bytes_egress(tmp_name)
        >>> result = f(b'pdf data')
        >>> result == tmp_name
        True
        >>> os.remove(tmp_name)
    """
    if egress is None:
        return lambda b: b
    elif isinstance(egress, str):

        def write_to_file(b: bytes) -> str:
            from pathlib import Path

            Path(egress).write_bytes(b)
            return egress

        return write_to_file
    elif callable(egress):
        return egress
    else:
        raise ValueError("egress must be None, a file path string, or a callable.")


dflt_css = """
<style>
    table {
        width: 100%;
        border-collapse: collapse;
        border: 1px solid black;
    }
    th, td {
        border: 1px solid black;
        padding: 8px;
        text-align: left;
    }
    th {
        background-color: #f2f2f2;
    }
</style>
"""


def add_css(html_text: str, css=dflt_css) -> str:
    return f"<html><head>{custom_css}</head><body>{html_text}</body></html>"


# Save to PDF with pdfkit
dflt_pdfkit_kwargs = {
    "options": {
        "encoding": "UTF-8",
        "page-size": "A4",
        "margin-top": "10mm",
        "margin-right": "10mm",
        "margin-bottom": "10mm",
        "margin-left": "10mm",
    }
}

dflt_markdown_kwargs = {
    "extensions": ("extra", "tables"),
}


def markdown_to_pdf(
    md_src: str,
    egress: Union[None, str, Callable] = None,
    *,
    markdown_extensions=dflt_markdown_kwargs,
    **pdfkit_kwargs,
):
    pdfkit_kwargs = {**dflt_pdfkit_kwargs, **pdfkit_kwargs}

    if isinstance(md_src, str) and os.path.isfile(md_src):
        md_file = md_src
        with open(md_file, "r", encoding="utf-8") as f:
            md_src = f.read()

    # Convert Markdown to HTML
    html_text = markdown.markdown(md_src, **dflt_markdown_kwargs)

    if not callable(egress):
        pdf_target = egress
        return pdfkit.from_string(html_text, pdf_target, **pdfkit_kwargs)
    else:
        # if egress is a function, we'll get the bytes for the PDF
        # and apply egress to them
        pdf_bytes = pdfkit.from_string(html_text, None)
        return egress(pdf_bytes)


def get_pdf(
    src: str,
    egress: Union[None, str, Callable] = None,
    *,
    src_kind: SrcKind = None,
    # extra options for pdfkit.from_* functions
    options=None,
    toc=None,
    cover=None,
    css=None,
    configuration=None,
    cover_first=False,
    verbose=False,
    **kwargs,
) -> Union[bytes, any]:
    """
    Convert the given source to a PDF (bytes) and process it using the specified egress.

    The source (src) can be:
      - a URL (e.g. "https://example.com")
      - an HTML string
      - a file path to an HTML file

    The egress parameter determines how the PDF bytes are returned:
      - If None, returns the PDF as bytes.
      - If a string, treats it as a file path where the PDF is saved.
      - If a callable, applies it to the PDF bytes and returns its result.
        For example, you may want to specify egress=pypdf.PdfReader to get an object
        that provides an interface of all PDF components, or you might want to
        upload the PDF to a cloud storage service.

    The src_kind parameter allows explicit specification of the source kind ("url", "html", or "file").
    If not provided, it is determined heuristically using _resolve_src_kind.

    Args:
        src (str): The source to convert.
        egress (Union[None, str, Callable], optional): How to handle the PDF bytes.
        src_kind (SrcKind, optional): Explicit source kind; if omitted, determined automatically.
        options: (optional) dict with wkhtmltopdf options, with or w/o '--'
        toc: (optional) dict with toc-specific wkhtmltopdf options, with or w/o '--'
        cover: (optional) string with url/filename with a cover html page
        css: (optional) string with path to css file which will be added to a single input file
        configuration: (optional) instance of pdfkit.configuration.Configuration()
        cover_first: (optional) if True, cover always precedes TOC
        verbose: (optional) By default '--quiet' is passed to all calls, set this to False to get wkhtmltopdf output to stdout.


    Returns:
        Union[bytes, any]: The PDF bytes, or the result of processing them via the egress callable.


    Examples:

        # Example with a URL:
        pdf_data = get_pdf("https://pypi.org", src_kind="url")
        print("Got PDF data of length:", len(pdf_data))

        # Example with HTML content:
        html_content = "<html><body><h1>Hello, PDF!</h1></body></html>"
        pdf_data = get_pdf(html_content, src_kind="html")
        print("Got PDF data of length:", len(pdf_data))

        # Example saving to file:
        filepath = get_pdf("https://pypi.org", egress="output.pdf", src_kind="url")
        print("PDF saved to:", filepath)


    """
    _kwargs = dict(
        dflt_pdfkit_kwargs,
        options=options,
        toc=toc,
        cover=cover,
        css=css,
        configuration=configuration,
        cover_first=cover_first,
        verbose=verbose,
    )

    # Determine the source kind if not explicitly provided.
    if src_kind is None:
        src_kind = _resolve_src_kind(src)
    elif src_kind == "md":
        src_kind = "markdown"

    if src_kind == "url":
        _kwargs.pop(
            "css", None
        )  # because from_url, for some reason, doesn't have a css argument

    _pdfkit_kwargs = dict(**_kwargs, **kwargs)
    _add_pdfkit_options = lambda func: partial(func, **_pdfkit_kwargs)

    # Helper: convert image (path or bytes) to single-page PDF bytes
    def _image_to_pdf_bytes(src_item):
        # src_item may be a path string or bytes
        try:
            import img2pdf

            if isinstance(src_item, (bytes, bytearray)):
                return img2pdf.convert(src_item)
            else:
                # img2pdf can accept filenames
                return img2pdf.convert(open(src_item, "rb"))
        except Exception:
            # Fallback to Pillow
            try:
                from PIL import Image

                if isinstance(src_item, (bytes, bytearray)):
                    buf = io.BytesIO(src_item)
                    im = Image.open(buf)
                else:
                    im = Image.open(src_item)

                try:
                    # ensure RGB; handle alpha
                    if im.mode in ("RGBA", "LA") or (
                        im.mode == "P" and "transparency" in im.info
                    ):
                        bg = Image.new("RGB", im.size, (255, 255, 255))
                        bg.paste(im, mask=im.split()[-1])
                        im_out = bg
                    else:
                        im_out = im.convert("RGB")
                    out = io.BytesIO()
                    im_out.save(out, format="PDF")
                    return out.getvalue()
                finally:
                    try:
                        im.close()
                    except Exception:
                        pass
            except Exception as e:
                raise RuntimeError(
                    "Cannot convert image to PDF bytes; please install img2pdf or Pillow"
                ) from e

    # Map the source kind to the corresponding pdfkit/function.
    func_for_kind = {
        "url": _add_pdfkit_options(pdfkit.from_url),
        "text": _add_pdfkit_options(pdfkit.from_string),
        "html": Pipe(io.StringIO, _add_pdfkit_options(pdfkit.from_file)),
        "file": _add_pdfkit_options(pdfkit.from_file),
        # egress=None to force bytes output in markdown:
        "markdown": partial(markdown_to_pdf, egress=None, **_pdfkit_kwargs),
        "image": lambda s: _image_to_pdf_bytes(s),
    }
    src_to_bytes_func = func_for_kind.get(src_kind)
    if src_to_bytes_func is None:
        raise ValueError(f"Unsupported src_kind: {src_kind}")

    # Generate the PDF bytes; passing False returns the bytes instead of writing to a file.
    pdf_bytes = src_to_bytes_func(src)

    # Resolve the egress processing function and apply it.
    egress_func = _resolve_bytes_egress(egress)
    return egress_func(pdf_bytes)
