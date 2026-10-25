"""Variable helpers offered to user-written GraphQL queries.

A query can declare any of these as ``$name`` and receives a current value on
every run, so ranges like "this month" never go stale. Pure and free of Home
Assistant imports.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo

from .periods import month_range, to_utc_window

HELPER_NAMES = frozenset(
    {"start_of_month", "end_of_month", "start_of_year", "one_year_ago", "owner"}
)


def query_variables(today: date, owner: str, zone: ZoneInfo) -> dict[str, str]:
    """Return every helper value for ``today`` in the contribution time zone.

    Timestamps are ISO 8601 in UTC, ready for GitHub ``DateTime`` variables.
    """
    month_start, month_end = to_utc_window(month_range(today.year, today.month), zone)
    year_start = datetime.combine(date(today.year, 1, 1), time.min, tzinfo=zone)
    year_ago = _same_day_last_year(today)
    return {
        "owner": owner,
        "start_of_month": _iso(month_start),
        "end_of_month": _iso(month_end),
        "start_of_year": _iso(year_start.astimezone(UTC)),
        "one_year_ago": _iso(
            datetime.combine(year_ago, time.min, tzinfo=zone).astimezone(UTC)
        ),
    }


def _same_day_last_year(today: date) -> date:
    """Return ``today`` one year earlier, mapping 29 February to 28 February."""
    try:
        return today.replace(year=today.year - 1)
    except ValueError:
        return today.replace(year=today.year - 1, day=28)


def _iso(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")
