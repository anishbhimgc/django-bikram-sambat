"""Admin integration: a Bikram Sambat aware ``list_filter``.

Why this module exists
----------------------
``django.contrib.admin`` resolves a field's list filter by walking the field's
MRO::

    FieldListFilter.register(lambda f: isinstance(f, models.DateField),
                             DateFieldListFilter)

:class:`~django_bikram.django.fields.BSDateField` subclasses
:class:`~django.db.models.DateField` to inherit every date lookup, so it matches
that test and gets Django's **Gregorian** date filter. The buckets it produces
are correct ranges over the stored AD value and are labelled with no calendar at
all -- "This month", "This year" -- so a Nepali admin user reads them as Bikram
Sambat periods and gets Gregorian ones:

===============  =========================  ==============================
Filter           What Django selects        What the label implies
===============  =========================  ==============================
"This month"     AD 2026-07-01 .. 08-01     the current **BS** month
                 = BS 2083-03-17 .. 04-16   2083-04-01 .. 2083-05-01
"This year"      AD 2026-01-01 .. 2027      the current **BS** year
                 = BS 2082-09-17 .. 2083    2083-01-01 .. 2084-01-01
===============  =========================  ==============================

"This month" spans two BS months *and* two fiscal years. Nothing on screen
reveals it. This is the same trap as DRF's ``ModelSerializer`` mapping and the
admin's Gregorian date widget, arriving by the same route.

:class:`BSDateFieldListFilter` replaces those buckets with real Bikram Sambat
ones, plus the fiscal year that Django has no concept of. Each is still a
half-open range on the indexed column, so the filter costs one index range scan
exactly as Django's does.

Using it
--------
Per field, which is the recommended form::

    from django_bikram.django.admin import BSDateFieldListFilter

    class InvoiceAdmin(admin.ModelAdmin):
        list_filter = [("issued_on", BSDateFieldListFilter)]

Or once, for every :class:`BSDateField` in the project::

    class MyAppConfig(AppConfig):
        def ready(self):
            from django_bikram.django.admin import register_list_filter
            register_list_filter()

As with :func:`django_bikram.django.drf.register_serializer_field`, the global
form is not applied on import: it mutates a third-party registry, and doing that
as an import side effect makes behaviour depend on module import order.

``date_hierarchy`` is **not** covered
-------------------------------------
``ModelAdmin.date_hierarchy`` is rendered by a Django template tag that builds
``__year`` / ``__month`` / ``__day`` lookups directly, with no registry to hook.
Those lookups are inherited from ``DateField`` and operate on the stored
Gregorian value, so a ``date_hierarchy`` on a ``BSDateField`` offers **AD**
drill-downs -- a record in 1 Baishakh 2081 appears under "2024". There is no
correct fix short of reimplementing the tag; prefer this filter instead.
"""

from __future__ import annotations

import datetime
from typing import Any

from django.contrib.admin.filters import DateFieldListFilter, FieldListFilter
from django.contrib.admin.options import IncorrectLookupParameters
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from ..date import BSDate
from ..exceptions import InvalidBSDate
from ..fiscal import fiscal_year_bounds
from .fields import BSDateField
from .lookups import bs_month_bounds, bs_year_bounds

__all__ = ["BSDateFieldListFilter", "register_list_filter"]


