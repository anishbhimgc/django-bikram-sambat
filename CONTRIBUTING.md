# Contributing to django-bikram

Thanks for helping. The bar here is high on purpose: this is a calendar library,
and a wrong month length is a silent, hard-to-notice bug.

## Development setup

```bash
git clone https://github.com/anishbhimgc/django-bikram
cd django-bikram
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

## The checks CI runs (run them before you push)

```bash
pytest                    # the full suite
ruff check django_bikram/ # style + lint
mypy django_bikram/       # strict typing
```

CI additionally runs the test suite across Python 3.10–3.13 and Django 4.2 / 5.1
/ 5.2, verifies the docstring examples, and validates the built package metadata.

## Touching the calendar data

`django_bikram/calendar_data.py` is the correctness core.

- **Verified years** (`VERIFIED_BS_MONTH_DAYS`) may only be added when a year is
  corroborated by **at least two independent published sources**, and must pass
  the invariants in `tests/test_calendar_data.py` (twelve months, 365/366 days,
  no filler tail).
- **Do not** promote predicted (provisional) data into the verified table. The
  predictor in `django_bikram/predict.py` is ~87% accurate per month (see its
  `validate()`); that is a planning aid, never a source of verified dates.

## Releasing (maintainers)

Publishing uses **PyPI Trusted Publishing** — no tokens are stored.

One-time PyPI setup:

1. On https://pypi.org, register a *pending publisher* under the project
   (or the account): PyPI → *Your projects* → *Publishing* → add a GitHub
   publisher with owner `anishbhimgc`, repo `django-bikram`, workflow
   `publish.yml`, environment `pypi`.

Each release:

1. Bump `version` in `pyproject.toml` and move the `CHANGELOG.md` entries from
   *Unreleased* into a dated version section.
2. Commit, tag (`git tag v0.1.0 && git push --tags`).
3. Create a GitHub Release for that tag. The `publish.yml` workflow builds,
   checks, and uploads to PyPI automatically.
