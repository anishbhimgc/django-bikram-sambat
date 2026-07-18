"""Optional external data sources for the provisional calendar range.

An **alternative** to the astronomical predictor in :mod:`django_bikram.predict`
for years past the verified range.

`bikram-sambat <https://pypi.org/project/bikram-sambat/>`_ (MIT) is a separately
maintained Nepali date library whose table covers 1901-2199 BS. Its 1975-2083
rows match this package's verified table exactly; **past 2083 they are that
project's own computed values** -- a single, unverified source. It is no more
authoritative than the built-in predictor: the two disagree on every year past
2083, and neither is the official Panchanga. This adapter exists only so you can
*choose* which best-guess to install; both produce tables you feed to
:func:`django_bikram.calendar_data.install_provisional`.

Requires the optional dependency::

    pip install "django-bikram[bikram-sambat]"

Nothing here is imported by default, so the dependency stays opt-in.
"""

from __future__ import annotations

from .calendar_data import MONTHS_IN_YEAR, VERIFIED_MAX_BS_YEAR

__all__ = ["bikram_sambat_table"]


def bikram_sambat_table(
    through_year: int = VERIFIED_MAX_BS_YEAR + 100,
) -> dict[int, tuple[int, ...]]:
    """Return `bikram-sambat`'s month lengths for years past the verified range.

    The result is shaped like
    :data:`~django_bikram.calendar_data.VERIFIED_BS_MONTH_DAYS` and covers
    ``VERIFIED_MAX_BS_YEAR + 1`` through ``through_year``, ready to hand to
    :func:`~django_bikram.calendar_data.install_provisional`.

    **This is unverified, single-source data** (see the module docstring). Treat
    it exactly like a prediction: fine for planning and display, never for a date
    where a one-day error matters. Installed years are flagged the same way the
    predictor's are -- ``is_verified`` is ``False`` and use raises
    :class:`~django_bikram.exceptions.ProvisionalDateWarning`.

    Args:
        through_year: The last BS year to include. Defaults to a century past
            the verified range.

    Returns:
        A mapping of BS year to twelve month lengths, contiguous from
        ``VERIFIED_MAX_BS_YEAR + 1``.

    Raises:
        ImportError: If the optional ``bikram-sambat`` package is not installed.
        ValueError: If ``through_year`` does not extend the range, or if
            ``bikram-sambat`` lacks a requested year or returns a malformed one.

    Example:
        >>> from django_bikram.calendar_data import install_provisional
        >>> install_provisional(bikram_sambat_table(2150))  # doctest: +SKIP
    """
    first = VERIFIED_MAX_BS_YEAR + 1
    if through_year < first:
        raise ValueError(
            f"through_year {through_year} is not past the verified range; the "
            f"provisional table starts at {first} BS"
        )
    try:
        from bikram_sambat.calendar import YEAR_MONTH_DAYS_BS
    except ImportError as exc:  # pragma: no cover - depends on the environment
        raise ImportError(
            "bikram_sambat_table() needs the optional 'bikram-sambat' package. "
            'Install it with: pip install "django-bikram[bikram-sambat]"'
        ) from exc

    table: dict[int, tuple[int, ...]] = {}
    for year in range(first, through_year + 1):
        if year not in YEAR_MONTH_DAYS_BS:
            raise ValueError(
                f"bikram-sambat has no data for BS {year} (its range ends "
                f"earlier); lower through_year"
            )
        row = tuple(int(n) for n in YEAR_MONTH_DAYS_BS[year])
        if len(row) != MONTHS_IN_YEAR or sum(row) not in (365, 366):
            raise ValueError(
                f"bikram-sambat returned a malformed year for BS {year}: {row}"
            )
        table[year] = row
    return table
