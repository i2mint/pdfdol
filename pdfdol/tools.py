"""Pdf Tools."""

from functools import partial
from typing import Literal, Any
from collections.abc import Callable
import os
import io

import markdown
import pdfkit
import pypdf

from dol import Pipe, cache_iter, wrap_kvs, Files, filt_iter
from pathlib import Path
from operator import methodcaller

filter_pdfs_and_images = filt_iter.suffixes(
    (".pdf", ".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tiff")
)

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
    # Accept bytes input as well (image/PDF bytes)
    if isinstance(src, (bytes, bytearray)):
        # Check for PDF first
        if src.startswith(b"%PDF"):
            return "file"  # treat as PDF file bytes

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


def _resolve_bytes_egress(egress: None | str | Callable) -> Callable[[bytes], any]:
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
    egress: None | str | Callable = None,
    *,
    markdown_extensions=dflt_markdown_kwargs,
    **pdfkit_kwargs,
):
    pdfkit_kwargs = {**dflt_pdfkit_kwargs, **pdfkit_kwargs}

    if isinstance(md_src, str) and os.path.isfile(md_src):
        md_file = md_src
        with open(md_file, encoding="utf-8") as f:
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
    egress: None | str | Callable = None,
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
) -> bytes | Any:
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


def any_to_pdf_bytes(src, *, src_kind: SrcKind = None) -> bytes:
    """
    Convert any source (string, bytes, file path, URL, HTML, etc.) to PDF bytes.

    This is a convenience function that uses get_pdf with egress=None to always
    return PDF bytes regardless of the source type.

    Args:
        src: Source content - can be a file path, URL, HTML string, markdown,
             image bytes, etc.
        src_kind: Optional hint about the source type. If not provided, it will
                 be determined heuristically.

    Returns:
        bytes: PDF bytes

    Examples:
        >>> # Convert image bytes to PDF
        >>> image_bytes = open('image.png', 'rb').read()  # doctest: +SKIP
        >>> pdf_bytes = any_to_pdf_bytes(image_bytes)  # doctest: +SKIP

        >>> # Convert HTML string to PDF
        >>> html = "<h1>Hello World</h1>"
        >>> pdf_bytes = any_to_pdf_bytes(html, src_kind="html")  # doctest: +SKIP
    """
    # Special case: if src is already PDF bytes, return as-is
    if isinstance(src, (bytes, bytearray)) and src.startswith(b"%PDF"):
        return src

    return get_pdf(src, egress=None, src_kind=src_kind)


