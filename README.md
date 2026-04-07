# pdfdol

Data Object Layer for PDF data

To install:	```pip install pdfdol```

[Documentation](https://i2mint.github.io/pdfdol/)


# Examples

## Pdf "Stores"

Get a dict-like object to list and read the pdfs of a folder, as text:

    >>> from pdfdol import PdfFilesReader
    >>> from pdfdol.tests import get_test_pdf_folder
    >>> folder_path = get_test_pdf_folder()
    >>> pdfs = PdfFilesReader(folder_path)
    >>> sorted(pdfs)
    ['sample_pdf_1', 'sample_pdf_2']
    >>> assert pdfs['sample_pdf_2'] == [
    ...     'Page 1\nThis is a sample text for testing Python PDF tools.'
    ... ]

See that the values of a `PdfFilesReader` are lists of pages. 
If you need strings (i.e. all the pages together) you can add a decoder like so:

```python
from dol import add_decoder
page_separator = '---------------------'
pdfs = add_decoder(pdfs, decoder=page_separator.join)
```

If you need this at the level of the class, just do this:

```python
from dol import add_decoder
page_separator = '---------------------'
FilesReader = add_decoder(PdfFilesReader, decoder=page_separator.join)
# and then
pdfs = FilesReader(folder_path)
# ...
```

If you need to concatinate a bunch of pdfs together, you can do so in many
ways. Here's one:

```python
from dol import Files
from pdfdol import concat_pdfs

s = Files('~/Downloads/cosmograph_documentation_pdfs/')
concat_pdfs(s, key_order=sorted)
```


## Converting ebooks and documents to PDF (optional Calibre integration)

pdfdol natively converts images, HTML, and Markdown to PDF.
For additional formats -- EPUB, MOBI, DOCX, ODT, DJVU, RTF, and 
[many more](https://manual.calibre-ebook.com/conversion.html) -- 
install [Calibre](https://calibre-ebook.com/download), which provides the
`ebook-convert` command-line tool.

pdfdol does **not** depend on Calibre; it auto-detects the tool at runtime
and uses it only for formats that have no built-in converter.

```python
from pdfdol import ebook_convert_to_pdf, find_ebook_convert

# Check whether Calibre is available
if find_ebook_convert():
    pdf_bytes = ebook_convert_to_pdf("book.epub")
```

You can also go through the usual `get_pdf` entry point -- it will
automatically route to `ebook-convert` when it recognises the file extension:

```python
from pdfdol import get_pdf
pdf_bytes = get_pdf("book.epub")                     # returns PDF bytes
get_pdf("book.epub", egress="book.pdf")              # saves to file
```

### Custom converters

pdfdol maintains a **format converter registry** that maps file extensions to
converter functions.  You can register your own:

```python
from pdfdol import register_format_converter, supported_extensions

def my_custom_converter(source):
    """source is a filepath (str) or raw bytes; must return PDF bytes."""
    ...

register_format_converter('.xyz', my_custom_converter)

# See everything that's currently supported
print(supported_extensions())
```


## Get pdf from various sources

Example with a URL

```py
pdf_data = get_pdf("https://pypi.org", src_kind="url")
print("Got PDF data of length:", len(pdf_data))
```

Example with HTML content

```py
html_content = "<html><body><h1>Hello, PDF!</h1></body></html>"
pdf_data = get_pdf(html_content, src_kind="html")
print("Got PDF data of length:", len(pdf_data))
```

Example saving to file

```py
filepath = get_pdf("https://pypi.org", egress="output.pdf", src_kind="url")
print("PDF saved to:", filepath)
```

