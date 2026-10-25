"""Month planning and refresh policy for the contribution history.

Pure and free of Home Assistant imports.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from .periods import previous_month

RECENT_MONTHS = 2
MONTHS_PER_REQUEST = 12
RECENT_MAX_AGE = timedelta(days=1)
OLD_MAX_AGE = timedelta(days=7)


@dataclass(frozen=True, slots=True, order=True)
class MonthKey:
    """A calendar month."""

    year: int
    month: int

    @property
    def label(self) -> str:
        """Return the ``YYYY-MM`` label used as storage key."""
        return f"{self.year:04d}-{self.month:02d}"

    @classmethod
    def parse(cls, label: str) -> MonthKey:
        """Parse a ``YYYY-MM`` label."""
        year, month = label.split("-")
        return cls(int(year), int(month))


@dataclass(frozen=True, slots=True)
class MonthStats:
    """Contribution totals of one month."""

    commits: int
    pull_requests: int
    issues: int
    reviews: int
    restricted: int


def months_back(today: date, years: int) -> list[MonthKey]:
    """Return the months from ``years`` ago up to and including today's month.

    The result is ordered oldest first and contains ``years * 12 + 1`` months.
    """
    keys = [MonthKey(today.year, today.month)]
    for _ in range(years * 12):
        keys.append(MonthKey(*previous_month(keys[-1].year, keys[-1].month)))
    return sorted(keys)


def needs_refresh(
    key: MonthKey, fetched_at: datetime | None, today: date, now: datetime
) -> bool:
    """Decide whether a stored month must be fetched again.

    Months never fetched, the current month and the last ``RECENT_MONTHS``
    months are refreshed daily; older months weekly, because backdated commits
    and newly linked e-mail addresses can still change them.
    """
    if fetched_at is None:
        return True
    recent = months_back(today, 0)[-1]
    cutoff = recent
    for _ in range(RECENT_MONTHS):
        cutoff = MonthKey(*previous_month(cutoff.year, cutoff.month))
    max_age = RECENT_MAX_AGE if key > cutoff else OLD_MAX_AGE
    return now - fetched_at >= max_age


def chunk_months(
    keys: list[MonthKey], size: int = MONTHS_PER_REQUEST
) -> list[list[MonthKey]]:
    """Split months into request-sized chunks, oldest first."""
    ordered = sorted(keys)
    return [ordered[i : i + size] for i in range(0, len(ordered), size)]
