"""Compatibility shim: this project is now ``django-bikram-sambat``.

Importing ``django_bikram`` re-exports :mod:`django_bikram_sambat` unchanged, so
existing code keeps working. Nothing else is maintained here -- fixes and new
features land in the new package only.

Migrate with a find-and-replace::

    pip uninstall django-bikram
    pip install django-bikram-sambat

    from django_bikram_sambat import BSDate     # was: django_bikram
"""

from __future__ import annotations

import sys
import warnings

import django_bikram_sambat as _pkg
from django_bikram_sambat import *  # noqa: F403

__version__ = "0.4.0"
__all__ = list(_pkg.__all__)

warnings.warn(
    "django-bikram has been renamed to django-bikram-sambat. Import "
    "'django_bikram_sambat' instead of 'django_bikram'; this shim will not "
    "receive further updates.",
    DeprecationWarning,
    stacklevel=2,
)

# Alias the submodules too, so `from django_bikram.django import BSDateField`
# and `import django_bikram.fiscal` keep resolving.
for _name in (
    "calendar_data", "convert", "date", "exceptions", "fiscal", "formatting",
    "predict", "sources", "apps", "django",
):
    try:
        _mod = __import__(f"django_bikram_sambat.{_name}", fromlist=["_"])
    except ImportError:  # optional integrations (django, drf) may be absent
        continue
    sys.modules[f"django_bikram.{_name}"] = _mod
