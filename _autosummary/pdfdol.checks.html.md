# pdfdol.checks

Checks that verify a PDF, rather than looking at a few of its pages.

`text_overlaps` finds text lines whose boxes overlap, the signature of a broken
pagination (a block drawn on top of another). It needs PyMuPDF, which is part of the
`chromium` extra of pdfdol.

### Functions

| [`text_overlaps`](#pdfdol.checks.text_overlaps)(pdf, \*[, min_frac, snippet_len])   | Pages (1-based) with text lines that overlap, and the pairs of overlapping lines.   |
|----------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------|

### pdfdol.checks.text_overlaps(pdf, , min_frac=0.3, snippet_len=40)

Pages (1-based) with text lines that overlap, and the pairs of overlapping lines.

Two lines overlap when the area they share is at least `min_frac` of the
smaller line’s area. An empty dict means no overlapping text.

* **Parameters:**
  * **pdf** – path, bytes, or an open PyMuPDF document.
  * **min_frac** ([`float`](https://docs.python.org/3/builtins/functions.html#float)) – overlap threshold, as a fraction of the smaller line box.
  * **snippet_len** ([`int`](https://docs.python.org/3/builtins/functions.html#int)) – how many characters of each line to report.
* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`int`](https://docs.python.org/3/builtins/functions.html#int), [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]]]

```pycon
>>> import io
>>> from reportlab.pdfgen import canvas
>>> def make(y2):
...     buf = io.BytesIO(); c = canvas.Canvas(buf)
...     c.drawString(72, 700, "first line of text"); c.drawString(72, y2, "second line of text")
...     c.save(); return buf.getvalue()
>>> text_overlaps(make(100))
{}
>>> text_overlaps(make(699))
{1: [('first line of text', 'second line of text')]}
```
