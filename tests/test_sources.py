"""Tests for the optional bikram-sambat provisional data adapter.

These require the optional ``bikram-sambat`` package, which the ``[dev]`` extra
installs. Activation mutates process-global calendar state, so that path runs in
a clean subprocess.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap

import pytest

from django_bikram_sambat.calendar_data import MONTHS_IN_YEAR, VERIFIED_MAX_BS_YEAR
from django_bikram_sambat.predict import predicted_month_days
from django_bikram_sambat.sources import bikram_sambat_table


def test_table_covers_the_requested_span() -> None:
    """The table is contiguous from just past the verified range."""
    table = bikram_sambat_table(through_year=2100)
    assert min(table) == VERIFIED_MAX_BS_YEAR + 1
    assert max(table) == 2100


def test_every_year_is_structurally_valid() -> None:
    """Each row has twelve months totalling 365 or 366 days."""
    for year, lengths in bikram_sambat_table(through_year=2150).items():
        assert len(lengths) == MONTHS_IN_YEAR, year
        assert sum(lengths) in (365, 366), (year, sum(lengths))


def test_extraction_matches_the_source_exactly() -> None:
    """What we return is exactly what bikram-sambat holds -- no transformation."""
    from bikram_sambat.calendar import YEAR_MONTH_DAYS_BS

    table = bikram_sambat_table(through_year=2090)
    for year, lengths in table.items():
        assert lengths == tuple(int(n) for n in YEAR_MONTH_DAYS_BS[year])


def test_before_the_range_is_rejected() -> None:
    """Asking for a table that does not extend the range is an error."""
    with pytest.raises(ValueError, match="not past the verified range"):
        bikram_sambat_table(through_year=VERIFIED_MAX_BS_YEAR)


def test_it_is_a_genuinely_independent_guess() -> None:
    """bikram-sambat and the built-in predictor disagree past the verified range.

    This is the whole point of offering both: they are two independent
    unverified sources, and neither is authoritative. If they ever fully agreed,
    that agreement would itself be worth promoting to verified.
    """
    disagreements = sum(
        1
        for year, lengths in bikram_sambat_table(through_year=2100).items()
        if lengths != predicted_month_days(year)
    )
    assert disagreements > 0


def _run(script: str) -> str:
    """Run a snippet in a clean subprocess and return stdout."""
    result = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(script)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


def test_installs_as_an_alternative_provisional_source() -> None:
    """The table feeds install_provisional() and its dates are flagged."""
    out = _run(
        """
        import warnings
        import django_bikram_sambat as b
        from django_bikram_sambat import BSDate, ProvisionalDateWarning
        from django_bikram_sambat.calendar_data import install_provisional
        from django_bikram_sambat.sources import bikram_sambat_table
        install_provisional(bikram_sambat_table(through_year=2100))
        assert b.MAX_BS_YEAR == 2100, b.MAX_BS_YEAR
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            d = BSDate(2090, 1, 1)
            ad = d.to_ad()
        assert d.is_verified is False
        assert BSDate.from_ad(ad) == d
        assert any(issubclass(w.category, ProvisionalDateWarning) for w in caught)
        print("ok")
        """
    )
    assert out.strip() == "ok"
