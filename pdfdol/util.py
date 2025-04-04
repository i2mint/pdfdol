"""Utils for pdfdol"""

from pypdf import PdfReader, PdfWriter, PageObject
from typing import Iterable, Mapping, Union, Callable, Iterable
import io
import os
from pathlib import Path
from contextlib import redirect_stderr, nullcontext, suppress

from dol import Pipe, filt_iter, wrap_kvs, Files

filter_pdfs = filt_iter.suffixes(".pdf")
filter_pdfs_and_images = filt_iter.suffixes(
    (".pdf", ".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tiff")
)

PdfPages = Iterable[PageObject]
Filepath = str
PdfPagesSpec = Union[PdfPages, Filepath]


# TODO: generalize functions so they can work with pdf objects, not just filepaths
def add_affix(string: str, *, prefix: str = None, suffix: str = None):
    """Add a suffix and/or prefix to a filepath.

    >>> add_affix('file.pdf', prefix='new_', suffix='_for_you')
    'new_file_for_you.pdf'
    """
    if suffix:
        string = string.rsplit(".", 1)
        string = f"{string[0]}{suffix}.{string[1]}"
    if prefix:
        string = f"{prefix}{string}"
    return string


def affix_source_if_target_not_given(
    src: str, target: str = None, *, prefix: str = None, suffix: str = None
):
    """
    If target is None, affix the source filepath and return it.

    >>> affix_source_if_target_not_given(
    ...     'file.pdf', 'target_exists', prefix='new_', suffix='_for_you'
    ... )
    'target_exists'
    >>> affix_source_if_target_not_given(
    ...     'file.pdf', None, prefix='new_', suffix='_for_you'
    ... )
    'new_file_for_you.pdf'

    """
    if target is None:
        return add_affix(src, prefix=prefix, suffix=suffix)
    return target


def ensure_pages(pages: PdfPagesSpec) -> PdfPages:
    """Ensure that pages are given as a sequence of PageObject objects."""
    if isinstance(pages, str):
        filepath = pages
        return PdfReader(filepath).pages
    return pages


def is_page_empty(page, min_n_characters: int = 1) -> bool:
    """Check if a PDF page is empty."""
    text = page.extract_text()
    return len(text.strip()) < min_n_characters


def remove_empty_pages(
    pages: PdfPagesSpec,
    output_path: str = None,
    *,
    page_is_empty: Callable = None,
    suppress_warnings: bool = True,
):
    """Remove empty pages from a PDF file."""

    if isinstance(pages, str) and output_path is None:
        filepath = pages
        output_path = affix_source_if_target_not_given(
            filepath, output_path, suffix="_without_empty_pages"
        )
    assert isinstance(
        output_path, str
    ), f"output_path must be a string, not {output_path}"

    pages = ensure_pages(pages)

    if page_is_empty is None:
        page_is_empty = is_page_empty

    writer = PdfWriter()

    context_manager = (
        nullcontext()
        if not suppress_warnings
        else redirect_stderr(open(os.devnull, "w"))
    )

    with context_manager:
        for i, page in enumerate(pages):
            if not page_is_empty(page):
                writer.add_page(page)

    with open(output_path, "wb") as out_pdf:
        writer.write(out_pdf)

    return output_path


# ---------------------------------------------------------------------------------
# Sourcing pdfs
from typing import Mapping, Union, Iterable
import io
from dol import written_bytes


# TODO: Generalize to allow html_filepaths to be mappings (with html as values)
with suppress(ImportError, ModuleNotFoundError):
    from weasyprint import HTML

    def _html_bytes_to_pdf_bytes_writer(html_bytes, buffer):
        return HTML(io.BytesIO(html_bytes)).write_pdf(buffer)

    html_bytes_to_pdf_bytes = written_bytes(_html_bytes_to_pdf_bytes_writer)

    def html_to_pdf_w_weasyprint(
        htmls: Union[Filepath, Iterable[Filepath]],
        save_filepath="htmls_to_pdf.pdf",
    ):
        """Convert one or several HTML files into a single PDF file."""
        if isinstance(htmls, Mapping):
            pdf_bytes = map(html_bytes_to_pdf_bytes, htmls.values())
        else:
            if isinstance(htmls, str):
                htmls = [htmls]
            if not isinstance(htmls, Iterable):
                raise TypeError(
                    f"htmls must be an iterable of filepaths or a mapping, not {htmls}"
                )
            html_file_bytes = map(lambda x: Path(x).read_bytes(), htmls)
            pdf_bytes = map(html_bytes_to_pdf_bytes, html_file_bytes)

        combined_pdf_bytes = concat_pdf_bytes(pdf_bytes)

        if save_filepath:
            Path(save_filepath).write_bytes(combined_pdf_bytes)
            return save_filepath
        else:
            return combined_pdf_bytes


