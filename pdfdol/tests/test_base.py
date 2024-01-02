"""Test the base.py module"""

from pdfdol.base import PdfFilesReader, pdf_files_reader_wrap
from pdfdol.tests.utils_for_testing import get_test_pdf_folder


def test_pdf_files_reader():
    test_pdf_folder = get_test_pdf_folder()
    s = PdfFilesReader(str(test_pdf_folder))

    assert sorted(s) == ['sample_pdf_1', 'sample_pdf_2']
    assert s['sample_pdf_2'] == [
        'Page 1\nThis is a sample text for testing Python PDF tools.'
    ]
