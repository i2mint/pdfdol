"""A few examples of functions to aggregate PDF content

This module provides a helper to aggregate a directory (or iterable) of
images into a single PDF. The key parameter `sort_dir_files` is a
callable that receives the raw directory listing (list of path strings)
and returns a (possibly filtered, reordered) list of paths. The default
is the builtin `sorted` which preserves the usual behaviour; however a
custom callable can be used to filter out non-image files or reorder
entries before aggregation.

if __name__ == "__main__":
    # Assume you have a folder with image files.
    # Replace the following path with the actual directory containing your images.
    image_folder = Path("/path/to/your/images")
    output_pdf = Path("demo_output.pdf")

    # Optional: If you want to add captions, provide a list with one caption per image.
    # Ensure the list length matches the number of images in the folder.
    captions = [
        "First image caption",
        "Second image caption",
        "Third image caption",
        # ... add more captions as needed
    ]

    try:
        # Create the PDF by aggregating images from the folder.
        # The egress parameter is set to a file path to write the output.
        result = images_to_pdf(image_folder, egress=output_pdf, captions=captions)
        print("PDF successfully created at:", result)
    except Exception as err:
        print("An error occurred while creating PDF:", err)
"""

from pathlib import Path
import os
from typing import Iterable, Union, Callable, Optional
from ..util import concat_pdfs
import base64
import imghdr
import io
import markdown
import pdfkit
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from reportlab.platypus import Paragraph, Frame
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch


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
    captions: Optional[Iterable[str]] = None,
    # Common layout controls forwarded to mk_image_and_caption_pdf_page
    image_fraction: Optional[float] = None,
    horizontal_margin: Optional[float] = None,
    align: Optional[str] = None,
    mk_page_kwargs: Optional[dict] = None,
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

    # If captions provided, validate length and ensure it's a list
    if captions is not None:
        caps = list(captions)
        if len(caps) != len(imgs):
            raise ValueError(
                f"Captions ({len(caps)=}) must be the same length as images ({len(imgs)=})"
            )
    else:
        caps = None

    # Convert each image-like item to PDF bytes via get_pdf or mk_image_and_caption_pdf_page
    pdf_blobs = []

    def _load_image_for_reportlab(item):
        """Return an ImageReader or raise.

        Accepts bytes, file paths, or URLs (URL requires requests; otherwise raise).
        """
        if isinstance(item, (bytes, bytearray)):
            return ImageReader(io.BytesIO(bytes(item)))
        p = Path(item)
        if p.exists():
            return ImageReader(str(p.resolve()))
        # try URL fetch if requests is available
        try:
            import requests

            r = requests.get(str(item), timeout=5)
            r.raise_for_status()
            return ImageReader(io.BytesIO(r.content))
        except Exception:
            raise ValueError(
                f"Cannot load image from {item!r}; provide bytes or a local file"
            )

    def mk_image_and_caption_pdf_page(
        image,
        caption,
        *,
        page_size=A4,
        image_fraction=0.75,
        horizontal_margin=0.5 * inch,
        top_margin=0.5 * inch,
        bottom_margin=0.5 * inch,
        gap=0.1 * inch,
        start_font=11,
        min_font=6,
        preserve_aspect=True,
        align="center",
    ):
        """Return PDF bytes for a single page showing image (top) and caption (bottom).

        Keyword-only layout parameters allow callers to control page size and
        margins without changing the implementation.

        Parameters (keyword-only):
        - page_size: tuple (width, height) for the page (default: A4)
        - image_fraction: fraction of page height reserved for the image (default 0.75)
        - horizontal_margin: left/right margin (default 0.5 inch)
        - top_margin: top margin (default 0.5 inch)
        - bottom_margin: bottom margin (default 0.5 inch)
        - gap: vertical gap between image and caption area
        - start_font, min_font: font sizes for auto-shrinking captions
        - preserve_aspect: passed to ReportLab's drawImage preserveAspectRatio
        - align: 'center'|'left'|'right' alignment for the image

        Uses ReportLab to render a single page with the image occupying the
        top portion of the page and the caption rendered in the area below it.
        """
        img = _load_image_for_reportlab(image)

        # Prepare canvas
        buf = io.BytesIO()
        w, h = page_size
        c = canvas.Canvas(buf, pagesize=page_size)

        # Image area: reserve top portion of page height for image
        img_area_h = h * float(image_fraction)
        img_area_w = w - 2 * float(horizontal_margin)  # horizontal margins
        # get image size
        try:
            iw, ih = img.getSize()
        except Exception:
            # fallback to drawing without size
            iw, ih = img._getSize()

        scale = min(img_area_w / iw, img_area_h / ih, float(1.0))
        draw_w = iw * scale
        draw_h = ih * scale
        # horizontal alignment
        if align == "left":
            x = horizontal_margin
        elif align == "right":
            x = w - horizontal_margin - draw_w
        else:
            x = (w - draw_w) / 2

        y = h - draw_h - float(top_margin)
        c.drawImage(img, x, y, draw_w, draw_h, preserveAspectRatio=preserve_aspect)

        # Caption area: bottom 25%
        # Convert caption to safe HTML-like text for Paragraph while preserving newlines.
        # Avoid full markdown -> HTML conversion because ReportLab's Paragraph supports
        # only a subset of tags and complex HTML (lists, <p>, etc.) can cause content to
        # not render. Instead, render plain text with <br/> for newlines.
        from xml.sax.saxutils import escape
        from pathlib import Path

        raw = caption or ""
        # turn lines into escaped lines joined by <br/>
        lines = raw.splitlines()
        escaped = [escape(line) for line in lines]
        caption_html = "<br/>".join(escaped) if escaped else ""

        styles = getSampleStyleSheet()
        base_style = styles["BodyText"]
        # start with a reasonable font size and shrink if needed
        frame_x = float(horizontal_margin)
        frame_y = float(bottom_margin)
        frame_w = w - 2 * float(horizontal_margin)
        frame_h = y - float(bottom_margin) - float(gap)
        if frame_h <= 0:
            # fallback: give a small caption area at bottom
            frame_h = inch * 1.0
            frame_y = float(bottom_margin)

        chosen_font = start_font
        para = None
        # Try decreasing font sizes until paragraph fits the frame height
        for fs in range(start_font, min_font - 1, -1):
            p_style = base_style.clone("caption")
            p_style.fontSize = fs
            p_style.leading = fs * 1.2
            p = Paragraph(caption_html, p_style)
            # para.wrap returns (width, height) that the para would occupy
            try:
                needed_w, needed_h = p.wrap(frame_w, frame_h)
            except Exception:
                # if wrap fails for any reason, accept this paragraph and proceed
                para = p
                chosen_font = fs
                break
            if needed_h <= frame_h:
                para = p
                chosen_font = fs
                break

        if para is None:
            # last resort: use the minimum font size paragraph even if it overflows
            p_style = base_style.clone("caption")
            p_style.fontSize = min_font
            p_style.leading = min_font * 1.2
            para = Paragraph(caption_html, p_style)

        frame = Frame(frame_x, frame_y, frame_w, frame_h, showBoundary=0)
        frame.addFromList([para], c)

        c.showPage()
        c.save()
        return buf.getvalue()

    for idx, item in enumerate(imgs):
        if caps is not None:
            mk_kwargs = dict(mk_page_kwargs or {})
            if image_fraction is not None:
                mk_kwargs["image_fraction"] = image_fraction
            if horizontal_margin is not None:
                mk_kwargs["horizontal_margin"] = horizontal_margin
            if align is not None:
                mk_kwargs["align"] = align

            pdf_bytes = mk_image_and_caption_pdf_page(item, caps[idx], **mk_kwargs)
        else:
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
