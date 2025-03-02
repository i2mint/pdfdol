"""Base objects for pdfdol"""

from typing import Iterable
from dol import Files, wrap_kvs, Pipe, KeyCodecs, add_ipython_key_completions
from pypdf import PdfReader
from io import BytesIO

bytes_to_pdf_reader_obj = Pipe(BytesIO, PdfReader)


def pdf_reader_to_text_pages(pdf_reader: PdfReader) -> Iterable[str]:
    for page in pdf_reader.pages:
        yield page.extract_text()


pdf_reader_to_text_pages_list = Pipe(pdf_reader_to_text_pages, list)

read_pdf_text = pdf_reader_to_text_pages_list  # backwards compatibility alias

pdf_bytes_to_text_pages = Pipe(bytes_to_pdf_reader_obj, pdf_reader_to_text_pages)

page_sep = "\n\n-------------------------------------------------------------------\n\n"
pdf_bytes_to_text = Pipe(
    pdf_bytes_to_text_pages, page_sep.join
)  # TODO: Use Parametrizable Pipe to make page_sep a parameter

# wrappers ----------------------------------------------------

bytes_to_pdf_obj_wrap = wrap_kvs(obj_of_data=bytes_to_pdf_reader_obj)

filter_for_pdf_extension = KeyCodecs.suffixed(".pdf")

# bytes to pdf text pages ----------------------------------------------------
bytes_to_pdf_text_pages_wrap = Pipe(
    bytes_to_pdf_obj_wrap, wrap_kvs(obj_of_data=pdf_reader_to_text_pages_list)
)

pdf_files_pages_reader_wrap = Pipe(
    filter_for_pdf_extension, bytes_to_pdf_text_pages_wrap, add_ipython_key_completions
)

PdfFilesPagesReader = pdf_files_pages_reader_wrap(Files)

PdfFilesReader = PdfFilesPagesReader  # backwards compatibility alias

# bytes to pdf text (concatenated pages) ----------------------------------------

bytes_to_pdf_text_wrap = wrap_kvs(obj_of_data=pdf_bytes_to_text)

pdf_files_text_reader_wrap = Pipe(
    filter_for_pdf_extension, bytes_to_pdf_text_wrap, add_ipython_key_completions
)

PdfTextReader = pdf_files_text_reader_wrap(Files)


# ---------------------------------------------------------------------
# Further ideas:
# Divide read_pdf_text into a pdf_reader_to_text_pages generator and a list function.
# Specify edges (meshed style) to then be make any pipeline (from any source to any sink) with the same steps.
# This would allow for a more flexible and modular approach to the pipeline.
# write_bytes_to_file = lambda b, f: Path(f).write_bytes(b)
# edges = {
#     ('bytes', 'file'): write_bytes_to_file,  # needs filepath spec!
#     ('bytes', 'bytesio'): BytesIO,
#     ('bytesio', 'pdf_reader'): PdfReader,
#     ('pdf_reader', 'text_pages_iter'): pdf_reader_to_text_pages_iter,
#     ('text_pages_iter', 'text_pages'): list,
#     ('text_pages', 'string'): page_sep.join,
# }
