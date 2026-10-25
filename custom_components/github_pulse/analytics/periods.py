"""Period math for like-for-like comparisons.

Everything here is pure and free of Home Assistant imports. Callers pass the
current date in the *contribution time zone* (GitHub buckets days in Pacific
Time unless the profile says otherwise), so a time-zone change never touches
the maths.
"""

from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo


@dataclass(frozen=True, slots=True)
class DateRange:
    """An inclusive range of calendar days."""

    start: date
    end: date

    def __post_init__(self) -> None:
        """Reject ranges whose end lies before their start."""
        if self.end < self.start:
            msg = f"range end {self.end} is before its start {self.start}"
            raise ValueError(msg)

    @property
    def days(self) -> int:
        """Return the number of days in the range, both ends included."""
        return (self.end - self.start).days + 1


def month_range(year: int, month: int) -> DateRange:
    """Return the whole calendar month."""
    return DateRange(
        date(year, month, 1), date(year, month, monthrange(year, month)[1])
    )


def previous_month(year: int, month: int) -> tuple[int, int]:
    """Return the ``(year, month)`` before the given one."""
    return (year - 1, 12) if month == 1 else (year, month - 1)


def month_to_date(today: date) -> DateRange:
    """Return the first of the month up to and including ``today``."""
    return DateRange(today.replace(day=1), today)


def _first_days_of(year: int, month: int, elapsed_days: int) -> DateRange:
    """Return the first ``elapsed_days`` of a month, clamped to its length."""
    length = monthrange(year, month)[1]
    return DateRange(date(year, month, 1), date(year, month, min(elapsed_days, length)))


def like_for_like_previous_month(today: date) -> DateRange:
    """Return the same number of days at the start of the previous month.

    On the 10th, this is the 1st to the 10th of last month, so a partial month
    is never compared with a full one. A shorter previous month is clamped.
    """
    year, month = previous_month(today.year, today.month)
    return _first_days_of(year, month, today.day)


def like_for_like_previous_year(today: date) -> DateRange:
    """Return the same number of days at the start of the same month last year."""
    return _first_days_of(today.year - 1, today.month, today.day)


def percent_change(current: int | float, previous: int | float) -> float | None:
    """Return the percentage change, or ``None`` when the baseline is zero."""
    if previous == 0:
        return None
    return (current - previous) / previous * 100


def to_utc_window(rng: DateRange, zone: ZoneInfo) -> tuple[datetime, datetime]:
    """Return the UTC instants spanning the range's days in the given zone.

    The window runs from the first instant of the start day to the last second
    of the end day, both in ``zone``.
    """
    start = datetime.combine(rng.start, time.min, tzinfo=zone)
    end = datetime.combine(rng.end, time(23, 59, 59), tzinfo=zone)
    return start.astimezone(UTC), end.astimezone(UTC)
