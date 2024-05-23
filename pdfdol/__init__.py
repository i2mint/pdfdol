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

from pdfdol.base import PdfFilesReader, pdf_files_reader_wrap
from pdfdol.util import concat_pdfs
