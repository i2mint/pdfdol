# pdfdol.download

Download PDF articles from markdown-formatted text.

Extracts `[title](url)` links from markdown and downloads the PDFs,
with validation (Content-Type check + %PDF magic byte check).

Main entry points:

```default
>>> download_articles(md_string, save_dir='~/Downloads')
>>> download_articles_by_section(md_string, rootdir='~/Downloads')
```

### Functions

| [`download_articles`](#pdfdol.download.download_articles)(md_string[, save_dir, ...])   | Download articles from markdown-formatted text and save them as PDFs.   |
|--------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------|
| [`download_articles_by_section`](#pdfdol.download.download_articles_by_section)(md_string[, ...])  | Download articles organized by markdown sections into subdirectories.   |

### pdfdol.download.download_articles(md_string, save_dir='/home/runner/Downloads', , save_non_pdf=False, verbose=True)

Download articles from markdown-formatted text and save them as PDFs.

Extracts links matching `- **[title](url)**` and downloads the URL.
Only saves files whose Content-Type is `application/pdf` and whose
first bytes are `%PDF`.

* **Parameters:**
  * **md_string** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – Markdown text containing `- **[title](url)**` links.
  * **save_dir** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – Directory to save downloaded PDFs. Defaults to `~/Downloads`.
  * **save_non_pdf** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – If True, save non-PDF responses with a `_non_pdf.html` suffix.
  * **verbose** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – Print progress messages.
* **Returns:**
  * *list* – URLs that failed to download or were not valid PDFs.
  * *Tips*
  *  *—-*
  * *When your knowledge base has many files, consider aggregating them*
  * into a single PDF with `pdfdol.concat_pdfs`.

### pdfdol.download.download_articles_by_section(md_string, rootdir=None, save_non_pdf=False, , section_marker='###')

Download articles organized by markdown sections into subdirectories.

Parses sections delimited by `section_marker` (default `###`) and
creates a subdirectory for each section, then downloads articles within
each section using [`download_articles()`](#pdfdol.download.download_articles).

* **Parameters:**
  * **md_string** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – Markdown text with sections and article links.
  * **rootdir** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – Root directory for section subdirectories. Defaults to `~/Downloads`.
  * **save_non_pdf** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – Whether to save non-PDF content.
  * **section_marker** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – Regex pattern for section headings (default `###`).
* **Returns:**
  Section names as keys, lists of failed URLs as values.
* **Return type:**
  [*dict*](https://docs.python.org/3/builtins/stdtypes.html#dict)
