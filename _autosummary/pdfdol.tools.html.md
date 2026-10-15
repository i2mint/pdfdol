# pdfdol.tools

Pdf Tools.

### Functions

| `add_css`(html_text[, css])                                                                         |                                                                                                                                 |
|-----------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------------------|
| [`any_to_pdf_bytes`](#pdfdol.tools.any_to_pdf_bytes)(src, \*[, src_kind])              | Convert any source (string, bytes, file path, URL, HTML, etc.) to PDF bytes.                                                    |
| [`concat_pdf_bytes`](#pdfdol.tools.concat_pdf_bytes)(list_of_pdf_bytes)                | Concatenate multiple PDF bytes into a single PDF bytes.                                                                         |
| [`concat_pdf_files`](#pdfdol.tools.concat_pdf_files)(pdf_filepaths[, save_filepath])   | Concatenate multiple PDF files into a single PDF file.                                                                          |
| [`concat_pdf_readers`](#pdfdol.tools.concat_pdf_readers)(pdf_readers)                    | Concatenate multiple PdfReader objects into a single PdfWriter object.                                                          |
| [`concat_pdfs`](#pdfdol.tools.concat_pdfs)(pdf_source[, save_filepath, ...])      | Concatenate multiple PDFs and/or images given as a mapping of filepaths to bytes.                                               |
| [`ebook_convert_to_pdf`](#pdfdol.tools.ebook_convert_to_pdf)(source, \*[, extension, ...]) | Convert a file to PDF using Calibre's `ebook-convert`.                                                                          |
| [`find_ebook_convert`](#pdfdol.tools.find_ebook_convert)()                               | Find the `ebook-convert` binary from Calibre.                                                                                   |
| [`get_format_converter`](#pdfdol.tools.get_format_converter)(extension)                    | Get the registered PDF converter for a file extension.                                                                          |
| [`get_pdf`](#pdfdol.tools.get_pdf)(src[, egress, src_kind, options, ...])     | Convert the given source to a PDF (bytes) and process it using the specified egress.                                            |
| [`key_and_value_to_pdf_bytes`](#pdfdol.tools.key_and_value_to_pdf_bytes)(key, value)             | Convert a key-value pair to PDF bytes, using the key's file extension to select a converter from the format converter registry. |
| `markdown_to_pdf`(md_src[, egress, ...])                                                            |                                                                                                                                 |
| [`pdf_to_metadata`](#pdfdol.tools.pdf_to_metadata)(pdf_src)                           | Extract metadata from a PDF source.                                                                                             |
| [`pdf_to_title`](#pdfdol.tools.pdf_to_title)(pdf_src)                              | Extract the document title from a PDF source.                                                                                   |
| [`register_format_converter`](#pdfdol.tools.register_format_converter)(extensions, ...[, ...])  | Register a PDF converter function for one or more file extensions.                                                              |
| [`supported_extensions`](#pdfdol.tools.supported_extensions)()                             | Return file extensions that have registered PDF converters.                                                                     |

### pdfdol.tools.any_to_pdf_bytes(src, , src_kind=None)

Convert any source (string, bytes, file path, URL, HTML, etc.) to PDF bytes.

This is a convenience function that uses get_pdf with egress=None to always
return PDF bytes regardless of the source type.

* **Parameters:**
  * **src** – Source content - can be a file path, URL, HTML string, markdown,
    image bytes, etc.
  * **src_kind** ([`Literal`](https://docs.python.org/3/library/typing.html#typing.Literal)[`'url'`, `'html'`, `'file'`, `'md'`, `'markdown'`, `'text'`, `'image'`, `'ebook'`]) – Optional hint about the source type. If not provided, it will
    be determined heuristically.
* **Returns:**
  PDF bytes
* **Return type:**
  [`bytes`](https://docs.python.org/3/builtins/stdtypes.html#bytes)

### Examples

```pycon
>>> # Convert image bytes to PDF
>>> image_bytes = open('image.png', 'rb').read()
>>> pdf_bytes = any_to_pdf_bytes(image_bytes)
```

```pycon
>>> # Convert HTML string to PDF
>>> html = "<h1>Hello World</h1>"
>>> pdf_bytes = any_to_pdf_bytes(html, src_kind="html")
```

### pdfdol.tools.concat_pdf_bytes(list_of_pdf_bytes)

Concatenate multiple PDF bytes into a single PDF bytes.

* **Return type:**
  [`bytes`](https://docs.python.org/3/builtins/stdtypes.html#bytes)

### pdfdol.tools.concat_pdf_files(pdf_filepaths, save_filepath='combined.pdf')

Concatenate multiple PDF files into a single PDF file.

### pdfdol.tools.concat_pdf_readers(pdf_readers)

Concatenate multiple PdfReader objects into a single PdfWriter object.

* **Return type:**
  `PdfWriter`

### pdfdol.tools.concat_pdfs(pdf_source, save_filepath=False, , filter_extensions=False, key_order=None, skip_errors=False, toc=False, doc_header=None, outline=False, image_page_size=None, title=None, \*\*kwargs)

Concatenate multiple PDFs and/or images given as a mapping of filepaths to bytes.

#### TIP
Pdfs are aggregated in the order of the mapping’s iteration order.
If you need these to be in a specific order, you can use the key_order argument
to sort the mapping, specifying either a callable that will be called on the keys
to sort them, or specifying an iterable of keys in the desired order.
Both the ordering function and the explicit list can also be used to filter
out some keys.

* **Parameters:**
  * **pdf_source** (`Union`[[`Iterable`](https://docs.python.org/3/library/typing.html#typing.Iterable)[[`bytes`](https://docs.python.org/3/builtins/stdtypes.html#bytes)], [`Mapping`](https://docs.python.org/3/library/typing.html#typing.Mapping)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`bytes`](https://docs.python.org/3/builtins/stdtypes.html#bytes)]]) – Mapping of filepaths to pdf bytes or an iterable of pdf bytes
  * **save_filepath** – Filepath to save the concatenated pdf.
    If `True`, the save_filepath will be taken from the rootdir of the pdf_source
    that attribute exists, and no file of that name (+’.pdf’) exists.
    If `False`, the pdf bytes are returned.
  * **filter_extensions** – If True, only files with recognized extensions
    (‘.pdf’, ‘.png’, ‘.jpg’, ‘.jpeg’, ‘.bmp’, ‘.gif’, ‘.tiff’) are considered
  * **key_order** (`Union`[[`Callable`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Callable), [`Iterable`](https://docs.python.org/3/library/typing.html#typing.Iterable)]) – Callable or iterable of keys to sort the mapping
  * **toc** – Add a contents page whose lines link to each document. `True`, or a
    renderer callable (see `pdfdol.bundle.bundle_pdf_bytes`). Uses reportlab.
  * **doc_header** – Text of a band added above each document’s first page (so no
    content is covered): `True` for the key, a format string with `{key}`,
    `{start_page}`, `{n_pages}`, or a callable `key -> str`. Uses reportlab.
  * **outline** – Add one bookmark per document.
  * **image_page_size** – Fit and center each image on a page of this size
    (`'A4'`, `'letter'`, … or `(w, h)` points; landscape for wide images)
    instead of a page sized from its pixels. `None`: current behavior.
  * **title** – PDF title metadata (and contents page title).
* **Return type:**
  [*str*](https://docs.python.org/3/builtins/stdtypes.html#str) | [*bytes*](https://docs.python.org/3/builtins/stdtypes.html#bytes)

The `toc`, `doc_header`, `outline` and `title` options are implemented in
`pdfdol.bundle.bundle_pdf_bytes`, which you can call directly on converted pdfs.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`bytes`](https://docs.python.org/3/builtins/stdtypes.html#bytes)
* **Returns:**
  The save_filepath if it was specified, otherwise the concatenated pdf bytes

```pycon
>>> s = Files('~/Downloads/')
>>> pdf_bytes = concat_pdfs(s, save_filepath=False, key_order=sorted)
```

### pdfdol.tools.ebook_convert_to_pdf(source, , extension=None, ebook_convert_path=None)

Convert a file to PDF using Calibre’s `ebook-convert`.

Requires Calibre to be installed ([https://calibre-ebook.com/download](https://calibre-ebook.com/download)).

* **Parameters:**
  * **source** – File path (str/Path) or file content (bytes).
  * **extension** – File extension hint (e.g. `'.epub'`).  Required when
    *source* is bytes; auto-detected from file path otherwise.
  * **ebook_convert_path** – Explicit path to the `ebook-convert` binary.
    Auto-detected if not provided.
* **Returns:**
  PDF content.
* **Return type:**
  [*bytes*](https://docs.python.org/3/builtins/stdtypes.html#bytes)
* **Raises:**
  * [**FileNotFoundError**](https://docs.python.org/3/builtins/exceptions.html#FileNotFoundError) – If ebook-convert is not installed.
  * [**RuntimeError**](https://docs.python.org/3/builtins/exceptions.html#RuntimeError) – If the conversion fails.

### pdfdol.tools.find_ebook_convert()

Find the `ebook-convert` binary from Calibre.

Checks the system PATH first, then common platform-specific install
locations (macOS `Calibre.app`, Windows `Program Files`).

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`None`](https://docs.python.org/3/builtins/constants.html#None)
* **Returns:**
  Path to the binary, or `None` if not found.

### pdfdol.tools.get_format_converter(extension)

Get the registered PDF converter for a file extension.

Checks the built-in registry first.  For extensions supported by
Calibre’s `ebook-convert` (but not natively by pdfdol), returns an
ebook-convert-based converter on the fly.

* **Parameters:**
  **extension** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – File extension (e.g. `'.epub'` or `'epub'`).
* **Return type:**
  [`Callable`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Callable) | [`None`](https://docs.python.org/3/builtins/constants.html#None)
* **Returns:**
  Converter callable, or `None` if the format is not supported.

### pdfdol.tools.get_pdf(src, egress=None, , src_kind=None, options=None, toc=None, cover=None, css=None, configuration=None, cover_first=False, verbose=False, \*\*kwargs)

Convert the given source to a PDF (bytes) and process it using the specified egress.

The source (src) can be:

> - a URL (e.g. “[https://example.com](https://example.com)”)
> - an HTML string
> - a file path to an HTML file

The egress parameter determines how the PDF bytes are returned:

> - If None, returns the PDF as bytes.
> - If a string, treats it as a file path where the PDF is saved.
> - If a callable, applies it to the PDF bytes and returns its result.
>   For example, you may want to specify egress=pypdf.PdfReader to get an object
>   that provides an interface of all PDF components, or you might want to
>   upload the PDF to a cloud storage service.

The src_kind parameter allows explicit specification of the source kind (“url”, “html”, or “file”).
If not provided, it is determined heuristically using \_resolve_src_kind.

* **Parameters:**
  * **src** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – The source to convert.
  * **egress** ([`None`](https://docs.python.org/3/builtins/constants.html#None) | [`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`Callable`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Callable)) – How to handle the PDF bytes.
  * **src_kind** ([`Literal`](https://docs.python.org/3/library/typing.html#typing.Literal)[`'url'`, `'html'`, `'file'`, `'md'`, `'markdown'`, `'text'`, `'image'`, `'ebook'`]) – Explicit source kind; if omitted, determined automatically.
  * **options** – (optional) dict with wkhtmltopdf options, with or w/o ‘–’
  * **toc** – (optional) dict with toc-specific wkhtmltopdf options, with or w/o ‘–’
  * **cover** – (optional) string with url/filename with a cover html page
  * **css** – (optional) string with path to css file which will be added to a single input file
  * **configuration** – (optional) instance of pdfkit.configuration.Configuration()
  * **cover_first** – (optional) if True, cover always precedes TOC
  * **verbose** – (optional) By default ‘–quiet’ is passed to all calls, set this to False to get wkhtmltopdf output to stdout.
* **Returns:**
  The PDF bytes, or the result of processing them via the egress callable.
* **Return type:**
  [`bytes`](https://docs.python.org/3/builtins/stdtypes.html#bytes) | [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)

### Examples

# Example with a URL:
pdf_data = get_pdf(”[https://pypi.org](https://pypi.org)”, src_kind=”url”)
print(“Got PDF data of length:”, len(pdf_data))

# Example with HTML content:
html_content = “<html><body><h1>Hello, PDF!</h1></body></html>”
pdf_data = get_pdf(html_content, src_kind=”html”)
print(“Got PDF data of length:”, len(pdf_data))

# Example saving to file:
filepath = get_pdf(”[https://pypi.org](https://pypi.org)”, egress=”output.pdf”, src_kind=”url”)
print(“PDF saved to:”, filepath)

### pdfdol.tools.key_and_value_to_pdf_bytes(key, value)

Convert a key-value pair to PDF bytes, using the key’s file extension to
select a converter from the format converter registry.

* **Parameters:**
  * **key** – The key (usually a filename) whose extension determines the converter.
  * **value** – The value (usually bytes) to convert.
* **Returns:**
  PDF bytes
* **Return type:**
  [`bytes`](https://docs.python.org/3/builtins/stdtypes.html#bytes)
* **Raises:**
  [**ValueError**](https://docs.python.org/3/builtins/exceptions.html#ValueError) – If the file type is unsupported or conversion fails.

### pdfdol.tools.pdf_to_metadata(pdf_src)

Extract metadata from a PDF source.

* **Parameters:**
  **pdf_src** (`Union`[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`bytes`](https://docs.python.org/3/builtins/stdtypes.html#bytes), `PdfReader`]) – Can be a file path (str), PDF bytes, or a PdfReader object
* **Returns:**
  Dictionary containing metadata fields (title, author, subject, etc.)
  : Returns empty dict if no metadata or an error occurs.
* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### Examples

```pycon
>>> from pathlib import Path
>>> from pdfdol.tests.utils_for_testing import get_test_pdf_folder
>>> test_folder = Path(get_test_pdf_folder())
>>> pdf_path = test_folder / "sample_with_title.pdf"
>>> metadata = pdf_to_metadata(str(pdf_path))
>>> metadata.get('Title')
'Sample PDF with Title'
>>> metadata.get('Author')
'Test Author'
```

### pdfdol.tools.pdf_to_title(pdf_src)

Extract the document title from a PDF source.

* **Parameters:**
  **pdf_src** (`Union`[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`bytes`](https://docs.python.org/3/builtins/stdtypes.html#bytes), `PdfReader`]) – Can be a file path (str), PDF bytes, or a PdfReader object
* **Returns:**
  The title from the metadata, or None if not found or an error occurs.
* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`None`](https://docs.python.org/3/builtins/constants.html#None)

### Examples

```pycon
>>> from pathlib import Path
>>> from pdfdol.tests.utils_for_testing import get_test_pdf_folder
>>> test_folder = Path(get_test_pdf_folder())
>>> # Test with file path
>>> pdf_path = test_folder / "sample_with_title.pdf"
>>> pdf_to_title(str(pdf_path))
'Sample PDF with Title'
>>> # Test with bytes
>>> pdf_bytes = pdf_path.read_bytes()
>>> pdf_to_title(pdf_bytes)
'Sample PDF with Title'
>>> # Test with PdfReader
>>> reader = pypdf.PdfReader(str(pdf_path))
>>> pdf_to_title(reader)
'Sample PDF with Title'
>>> # Test with no title
>>> pdf_path_no_title = test_folder / "sample_pdf_1.pdf"
>>> pdf_to_title(str(pdf_path_no_title)) is None
True
```

### pdfdol.tools.register_format_converter(extensions, converter, , force=False)

Register a PDF converter function for one or more file extensions.

* **Parameters:**
  * **extensions** – File extension(s) to register (e.g. `'.epub'` or
    `['.epub', '.mobi']`).
  * **converter** – Callable that takes a source (filepath str or content bytes)
    and returns PDF bytes.
  * **force** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – If True, overwrite any existing converter for these extensions.

### pdfdol.tools.supported_extensions()

Return file extensions that have registered PDF converters.

Includes natively supported extensions and, when Calibre’s ebook-convert
is installed, additional ebook and document format extensions.

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`...`](https://docs.python.org/3/builtins/constants.html#Ellipsis)]