def key_and_value_to_pdf_bytes(key, value) -> bytes:
    """
    Convert a key-value pair to PDF bytes, using the key to determine the type.

    This replaces the old key_and_bytes_to_pdf_bytes function with a more general
    approach using any_to_pdf_bytes.

    Args:
        key: The key (usually a filename) used to infer the source type
        value: The value (usually bytes) to convert

    Returns:
        bytes: PDF bytes

    Raises:
        ValueError: If the file type is unsupported or conversion fails
    """
    # If it's already PDF bytes, return as-is
    if isinstance(value, bytes) and value.startswith(b"%PDF"):
        return value

    # For file-like keys, use the key to determine the source type
    if isinstance(key, str):
        extension = os.path.splitext(key)[1].lower()

        # Supported image formats
        if extension in {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tiff", ".webp"}:
            try:
                return any_to_pdf_bytes(value, src_kind="image")
            except Exception as e:
                raise ValueError(f"Failed to convert image file '{key}' to PDF: {e}")

        # Supported text/markup formats
        elif extension in {".html", ".htm"}:
            try:
                # HTML content should be string for pdfkit
                if isinstance(value, bytes):
                    value = value.decode("utf-8", errors="ignore")
                return any_to_pdf_bytes(value, src_kind="html")
            except Exception as e:
                raise ValueError(f"Failed to convert HTML file '{key}' to PDF: {e}")

        elif extension in {".md", ".markdown"}:
            try:
                # Markdown content should be string
                if isinstance(value, bytes):
                    value = value.decode("utf-8", errors="ignore")
                return any_to_pdf_bytes(value, src_kind="markdown")
            except Exception as e:
                raise ValueError(f"Failed to convert Markdown file '{key}' to PDF: {e}")

        elif extension == ".pdf":
            # Verify it's actually a PDF
            if isinstance(value, bytes) and value.startswith(b"%PDF"):
                return value
            else:
                raise ValueError(
                    f"File '{key}' has .pdf extension but is not a valid PDF"
                )

        # Unsupported file types
        else:
            raise ValueError(
                f"Unsupported file type '{extension}' for file '{key}'. "
                f"Supported types: .pdf, .png, .jpg, .jpeg, .bmp, .gif, .tiff, .webp, .html, .htm, .md, .markdown"
            )

    # If key is not a string, try auto-detection as last resort
    try:
        return any_to_pdf_bytes(value)
    except Exception as e:
        raise ValueError(f"Failed to convert value to PDF: {e}")


# ---------------------------------------------------------------------------------
# PDF metadata extraction

from typing import Union


def _resolve_pdf_src_to_reader(
    pdf_src: Union[str, bytes, pypdf.PdfReader],
) -> pypdf.PdfReader:
    """
    Convert various PDF source types to a PdfReader object.

    Args:
        pdf_src: Can be a file path (str), PDF bytes, or a PdfReader object

    Returns:
        pypdf.PdfReader: A PdfReader object

    Raises:
        ValueError: If pdf_src type is not supported or file doesn't exist

    Examples:
        >>> import tempfile
        >>> from pypdf import PdfWriter
        >>> # Create a temp PDF
        >>> writer = PdfWriter()
        >>> _ = writer.add_blank_page(width=200, height=200)
        >>> with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp:  # doctest: +ELLIPSIS
        ...     _ = writer.write(tmp)
        ...     tmp_path = tmp.name
        >>> # Test with filepath
        >>> reader = _resolve_pdf_src_to_reader(tmp_path)
        >>> isinstance(reader, pypdf.PdfReader)
        True
        >>> # Test with bytes
        >>> with open(tmp_path, 'rb') as f:
        ...     pdf_bytes = f.read()
        >>> reader = _resolve_pdf_src_to_reader(pdf_bytes)
        >>> isinstance(reader, pypdf.PdfReader)
        True
        >>> # Test with PdfReader
        >>> reader_in = pypdf.PdfReader(tmp_path)
        >>> reader = _resolve_pdf_src_to_reader(reader_in)
        >>> reader is reader_in
        True
        >>> import os
        >>> os.remove(tmp_path)
    """
    if isinstance(pdf_src, pypdf.PdfReader):
        return pdf_src
    elif isinstance(pdf_src, bytes):
        from pdfdol.base import bytes_to_pdf_reader_obj

        return bytes_to_pdf_reader_obj(pdf_src)
    elif isinstance(pdf_src, str):
        if not os.path.exists(pdf_src):
            raise ValueError(f"File not found: {pdf_src}")
        return pypdf.PdfReader(pdf_src)
    else:
        raise ValueError(
            f"pdf_src must be a file path (str), bytes, or PdfReader object, not {type(pdf_src)}"
        )


def pdf_to_metadata(pdf_src: Union[str, bytes, pypdf.PdfReader]) -> dict:
    """
    Extract metadata from a PDF source.

    Args:
        pdf_src: Can be a file path (str), PDF bytes, or a PdfReader object

    Returns:
        dict: Dictionary containing metadata fields (title, author, subject, etc.)
              Returns empty dict if no metadata or an error occurs.

    Examples:
        >>> from pathlib import Path
        >>> from pdfdol.tests.utils_for_testing import get_test_pdf_folder
        >>> test_folder = Path(get_test_pdf_folder())
        >>> pdf_path = test_folder / "sample_with_title.pdf"
        >>> metadata = pdf_to_metadata(str(pdf_path))
        >>> metadata.get('Title')
        'Sample PDF with Title'
        >>> metadata.get('Author')
        'Test Author'
    """
    try:
        reader = _resolve_pdf_src_to_reader(pdf_src)
        if reader.metadata:
            # Convert pypdf DocumentInformation to a regular dict
            # and normalize the keys (remove leading slash)
            return {key.lstrip("/"): value for key, value in reader.metadata.items()}
        return {}
    except Exception as e:
        # Optionally log the error instead of printing
        # For now, return empty dict on error
        return {}


def pdf_to_title(pdf_src: Union[str, bytes, pypdf.PdfReader]) -> str | None:
    """
    Extract the document title from a PDF source.

    Args:
        pdf_src: Can be a file path (str), PDF bytes, or a PdfReader object

    Returns:
        str | None: The title from the metadata, or None if not found or an error occurs.

    Examples:
        >>> from pathlib import Path
        >>> from pdfdol.tests.utils_for_testing import get_test_pdf_folder
        >>> test_folder = Path(get_test_pdf_folder())
        >>> # Test with file path
        >>> pdf_path = test_folder / "sample_with_title.pdf"
        >>> pdf_to_title(str(pdf_path))
        'Sample PDF with Title'
        >>> # Test with bytes
        >>> pdf_bytes = pdf_path.read_bytes()
        >>> pdf_to_title(pdf_bytes)
        'Sample PDF with Title'
        >>> # Test with PdfReader
        >>> reader = pypdf.PdfReader(str(pdf_path))
        >>> pdf_to_title(reader)
        'Sample PDF with Title'
        >>> # Test with no title
        >>> pdf_path_no_title = test_folder / "sample_pdf_1.pdf"
        >>> pdf_to_title(str(pdf_path_no_title)) is None
        True
    """
    metadata = pdf_to_metadata(pdf_src)
    title = metadata.get("title") or metadata.get("Title")
    if title:
        return title.strip()
    return None


# ---------------------------------------------------------------------------------
# Pdf concatenation helpers
from typing import Iterable, Mapping
import pypdf
from pathlib import Path
from operator import methodcaller

# Core helpers for PDF concatenation
bytes_to_pdf_reader_obj = Pipe(io.BytesIO, pypdf.PdfReader)
file_to_bytes = Pipe(Path, methodcaller("read_bytes"))
DFLT_SAVE_PDF_NAME = "combined.pdf"


def concat_pdf_readers(pdf_readers: Iterable[pypdf.PdfReader]) -> pypdf.PdfWriter:
    """Concatenate multiple PdfReader objects into a single PdfWriter object."""
    writer = pypdf.PdfWriter()
    for reader in pdf_readers:
        for page in reader.pages:
            writer.add_page(page)
    return writer


def concat_pdf_bytes(list_of_pdf_bytes: Iterable[bytes]) -> bytes:
    """Concatenate multiple PDF bytes into a single PDF bytes."""
    pdf_readers = map(bytes_to_pdf_reader_obj, list_of_pdf_bytes)
    writer = concat_pdf_readers(pdf_readers)
    output_buffer = io.BytesIO()
    writer.write(output_buffer)
    return output_buffer.getvalue()


def concat_pdf_files(pdf_filepaths: Iterable[str], save_filepath=DFLT_SAVE_PDF_NAME):
    """Concatenate multiple PDF files into a single PDF file."""
    pdf_bytes = map(file_to_bytes, pdf_filepaths)
    combined_pdf_bytes = concat_pdf_bytes(pdf_bytes)
    Path(save_filepath).write_bytes(combined_pdf_bytes)


# TODO: Generalize to allow pdf_source to be a mapping of any keys to pdf bytes (not necessarily filepaths)
def concat_pdfs(
    pdf_source: Iterable[bytes] | Mapping[str, bytes],
    save_filepath=False,
    *,
    filter_extensions=False,
    key_order: Callable | Iterable = None,
    skip_errors=False,
    **kwargs,
) -> str | bytes:
    """
    Concatenate multiple PDFs and/or images given as a mapping of filepaths to bytes.

    Tip: Pdfs are aggregated in the order of the mapping's iteration order.
    If you need these to be in a specific order, you can use the key_order argument
    to sort the mapping, specifying either a callable that will be called on the keys
    to sort them, or specifying an iterable of keys in the desired order.
    Both the ordering function and the explicit list can also be used to filter
    out some keys.

    :param pdf_source: Mapping of filepaths to pdf bytes or an iterable of pdf bytes
    :param save_filepath: Filepath to save the concatenated pdf.
        If `True`, the save_filepath will be taken from the rootdir of the pdf_source
        that attribute exists, and no file of that name (+'.pdf') exists.
        If `False`, the pdf bytes are returned.
    :param filter_extensions: If True, only files with recognized extensions
        ('.pdf', '.png', '.jpg', '.jpeg', '.bmp', '.gif', '.tiff') are considered
    :param key_order: Callable or iterable of keys to sort the mapping

    :return: The save_filepath if it was specified, otherwise the concatenated pdf bytes

    >>> s = Files('~/Downloads/')  # doctest: +SKIP
    >>> pdf_bytes = concat_pdfs(s, save_filepath=False, key_order=sorted)  # doctest: +SKIP

    """
    _inputs = dict(locals())
    if isinstance(pdf_source, Mapping):
        filter_extensions = kwargs.get(
            "filter_pdf_extension", filter_extensions
        )  # backwards compatibility

        if filter_extensions:
            pdf_source = filter_pdfs_and_images(pdf_source)

        if key_order is not None:
            if callable(key_order):
                keys = sorted(pdf_source.keys(), key=key_order)
            elif isinstance(key_order, bool):
                reverse = not key_order
                keys = sorted(pdf_source.keys(), reverse=reverse)
            elif isinstance(key_order, Iterable):
                keys = key_order
            pdf_source = cache_iter(pdf_source, keys_cache=keys)

        # Handle error skipping
        if skip_errors:

            def safe_converter(key, value):
                return _safe_key_and_value_to_pdf_bytes(key, value, skip_errors=True)

            _pdf_source = wrap_kvs(pdf_source, postget=safe_converter)
            # Filter out None values (skipped files)
            pdf_bytes = [pdf for pdf in _pdf_source.values() if pdf is not None]
        else:
            _pdf_source = wrap_kvs(pdf_source, postget=key_and_value_to_pdf_bytes)
            pdf_bytes = _pdf_source.values()

        combined_pdf_bytes = concat_pdf_bytes(pdf_bytes)
    elif isinstance(pdf_source, str) and os.path.isdir(pdf_source):
        _inputs["pdf_source"] = Files(pdf_source)
        return concat_pdfs(**_inputs)
    else:
        assert isinstance(
            pdf_source, Iterable
        ), f"pdf_source must be an iterable (mapping or sequence), not {pdf_source}"
        combined_pdf_bytes = concat_pdf_bytes(pdf_source)

    if save_filepath is False:
        return combined_pdf_bytes
    elif save_filepath is True:
        if hasattr(pdf_source, "rootdir"):
            rootdir = pdf_source.rootdir
            rootdir_path = Path(rootdir)
            # get rootdir name and parent path
            parent, rootdir_name = rootdir_path.parent, rootdir_path.name
            save_filepath = os.path.join(parent, rootdir_name + ".pdf")
            if os.path.isfile(save_filepath):
                raise ValueError(
                    f"File {save_filepath} already exists. Specify your save_filepath "
                    "explicitly if you want to overwrite it."
                )
        else:
            save_filepath = DFLT_SAVE_PDF_NAME
    elif save_filepath is None:
        # TODO: Deprecating "None" as True as it was before. Change to None == False later
        raise ValueError(
            "save_filepath must be a string, not None. "
            "Specify a filepath to save the concatenated pdf."
        )
    else:
        assert isinstance(
            save_filepath, str
        ), f"save_filepath must be a boolean or a string, not {save_filepath}"

    Path(save_filepath).write_bytes(combined_pdf_bytes)
    return save_filepath


def _safe_key_and_value_to_pdf_bytes(key, value, skip_errors=False):
    """Wrapper that optionally skips conversion errors."""
    try:
        return key_and_value_to_pdf_bytes(key, value)
    except Exception as e:
        if skip_errors:
            print(f"Warning: Skipping file '{key}': {e}")
            return None  # Return None to indicate skipped file
        else:
            raise  # Re-raise the original exception
