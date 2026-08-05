# backend/app/services/benchmark_period.py
"""Shared period defaulting for benchmark endpoints.

Both the admin route and the share-link route must resolve "no dates given" the
same way, or an operator and their client would be shown different periods for
the same benchmark and neither would know.

The default is the last fully closed calendar month. Never the current month:
a partial period compared against complete ones reads as a collapse in
performance when it is only a collapse in elapsed time.
"""
from datetime import date, timedelta


def previous_month_bounds(today: date) -> tuple[date, date]:
    first_of_this_month = today.replace(day=1)
    period_end = first_of_this_month - timedelta(days=1)
    return period_end.replace(day=1), period_end


def default_benchmark_period(
    period_start: date | None, period_end: date | None, today: date | None = None
) -> tuple[date, date]:
    """Resolve an optional period into a concrete one.

    Both bounds must be supplied together; a half-specified period falls back
    to the default rather than pairing a caller's date with a computed one,
    which would silently produce a window nobody asked for.
    """
    if period_start is not None and period_end is not None:
        return period_start, period_end
    return previous_month_bounds(today or date.today())
