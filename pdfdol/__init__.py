r"""Data Object Layers for PDF data.

>>> from pdfdol import PdfFilesReader
>>> from pdfdol.tests import get_test_pdf_folder
>>> folder_path = get_test_pdf_folder()
>>> s = PdfFilesReader(folder_path)
>>> sorted(s)
['sample_pdf_1', 'sample_pdf_2']
>>> assert s['sample_pdf_2'] == [
...     'Page 1\nThis is a sample text for testing Python PDF tools.'
... ]

"""

from pdfdol.base import (
    PdfReader,  # just pypdf's PdfReader
    PdfFilesReader,  # A Mapping giving you a dict-like API to pdf files in a folder (values are lists of text pages).
    PdfTextReader,  #  A Mapping giving you a dict-like API to pdf text in a folder (values are strings (concatenated text pages)).
    pdf_bytes_to_text_pages,  # A function to convert PDF bytes to a list of text pages
    pdf_bytes_to_text,  # A function to get the text "equivalent" of pdf bytes
    pdf_files_pages_reader_wrap,  # A store wrapper to get stores with list of pages as values
    pdf_files_text_reader_wrap,  # A store wrapper to get stores with aggregated pages text as values
)
from pdfdol.util import concat_pdfs  # concatenate pdfs
from pdfdol.tools import (
    get_pdf,  # Convert the given source to a PDF (bytes) and process it using the specified egress.
)
