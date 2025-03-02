"""Pdf Tools."""

from functools import partial
from typing import Literal, Callable, Union
import os

# Define the allowed source kinds
SrcKind = Literal["url", "html", "file"]


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
    s = src.strip()
    if s.startswith("http://") or s.startswith("https://"):
        return "url"
    elif "<html" in s.lower():
        return "html"
    elif os.path.exists(s):
        return "file"
    else:
        # Fallback: if it doesn't look like a URL or a file exists, assume HTML.
        return "html"


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
        :verbose: (optional) By default '--quiet' is passed to all calls, set this to False to get wkhtmltopdf output to stdout.


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
    import pdfkit

    _kwargs = dict(
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

    if src_kind == "url":
        _kwargs.pop(
            "css", None
        )  # because from_url, for some reason, doesn't have a css argument

    _add_options = lambda func: partial(func, **_kwargs, **kwargs)
    # Map the source kind to the corresponding pdfkit function.
    func_for_kind = {
        "url": _add_options(pdfkit.from_url),
        "html": _add_options(pdfkit.from_string),
        "file": _add_options(pdfkit.from_file),
    }
    src_to_bytes_func = func_for_kind.get(src_kind)
    if src_to_bytes_func is None:
        raise ValueError(f"Unsupported src_kind: {src_kind}")

    # Generate the PDF bytes; passing False returns the bytes instead of writing to a file.
    pdf_bytes = src_to_bytes_func(src, False)

    # Resolve the egress processing function and apply it.
    egress_func = _resolve_bytes_egress(egress)
    return egress_func(pdf_bytes)