with suppress(ImportError, ModuleNotFoundError):
    import pdfkit

    DFLT_OPTIONS = {
        "enable-local-file-access": None,
        "page-size": "A4",  # Ensure consistent page size
        "disable-smart-shrinking": None,  # Disable smart shrinking to avoid unexpected layout changes
    }

    def html_to_pdf_w_pdfkit(
        html_filepaths: Union[Filepath, Iterable[Filepath]],
        save_filepath="htmls_to_pdf.pdf",
        *,
        options=DFLT_OPTIONS,
    ):
        """Convert one or several HTML files into a single PDF file."""

        pdfkit.from_file(html_filepaths, save_filepath, options=options)
        return save_filepath


# choose the first available html_to_pdf function
preferences_for_html_to_pdf = ["html_to_pdf_w_weasyprint", "html_to_pdf_w_pdfkit"]

for pref in preferences_for_html_to_pdf:
    if pref in globals():
        html_to_pdf = globals()[pref]
        break
else:

    def html_to_pdf(*args, **kwargs):
        raise ImportError(
            "You need to have either weasyprint or pdfkit installed to use html_to_pdf"
        )


# ---------------------------------------------------------------------------------
# Pdf concatenation
# TODO: Add some functionality to prefix/suffix pdf pages (useful when concatenating)

bytes_to_pdf_reader_obj = Pipe(io.BytesIO, PdfReader)


def get_file_extension(filename):
    return os.path.splitext(filename)[1].lower()


def image_bytes_to_pdf_bytes(image_bytes):
    """Convert image bytes to PDF bytes."""
    from PIL import Image  # pip install Pillow

    image = Image.open(io.BytesIO(image_bytes))
    if image.mode in ("RGBA", "LA"):
        image = image.convert("RGB")
    output = io.BytesIO()
    image.save(output, format="PDF")
    return output.getvalue()


def key_and_bytes_to_pdf_bytes(key, data_bytes):
    extension = get_file_extension(key)
    if extension in {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tiff"}:
        return image_bytes_to_pdf_bytes(data_bytes)
    return data_bytes


from operator import methodcaller

# equivalent to lambda pdf_filepath: Path(pdf_filepath).write_bytes():
file_to_bytes = Pipe(Path, methodcaller("read_bytes"))


# TODO: Look at the concat patterns here and see how they can be generalized to
#    other file types, by parametrizing the concat operation.
def concat_pdf_readers(pdf_readers: Iterable[PdfReader]) -> PdfWriter:
    """Concatenate multiple PdfReader objects into a single PdfWriter object."""
    writer = PdfWriter()
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


DFLT_SAVE_PDF_NAME = "combined.pdf"


def concat_pdf_files(pdf_filepaths: Iterable[str], save_filepath=DFLT_SAVE_PDF_NAME):
    """Concatenate multiple PDF files into a single PDF file."""
    pdf_bytes = map(file_to_bytes, pdf_filepaths)
    combined_pdf_bytes = concat_pdf_bytes(pdf_bytes)
    Path(save_filepath).write_bytes(combined_pdf_bytes)


# TODO: Generalize to allow pdf_source to be a mapping of any keys to pdf bytes (not necessarily filepaths)
def concat_pdfs(
    pdf_source: Union[Iterable[bytes], Mapping[str, bytes]],
    save_filepath=False,
    *,
    filter_extensions=False,
    key_order: Union[Callable, Iterable] = None,
    **kwargs,
) -> Union[str, bytes]:
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
    >>> pdf_bytes = concat_pdfs(s, key_order=sorted)  # doctest: +SKIP

    """
    _inputs = locals()
    if isinstance(pdf_source, Mapping):
        filter_extensions = kwargs.get(
            "filter_pdf_extension", filter_extensions
        )  # backwards compatibility

        if filter_extensions:
            pdf_source = filter_pdfs_and_images(pdf_source)

        if key_order is not None:
            if callable(key_order):
                keys = sorted(pdf_source.keys(), key=key_order)
            else:
                keys = key_order
            pdf_source = {k: pdf_source[k] for k in keys}

        _pdf_source = wrap_kvs(pdf_source, postget=key_and_bytes_to_pdf_bytes)
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
                    f"File {save_filepath} already exists. Specify your save_filepath"
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
