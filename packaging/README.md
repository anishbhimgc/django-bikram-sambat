# packaging/

Sources that are published to PyPI but are not part of the library.

## `django-bikram-shim/`

The final release of the old **`django-bikram`** distribution (0.4.0). It has no
code of its own: it depends on `django-bikram-sambat`, re-exports it, aliases the
submodules so `from django_bikram.django import BSDateField` still resolves, and
raises a `DeprecationWarning` on import.

It exists so that anyone who installed the old name keeps working after the
rename. It is not built by CI and receives no further releases.

Build and publish manually:

```bash
cd packaging/django-bikram-shim
python -m build
twine check --strict dist/*
twine upload dist/*
```
