# Skill Opportunities for pdfdol

Notes on areas where a `.claude/skills` skill could accelerate future work.

## 1. Format Converter Authoring

**Trigger**: user asks to add support for a new file format (e.g. ".xyz to PDF").

**What the skill should know**:
- The converter registry API (`register_format_converter`, `get_format_converter`).
- Converter callable signature: `(source: str | bytes) -> bytes`.
- Where to add detection in `_resolve_src_kind` if a new `SrcKind` is warranted.
- How `key_and_value_to_pdf_bytes` delegates to the registry.
- Test patterns in `pdfdol/tests/test_tools.py`.

## 2. Store Wrapper Composition

**Trigger**: user asks to create a new dict-like view over files with custom value decoding.

**What the skill should know**:
- `dol.Files`, `dol.wrap_kvs`, `dol.Pipe`, `dol.KeyCodecs`, `dol.filt_iter`.
- How `PdfFilesReader` is built by chaining wrappers in `base.py`.
- `add_ipython_key_completions` for notebook UX.

## 3. PDF Pipeline Construction

**Trigger**: user asks to build a bytes -> something pipeline (e.g. PDF -> images, PDF -> structured data).

**What the skill should know**:
- `dol.Pipe` for composable left-to-right transformations.
- Existing pipeline components in `base.py` (bytes_to_pdf_reader_obj, pdf_reader_to_text_pages, etc.).
- The edge-graph idea in the `base.py` comments for meshed-style pipelines.

## 4. Calibre ebook-convert Recipes

**Trigger**: user asks about ebook-convert options, quality tuning, or Calibre setup.

**What the skill should know**:
- `find_ebook_convert()` detection logic (PATH, macOS app bundle, Windows paths).
- `ebook_convert_to_pdf()` temp-file workflow.
- Calibre CLI docs: https://manual.calibre-ebook.com/conversion.html
- Full list of supported input/output formats (see architecture.md).
