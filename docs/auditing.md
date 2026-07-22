# Auditing dates written by the pre-0.3.0 admin

Before 0.3.0, `BSDateField` inherited Django's **Gregorian** admin date widget.
`django.contrib.admin` maps `models.DateField` to `AdminDateWidget` by walking
the field's MRO, and `BSDateField` subclasses `DateField` to inherit its lookups
— so it inherited the calendar popup and the "Today" button too.

Anything entered through them was a Gregorian date, and the field read it as
Bikram Sambat. Clicking "Today" on 22 July 2026 stored `2026-07-22` **BS**,
which is 1969-11-07 AD. That is a real BS date, so it passed validation and
raised nothing.

This page is for finding those rows. **If no data was ever entered through the
Django admin, you are not affected** — the trap was specific to that widget.

---

## The quick check

A Gregorian date from 2024–2028 typed into the field lands in a narrow AD
window. One query, no loop:

```python
import datetime

Invoice.objects.filter(
    issued_on__gte=datetime.date(1967, 4, 14),
    issued_on__lte=datetime.date(1972, 4, 12),
).count()
```

That covers the realistic case — someone entering a date near today. If it
returns zero and your admin only ever recorded current dates, you are done.

It does **not** cover a user who typed some other Gregorian year: a 1998
birthdate, a 2015 contract date. For that, use the general check.

---

## The general check

The signature of this bug is that the row's Bikram Sambat *digits*, read as a
Gregorian date, give a date a human would plausibly have typed.

```python
import datetime

def misread_as_bs(
    value,
    earliest=datetime.date(1950, 1, 1),
    latest=datetime.date(2050, 1, 1),
):
    """Return the Gregorian date a user probably meant, or None.

    `value` is the stored BSDate. If its digits form a real Gregorian date
    inside the plausible-entry window, the row is a candidate.
    """
    try:
        meant = datetime.date(value.year, value.month, value.day)
    except ValueError:
        # The digits are not a valid Gregorian date -- e.g. day 32, which
        # Bikram Sambat has and the Gregorian calendar does not. Nobody could
        # have typed it, so this row is definitively not affected.
        return None
    return meant if earliest <= meant < latest else None


suspects = []
for invoice in Invoice.objects.iterator(chunk_size=2000):
    meant = misread_as_bs(invoice.issued_on)
    if meant is not None:
        suspects.append((invoice.pk, invoice.issued_on, meant))

for pk, stored, meant in suspects:
    print(f"{pk}: stored {stored} ({stored.to_ad()}) -- user probably meant {meant}")
```

Narrow `earliest`/`latest` to the range of dates your users actually enter. A
field holding invoice dates might use 2015–2030; a birthdate field needs a much
wider window and will therefore flag more.

---

## How reliable is it?

**It flags candidates, not proof.** Two properties make it more useful than a
bare heuristic, and one limit is irreducible.

**Impossible dates are excluded outright.** Bikram Sambat months run 29–32 days.
A stored BS date of `2081-02-32` cannot be a mistyped Gregorian date, because no
Gregorian month has 32 days — the `ValueError` branch rules it out with
certainty, not probability. The same applies to 31 Ashadh landing on a 30-day
Gregorian month.

**False positives have a hard boundary.** A genuine row is flagged only if its BS
year falls inside your plausible-entry window. With the 1950–2050 default:

| Genuine BS year | Gregorian equivalent | Flagged? |
|---|---|---|
| 1975 | AD 1918-04-13 | yes — ambiguous |
| 2049 | AD 1992-04-13 | yes — ambiguous |
| **2050** | **AD 1993-04-13** | **no** |
| 2070 | AD 2013-04-14 | no |
| 2084 | AD 2027-04-14 | no |

So **only genuine dates before roughly April 1993 are ambiguous.** An application
whose data starts after that — most of them — gets zero false positives from the
default window. If your data is entirely modern, every flagged row is real.

**The irreducible limit:** a genuine record from AD 1969 with BS date 2026-07-22
is byte-identical to a row corrupted by someone clicking "Today" in July 2026.
Nothing in the field can separate them. If you have genuine data from that era,
disambiguate with a column the bug never touched.

---

## Disambiguating with a second column

If the model has an untouched timestamp — `auto_now_add`, an audit log, anything
the admin widget did not write — use it. A row *created* in 2026 whose date
claims to be from 1969 is almost certainly corrupted:

```python
for invoice in Invoice.objects.iterator(chunk_size=2000):
    meant = misread_as_bs(invoice.issued_on)
    if meant is None:
        continue
    created = invoice.created_at.date()          # a plain DateTimeField
    gap_years = abs((created - invoice.issued_on.to_ad()).days) / 365.25
    if gap_years > 20:
        print(f"{invoice.pk}: created {created}, date claims "
              f"{invoice.issued_on.to_ad()} -- meant {meant}?")
```

Note `created_at` must be an ordinary `DateTimeField`. A `BSDateField` with
`auto_now_add` was always populated in code, never through the widget, so it is
also trustworthy — but read it with `.to_ad()` for the comparison.

---

## Fixing a row

Take the stored value's digits as the Gregorian date the user meant, then
convert that properly:

```python
bs = invoice.issued_on                              # BSDate(2026, 7, 22)
meant = datetime.date(bs.year, bs.month, bs.day)    # date(2026, 7, 22)
invoice.issued_on = BSDate.from_ad(meant)           # BSDate(2083, 4, 6)
invoice.save(update_fields=["issued_on"])
```

Round-tripped and verified: a user who meant 2026-07-22 had 1969-11-07 stored,
and this recovers `BSDate(2083, 4, 6)` — the correct Bikram Sambat date for
22 July 2026.

**Review before writing.** Print the full candidate list, confirm the dates make
sense for each record, and fix in a transaction you can roll back. This corrects
data that already validated once; a wrong "correction" is as silent as the
original bug.

---

## After upgrading

0.3.0 swaps the Gregorian widget out, so no new rows can be written this way.
For a proper Bikram Sambat calendar in the admin, use the bundled picker:

```python
from django_bikram_sambat.django import BSDatePickerInput
```

See [Date picker](../README.md#date-picker).