class BSDateFieldListFilter(DateFieldListFilter):
    """A ``list_filter`` whose periods are Bikram Sambat, not Gregorian.

    Offers *Any date*, *Today*, *Past 7 days*, *This month* (BS), *This year*
    (BS) and *This fiscal year*, plus Django's *No date* / *Has date* when the
    field is nullable. Every bucket is a half-open range on the stored column,
    so each is a single index range scan.

    Example:
        >>> class InvoiceAdmin(admin.ModelAdmin):
        ...     list_filter = [("issued_on", BSDateFieldListFilter)]
        ...     # doctest: +SKIP
    """

    def __init__(
        self,
        field: Any,
        request: Any,
        params: Any,
        model: Any,
        model_admin: Any,
        field_path: str,
    ) -> None:
        """Build the Bikram Sambat buckets, then hand off to Django.

        Args:
            field: The model field being filtered.
            request: The current request.
            params: The changelist's query parameters.
            model: The model class.
            model_admin: The ``ModelAdmin`` instance.
            field_path: The field's lookup path.
        """
        # Deliberately skips DateFieldListFilter.__init__, whose whole body is
        # the Gregorian bucket construction this class exists to replace. Its
        # choices(), expected_parameters() and get_facet_counts() all read
        # self.links, so replacing that attribute is enough to reuse them.
        self.field_generic = f"{field_path}__"
        # Django <5.0 hands `params` values as plain strings; 5.0+ as lists of
        # them. Normalise, rather than copying either version's idiom.
        self.date_params = {
            k: (v[-1] if isinstance(v, (list, tuple)) else v)
            for k, v in params.items()
            if k.startswith(self.field_generic)
        }
        self.lookup_kwarg_since = f"{field_path}__gte"
        self.lookup_kwarg_until = f"{field_path}__lt"

        self.links: tuple[tuple[Any, dict[str, Any]], ...] = ((_("Any date"), {}),)
        self.links += self._bs_links(self._today())

        if field.null:
            self.lookup_kwarg_isnull = f"{field_path}__isnull"
            self.links += (
                (_("No date"), {self.field_generic + "isnull": True}),
                (_("Has date"), {self.field_generic + "isnull": False}),
            )

        # Skip DateFieldListFilter in the MRO; go straight to FieldListFilter.
        FieldListFilter.__init__(
            self, field, request, params, model, model_admin, field_path
        )

    def queryset(self, request: Any, queryset: Any) -> Any:
        """Apply the selected bucket, reading its bounds as **Gregorian**.

        This is what makes the filter actually work, and it is not optional.

        A list filter round-trips its bounds through the query string, so by the
        time they come back they are ISO strings -- ``issued_on__gte=2026-07-17``.
        :meth:`BSDateField.to_python` reads a string as *Bikram Sambat* (that is
        the documented contract: a string in that field's context is the BS value
        a user typed), so the bound is re-read as 2026-07-17 **BS** = 1969 AD and
        the filter matches nothing at all.

        That defeats Django's own ``DateFieldListFilter`` on this field too, on
        every supported version: every bucket, including "Today" on a row saved
        today, returns zero rows. The bounds this filter puts in the URL are
        Gregorian, so they are parsed back as Gregorian here.

        Args:
            request: The current request.
            queryset: The changelist queryset.

        Returns:
            The filtered queryset.

        Raises:
            IncorrectLookupParameters: If a bound in the URL is not a valid ISO
                date -- a hand-edited or stale query string.
        """
        try:
            lookups = {
                key: self._as_gregorian(key, value)
                for key, value in self.used_parameters.items()
            }
            return queryset.filter(**lookups)
        except (ValueError, ValidationError) as exc:
            raise IncorrectLookupParameters(exc) from exc

    @staticmethod
    def _as_gregorian(key: str, value: Any) -> Any:
        """Coerce one URL parameter to the type the lookup needs.

        Args:
            key: The lookup key, e.g. ``"issued_on__gte"``.
            value: The raw value from the query string.

        Returns:
            A :class:`datetime.date` for the range bounds, so they are never
            re-read as Bikram Sambat; anything else (``__isnull``) untouched.

        Raises:
            ValueError: If a bound is not an ISO date.
        """
        if key.endswith("__isnull"):
            return value
        if isinstance(value, (list, tuple)):
            value = value[-1]
        if isinstance(value, str):
            return datetime.date.fromisoformat(value)
        return value

    def choices(self, changelist: Any) -> Any:
        """Yield the filter's choices, with a version-independent selected state.

        Django <5.0 compares ``self.date_params`` (strings, from the query
        string) against the raw ``links`` params; 5.0+ stringifies both first.
        This filter's links hold :class:`datetime.date` objects -- they have to,
        so :meth:`queryset` never sees an ambiguous string -- which means the
        older comparison never matches and no bucket ever highlights. Comparing
        stringified values works on every version.

        Args:
            changelist: The admin changelist.

        Yields:
            One choice dict per bucket.
        """
        # add_facets and get_facet_queryset are Django 5.0+; degrade quietly.
        add_facets = getattr(changelist, "add_facets", False)
        facet_counts = self.get_facet_queryset(changelist) if add_facets else None
        for index, (title, param_dict) in enumerate(self.links):
            param_dict_str = {key: str(value) for key, value in param_dict.items()}
            if add_facets and facet_counts is not None:
                title = f"{title} ({facet_counts[f'{index}__c']})"
            yield {
                "selected": self.date_params == param_dict_str,
                "query_string": changelist.get_query_string(
                    param_dict_str, [self.field_generic]
                ),
                "display": title,
            }

    def _today(self) -> BSDate | None:
        """Return today as a :class:`BSDate`, or ``None`` if unrepresentable.

        Uses the project's local date, matching Django's own "Today" and
        :meth:`BSDateField.pre_save` -- a project that sets ``TIME_ZONE`` is
        stating which day it means.

        Returns:
            Today in Bikram Sambat, or ``None`` once the calendar table has
            lapsed. Returning ``None`` rather than raising keeps the changelist
            usable: an admin that cannot render is worse than one missing some
            filter buckets.
        """
        now = timezone.now()
        if timezone.is_aware(now):
            now = timezone.localtime(now)
        try:
            return BSDate.from_ad(now.date())
        except InvalidBSDate:
            return None

    def _bs_links(self, today: BSDate | None) -> tuple[tuple[Any, dict[str, Any]], ...]:
        """Build the date buckets that the calendar table can support.

        A bucket whose range falls outside the verified calendar is omitted
        rather than approximated -- near the end of the table the fiscal year is
        the first to go, since it reaches into the following BS year.

        Args:
            today: Today in Bikram Sambat, or ``None``.

        Returns:
            The ``(title, params)`` pairs to offer.
        """
        if today is None:
            return ()

        ad_today = today.to_ad()
        links: list[tuple[Any, dict[str, Any]]] = []

        def add(title: Any, bounds: tuple[datetime.date, datetime.date]) -> None:
            """Append a bucket built from a half-open ``(start, end)`` pair."""
            links.append(
                (
                    title,
                    {
                        self.lookup_kwarg_since: bounds[0],
                        self.lookup_kwarg_until: bounds[1],
                    },
                )
            )

        tomorrow = ad_today + datetime.timedelta(days=1)
        add(_("Today"), (ad_today, tomorrow))
        add(_("Past 7 days"), (ad_today - datetime.timedelta(days=7), tomorrow))

        for title, builder in (
            (_("This month"), lambda: bs_month_bounds(today.year, today.month)),
            (_("This year"), lambda: bs_year_bounds(today.year)),
            (_("This fiscal year"), lambda: fiscal_year_bounds(today.fiscal_year)),
        ):
            try:
                add(title, builder())
            except InvalidBSDate:
                # Past the table's edge. Drop the bucket; never guess at it.
                continue

        return tuple(links)


def register_list_filter(take_priority: bool = True) -> None:
    """Make :class:`BSDateFieldListFilter` the default for every ``BSDateField``.

    Without this, ``list_filter = ["issued_on"]`` resolves through Django's
    ``isinstance(f, models.DateField)`` test to the Gregorian
    ``DateFieldListFilter`` -- see this module's docstring for what that shows
    the user.

    Call it once at startup, from an ``AppConfig.ready()``::

        class MyAppConfig(AppConfig):
            def ready(self):
                from django_bikram.django.admin import register_list_filter
                register_list_filter()

    It is not called on import: it mutates a third-party registry, and doing
    that as an import side effect makes behaviour depend on import order.
    Declaring the filter per field -- ``list_filter = [("issued_on",
    BSDateFieldListFilter)]`` -- needs no registration at all.

    Args:
        take_priority: Insert ahead of Django's own registrations, which is
            required for this to have any effect: Django's ``DateField`` test
            is registered first and the first match wins. Pass ``False`` only
            if you have your own registration ordering to preserve.
    """
    FieldListFilter.register(
        lambda f: isinstance(f, BSDateField),
        BSDateFieldListFilter,
        take_priority=take_priority,
    )
