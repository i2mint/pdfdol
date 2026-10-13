# pdfdol

Data Object Layers for PDF data.

```pycon
>>> from pdfdol import PdfFilesReader
>>> from pdfdol.tests import get_test_pdf_folder
>>> folder_path = get_test_pdf_folder()
>>> s = PdfFilesReader(folder_path)
>>> sorted(s)
['sample_pdf_1', 'sample_pdf_2', 'sample_with_title']
>>> assert s['sample_pdf_2'] == [
...     'Page 1\nThis is a sample text for testing Python PDF tools.'
... ]
```

### Modules

| [`base`](pdfdol.base.html.md#module-pdfdol.base)         | Base objects for pdfdol                             |
|----------------------------------------------------------------------------------|-----------------------------------------------------|
| [`download`](pdfdol.download.html.md#module-pdfdol.download) | Download PDF articles from markdown-formatted text. |
| [`tools`](pdfdol.tools.html.md#module-pdfdol.tools)       | Pdf Tools.                                          |
| [`util`](pdfdol.util.html.md#module-pdfdol.util)         | Utils for pdfdol                                    |
