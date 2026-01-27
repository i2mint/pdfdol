"""Utils for pdfdol"""

from pypdf import PdfReader, PdfWriter, PageObject
from typing import Union
from collections.abc import Iterable, Mapping, Callable, Iterable
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
