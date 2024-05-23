"""Utils for pdfdol"""

from pypdf import PdfReader, PdfWriter
from typing import Iterable, Mapping, Union, Callable, Iterable
import io
import os
from pathlib import Path

from dol import Pipe, filt_iter, cache_iter

filter_pdfs = filt_iter.suffixes('.pdf')

# ---------------------------------------------------------------------------------
# Pdf concatenation
# TODO: Add some functionality to prefix/suffix pdf pages (useful when concatenating)

bytes_to_pdf_reader_obj = Pipe(io.BytesIO, PdfReader)

from operator import methodcaller

# equivalent to lambda pdf_filepath: Path(pdf_filepath).write_bytes():
file_to_bytes = Pipe(Path, methodcaller('read_bytes'))


# TODO: Look at the concat patterns here and see how they can be generalized to
#    other file types, by parametrizing the concat operation.
def concat_pdf_readers(pdf_readers: Iterable[PdfReader]) -> PdfWriter:
    """Concatenate multiple PdfReader objects into a single PdfWriter object."""
    writer = PdfWriter()

    # Iterate over the iterable of PdfReader objects
    for reader in pdf_readers:
        # Append all pages of the current pdf to the writer object
        for page_num in range(len(reader.pages)):
            writer.add_page(reader.pages[page_num])

    return writer


def concat_pdf_bytes(list_of_pdf_bytes: Iterable[bytes]) -> bytes:
    """Concatenate multiple PDF bytes into a single PDF bytes."""
    pdf_readers = map(bytes_to_pdf_reader_obj, list_of_pdf_bytes)
    writer = concat_pdf_readers(pdf_readers)
    output_buffer = io.BytesIO()
    writer.write(output_buffer)
    return output_buffer.getvalue()


DFLT_SAVE_PDF_NAME = 'combined.pdf'


def concat_pdf_files(pdf_filepaths: Iterable[str], save_filepath=DFLT_SAVE_PDF_NAME):
    """Concatenate multiple PDF files into a single PDF file."""
    pdf_bytes = map(file_to_bytes, pdf_filepaths)
    combined_pdf_bytes = concat_pdf_bytes(pdf_bytes)
    Path(save_filepath).write_bytes(combined_pdf_bytes)


def concat_pdfs(
    pdf_source: Mapping[str, bytes],
    save_filepath=None,
    *,
    filter_pdf_extension=False,
    key_order: Union[Callable, Iterable] = None,
):
    """
    Concatenate multiple PDFs given as a mapping of filepaths to bytes.

    Tip: Pdfs are aggregated in the order of the mapping's iteration order.
    If you need these to be in a specific order, you can use the key_order argument
    to sort the mapping, specifying either a callable that will be called on the keys
    to sort them, or specifying an iterable of keys in the desired order.
    Both the ordering function and the explicit list can also be used to filter
    out some keys.

    :param pdf_source: Mapping of filepaths to pdf bytes
    :param save_filepath: Filepath to save the concatenated pdf.
        If not given, the save_filepath will be taken from the rootdir of the pdf_source
        that attribute exists, and no file of that name (+'.pdf') exists.
    :param filter_pdf_extension: If True, only pdf files are considered
    :param key_order: Callable or iterable of keys to sort the mapping

    >>> s = Files('~/Downloads/')  # doctest: +SKIP
    >>> concat_pdfs(s, key_order=sorted)  # doctest: +SKIP

    """
    if filter_pdf_extension:
        pdf_source = filter_pdfs(pdf_source)
    if key_order is not None:
        pdf_source = cache_iter(pdf_source, keys_cache=key_order)

    if save_filepath is None:
        if hasattr(pdf_source, 'rootdir'):
            rootdir = pdf_source.rootdir
            rootdir_path = Path(rootdir)
            # get rootdir name and parent path
            parent, rootdir_name = rootdir_path.parent, rootdir_path.name
            save_filepath = os.path.join(parent, rootdir_name + '.pdf')
            if os.path.isfile(save_filepath):
                raise ValueError(
                    f"File {save_filepath} already exists. Specify your save_filepath"
                    "explicitly if you want to overwrite it."
                )
        else:
            save_filepath = DFLT_SAVE_PDF_NAME
    pdf_bytes = pdf_source.values()
    combined_pdf_bytes = concat_pdf_bytes(pdf_bytes)
    Path(save_filepath).write_bytes(combined_pdf_bytes)
