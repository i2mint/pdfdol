"""Utils for testing"""

from importlib.resources import files


def get_test_pdf_folder():
    return str(files('pdfdol.tests') / 'data' / 'some_pdfs')
