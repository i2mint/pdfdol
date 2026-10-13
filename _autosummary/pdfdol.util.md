# pdfdol.util

Utils for pdfdol

### Functions

| [`add_affix`](#pdfdol.util.add_affix)(string, \*[, prefix, suffix])       | Add a suffix and/or prefix to a filepath.                        |
|------------------------------------------------------------------------------------------------|------------------------------------------------------------------|
| [`affix_source_if_target_not_given`](#pdfdol.util.affix_source_if_target_not_given)(src[, ...])  | If target is None, affix the source filepath and return it.      |
| [`ensure_pages`](#pdfdol.util.ensure_pages)(pages)                           | Ensure that pages are given as a sequence of PageObject objects. |
| [`is_page_empty`](#pdfdol.util.is_page_empty)(page[, min_n_characters])       | Check if a PDF page is empty.                                    |
| [`remove_empty_pages`](#pdfdol.util.remove_empty_pages)(pages[, output_path, ...]) | Remove empty pages from a PDF file.                              |

### pdfdol.util.add_affix(string, , prefix=None, suffix=None)

Add a suffix and/or prefix to a filepath.

```pycon
>>> add_affix('file.pdf', prefix='new_', suffix='_for_you')
'new_file_for_you.pdf'
```

### pdfdol.util.affix_source_if_target_not_given(src, target=None, , prefix=None, suffix=None)

If target is None, affix the source filepath and return it.

```pycon
>>> affix_source_if_target_not_given(
...     'file.pdf', 'target_exists', prefix='new_', suffix='_for_you'
... )
'target_exists'
>>> affix_source_if_target_not_given(
...     'file.pdf', None, prefix='new_', suffix='_for_you'
... )
'new_file_for_you.pdf'
```

### pdfdol.util.ensure_pages(pages)

Ensure that pages are given as a sequence of PageObject objects.

* **Return type:**
  [`Iterable`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Iterable)[`PageObject`]

### pdfdol.util.is_page_empty(page, min_n_characters=1)

Check if a PDF page is empty.

* **Return type:**
  [`bool`](https://docs.python.org/3/builtins/functions.html#bool)

### pdfdol.util.remove_empty_pages(pages, output_path=None, , page_is_empty=None, suppress_warnings=True)

Remove empty pages from a PDF file.
