"""Test the base.py module"""

from pathlib import Path
from pypdf import PdfReader
from pdfdol.base import PdfFilesReader
from pdfdol.tests.utils_for_testing import get_test_pdf_folder


def test_pdf_files_reader():
    test_pdf_folder = get_test_pdf_folder()
    s = PdfFilesReader(str(test_pdf_folder))

    assert sorted(s) == ["sample_pdf_1", "sample_pdf_2", "sample_with_title"]
    assert s["sample_pdf_2"] == [
        "Page 1\nThis is a sample text for testing Python PDF tools."
    ]


def test_pdf_to_title_with_filepath():
    """Test pdf_to_title with a file path"""
    from pdfdol.tools import pdf_to_title

    test_pdf_folder = get_test_pdf_folder()
    pdf_path = Path(test_pdf_folder) / "sample_with_title.pdf"

    title = pdf_to_title(str(pdf_path))
    assert title == "Sample PDF with Title"


def test_pdf_to_title_with_bytes():
    """Test pdf_to_title with PDF bytes"""
    from pdfdol.tools import pdf_to_title

    test_pdf_folder = get_test_pdf_folder()
    pdf_path = Path(test_pdf_folder) / "sample_with_title.pdf"
    pdf_bytes = pdf_path.read_bytes()

    title = pdf_to_title(pdf_bytes)
    assert title == "Sample PDF with Title"


def test_pdf_to_title_with_pdf_reader():
    """Test pdf_to_title with a PdfReader object"""
    from pdfdol.tools import pdf_to_title

    test_pdf_folder = get_test_pdf_folder()
    pdf_path = Path(test_pdf_folder) / "sample_with_title.pdf"
    reader = PdfReader(str(pdf_path))

    title = pdf_to_title(reader)
    assert title == "Sample PDF with Title"


def test_pdf_to_title_no_title():
    """Test pdf_to_title when PDF has no title metadata"""
    from pdfdol.tools import pdf_to_title

    test_pdf_folder = get_test_pdf_folder()
    pdf_path = Path(test_pdf_folder) / "sample_pdf_1.pdf"

    title = pdf_to_title(str(pdf_path))
    assert title is None


def test_pdf_to_title_nonexistent_file():
    """Test pdf_to_title with non-existent file"""
    from pdfdol.tools import pdf_to_title

    title = pdf_to_title("/nonexistent/path/to/file.pdf")
    assert title is None


def test_pdf_to_metadata():
    """Test pdf_to_metadata function"""
    from pdfdol.tools import pdf_to_metadata

    test_pdf_folder = get_test_pdf_folder()
    pdf_path = Path(test_pdf_folder) / "sample_with_title.pdf"

    # Test with filepath
    metadata = pdf_to_metadata(str(pdf_path))
    assert metadata['Title'] == "Sample PDF with Title"
    assert metadata['Author'] == "Test Author"
    assert metadata['Subject'] == "Testing PDF metadata extraction"

    # Test with bytes
    pdf_bytes = pdf_path.read_bytes()
    metadata = pdf_to_metadata(pdf_bytes)
    assert metadata['Title'] == "Sample PDF with Title"

    # Test with PdfReader
    reader = PdfReader(str(pdf_path))
    metadata = pdf_to_metadata(reader)
    assert metadata['Title'] == "Sample PDF with Title"

    # Test with PDF without metadata
    pdf_path_no_meta = Path(test_pdf_folder) / "sample_pdf_1.pdf"
    metadata = pdf_to_metadata(str(pdf_path_no_meta))
    assert isinstance(metadata, dict)  # Should return empty dict, not None
