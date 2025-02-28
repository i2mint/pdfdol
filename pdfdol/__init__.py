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
    PdfFilesReader,  # A Mapping giving you a dict-like API to pdf files in a folder.
    pdf_files_reader_wrap,  # To create a PdfFilesReader for different sources than a folder.
)
from pdfdol.util import concat_pdfs  # concatenate pdfs
from pdfdol.tools import (
    get_pdf,  # Convert the given source to a PDF (bytes) and process it using the specified egress.
)
