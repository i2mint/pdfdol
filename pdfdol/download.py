"""Download PDF articles from markdown-formatted text.

Extracts ``[title](url)`` links from markdown and downloads the PDFs,
with validation (Content-Type check + %PDF magic byte check).

Main entry points::

    >>> download_articles(md_string, save_dir='~/Downloads')  # doctest: +SKIP
    >>> download_articles_by_section(md_string, rootdir='~/Downloads')  # doctest: +SKIP

"""

import os
import re

import requests

DFLT_SAVE_DIR = os.path.expanduser("~/Downloads")

DFLT_USER_AGENT = (
    "Mozilla/5.0 (compatible; pdfdol/0.1; " "+https://github.com/i2mint/pdfdol)"
)


def download_articles(
    md_string: str,
    save_dir: str = DFLT_SAVE_DIR,
    *,
    save_non_pdf: bool = False,
    verbose: bool = True,
):
    """Download articles from markdown-formatted text and save them as PDFs.

    Extracts links matching ``- **[title](url)**`` and downloads the URL.
    Only saves files whose Content-Type is ``application/pdf`` and whose
    first bytes are ``%PDF``.

    Parameters
    ----------
    md_string : str
        Markdown text containing ``- **[title](url)**`` links.
    save_dir : str
        Directory to save downloaded PDFs. Defaults to ``~/Downloads``.
    save_non_pdf : bool
        If True, save non-PDF responses with a ``_non_pdf.html`` suffix.
    verbose : bool
        Print progress messages.

    Returns
    -------
    list
        URLs that failed to download or were not valid PDFs.

    Tips
    ----
    When your knowledge base has many files, consider aggregating them
    into a single PDF with ``pdfdol.concat_pdfs``.
    """
    save_dir = os.path.expanduser(save_dir)
    assert os.path.exists(save_dir), f"Directory not found: {save_dir}"

    def clog(msg):
        if verbose:
            print(msg)

    pattern = r"- \*\*\[(.*?)\]\((.*?)\)\*\*"
    matches = re.findall(pattern, md_string)

    failed_urls = []

    for title, url in matches:
        sanitized_title = re.sub(r"[^\w\-_\. ]", "_", title)
        filename = f"{sanitized_title}.pdf"
        filepath = os.path.join(save_dir, filename)

        try:
            response = requests.get(
                url,
                stream=True,
                headers={"User-Agent": DFLT_USER_AGENT},
            )
            response.raise_for_status()

            content_type = response.headers.get("Content-Type", "")
            if "application/pdf" not in content_type:
                clog(
                    f"Skipped (HTML or non-PDF): {title} from {url} "
                    f"(Content-Type: {content_type})"
                )
                if save_non_pdf:
                    non_pdf_path = os.path.join(
                        save_dir, f"{sanitized_title}_non_pdf.html"
                    )
                    with open(non_pdf_path, "wb") as f:
                        for chunk in response.iter_content(chunk_size=8192):
                            f.write(chunk)
                    clog(f"Non-PDF content saved to: {non_pdf_path}")
                failed_urls.append(url)
                continue

            first_chunk = next(response.iter_content(chunk_size=8192))
            if not first_chunk.startswith(b"%PDF"):
                clog(f"Invalid PDF content: {title} from {url}")
                if save_non_pdf:
                    invalid_path = os.path.join(
                        save_dir, f"{sanitized_title}_invalid.pdf"
                    )
                    with open(invalid_path, "wb") as f:
                        f.write(first_chunk)
                        for chunk in response.iter_content(chunk_size=8192):
                            f.write(chunk)
                    clog(f"Invalid PDF content saved to: {invalid_path}")
                failed_urls.append(url)
                continue

            with open(filepath, "wb") as f:
                f.write(first_chunk)
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

            clog(f"Downloaded: {title} -> {filepath}")
        except Exception as e:
            clog(f"Failed to download {title} from {url}: {e}")
            failed_urls.append(url)

    return failed_urls


def download_articles_by_section(
    md_string: str,
    rootdir: str = None,
    save_non_pdf: bool = False,
    *,
    section_marker: str = r"###",
):
    """Download articles organized by markdown sections into subdirectories.

    Parses sections delimited by ``section_marker`` (default ``###``) and
    creates a subdirectory for each section, then downloads articles within
    each section using :func:`download_articles`.

    Parameters
    ----------
    md_string : str
        Markdown text with sections and article links.
    rootdir : str
        Root directory for section subdirectories. Defaults to ``~/Downloads``.
    save_non_pdf : bool
        Whether to save non-PDF content.
    section_marker : str
        Regex pattern for section headings (default ``###``).

    Returns
    -------
    dict
        Section names as keys, lists of failed URLs as values.
    """
    if rootdir is None:
        rootdir = os.path.expanduser("~/Downloads")

    os.makedirs(rootdir, exist_ok=True)

    section_pattern = section_marker + r" (.*?)\n(.*?)(?=\n" + section_marker + r"|\Z)"
    sections = re.findall(section_pattern, md_string, re.DOTALL)

    failed_urls_by_section = {}

    for section_title, section_content in sections:
        sanitized = (
            re.sub(r"[^\w\s]", "", section_title).strip().replace(" ", "_").lower()
        )
        section_dir = os.path.join(rootdir, sanitized)
        os.makedirs(section_dir, exist_ok=True)

        print(f"\nProcessing section: {section_title} (Directory: {section_dir})")

        failed_urls = download_articles(
            section_content, save_dir=section_dir, save_non_pdf=save_non_pdf
        )
        failed_urls_by_section[section_title] = failed_urls

    return failed_urls_by_section
