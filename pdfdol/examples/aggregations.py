"""A few examples of functions to aggregate PDF content

This module provides a helper to aggregate a directory (or iterable) of
images into a single PDF. The key parameter `sort_dir_files` is a
callable that receives the raw directory listing (list of path strings)
and returns a (possibly filtered, reordered) list of paths. The default
is the builtin `sorted` which preserves the usual behaviour; however a
custom callable can be used to filter out non-image files or reorder
entries before aggregation.
"""

from pathlib import Path
import os
from typing import Iterable, Union, Callable, Optional
from ..util import concat_pdfs


def sorted_image_files(
    paths,
    image_extensions=(".png", ".jpg", ".jpeg", ".tiff", ".bmp", ".gif", ".webp"),
):
    """
    Sort image files by their natural order.

    This function filters the input paths to include only those with
    image file extensions, and then sorts them.
    """
    return sorted(x for x in paths if Path(x).suffix.lower() in image_extensions)


def images_to_pdf(
    images: Union[str, Path, Iterable],
    egress: Optional[Union[str, Path, Callable]] = None,
    *,
    sort_dir_files: Callable[[list], list] = sorted_image_files,
    _get_pdf_egress=None,
):
    """
    Aggregate a folder (or iterable) of images into a single PDF (one image per page).

    Parameters
    - images: either a folder path (str/Path), a path to a single image, or an iterable
      of items accepted by `get_pdf` (file paths, bytes, URLs, ...).
    - egress:
        - if callable: called with the resulting PDF bytes and its return value is returned.
        - if "bytes" or False or None: the raw PDF bytes are returned.
        - if a str/Path: treated as a filesystem path to write the PDF to; the path (str)
          is returned after writing.
    - sort_dir_files: A callable that accepts the raw directory listing (a list of
      path strings) and returns a list of paths (or strings).
      The default is sorted_image_files, which filters for files having image extensions,
      and sorts these paths by lexicographic order.
      The callable may also filter the paths (useful when the
      directory contains non-image files) or reorder them in any custom way.

    Notes:
        - Uses `get_pdf(item, egress=None)` for each item to obtain a single-page
            PDF blob (egress=None forces get_pdf to return bytes instead of writing to a file).
    - Uses `concat_pdfs(...)` to combine all single-page PDF blobs into one PDF bytes object.
    """
    # lazy import to avoid ordering issues
    from ..tools import get_pdf  # noqa: F401

    # Normalize images iterable
    if isinstance(images, (str, Path)):
        p = Path(images)
        if p.is_dir():
            # take the raw directory listing as strings so the caller's
            # sort_dir_files can operate and optionally filter
            raw_entries = [str(x) for x in p.iterdir()]
            imgs = sort_dir_files(raw_entries) if sort_dir_files else raw_entries
        else:
            imgs = [str(p)]
    else:
        imgs = list(images)

    # Convert each image-like item to PDF bytes via get_pdf
    pdf_blobs = []
    for item in imgs:
        # get_pdf should accept paths, bytes, urls, etc. Request bytes egress.
        pdf_bytes = get_pdf(
            str(item) if isinstance(item, (Path,)) else item, egress=_get_pdf_egress
        )
        if not isinstance(pdf_bytes, (bytes, bytearray)):
            raise TypeError(f"get_pdf did not return bytes for item {item!r}")
        pdf_blobs.append(bytes(pdf_bytes))

    if not pdf_blobs:
        # prefer raising so caller knows nothing was aggregated
        raise ValueError("No images found / provided to aggregate")

    combined = concat_pdfs(pdf_blobs)

    # handle egress
    if callable(egress):
        return egress(combined)

    # treat strings/Paths as file paths to save to
    if isinstance(egress, (str, Path)):
        out_path = Path(egress)
        # if a directory is passed, write to <dir>/images.pdf
        if out_path.is_dir() or str(out_path).endswith(("/", os.path.sep)):
            out_path = out_path / "images.pdf"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "wb") as fp:
            fp.write(combined)
        return str(out_path)

    # default: return bytes
    return combined
