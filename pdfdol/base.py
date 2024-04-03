"""Base objects for pdfdol"""

from dol import Files, wrap_kvs, Pipe, KeyCodecs, add_ipython_key_completions
from pypdf import PdfReader
from io import BytesIO

bytes_to_pdf_reader_obj = Pipe(BytesIO, PdfReader)


def read_pdf_text(pdf_reader):
    text_pages = []
    for page in pdf_reader.pages:
        text_pages.append(page.extract_text())
    return text_pages


bytes_to_pdf_obj_wrap = wrap_kvs(obj_of_data=bytes_to_pdf_reader_obj)

filter_for_pdf_extension = KeyCodecs.suffixed('.pdf')

bytes_to_pdf_text_pages = Pipe(
    bytes_to_pdf_obj_wrap, wrap_kvs(obj_of_data=read_pdf_text)
)

pdf_files_reader_wrap = Pipe(
    filter_for_pdf_extension, bytes_to_pdf_text_pages, add_ipython_key_completions
)

PdfFilesReader = pdf_files_reader_wrap(Files)
