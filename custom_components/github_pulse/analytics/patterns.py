"""Activity patterns: busiest month, contribution streaks and weekday rhythm."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, timedelta


@dataclass(frozen=True, slots=True)
class BusiestMonth:
    """The month of a year with the most contributions."""

    month: int
    count: int


@dataclass(frozen=True, slots=True)
class Streaks:
    """Consecutive-day contribution streaks."""

    current: int
    longest: int


@dataclass(frozen=True, slots=True)
class WeekdayPattern:
    """Contributions per weekday (0 = Monday) and the strongest weekday."""

    most_productive: int
    totals: Mapping[int, int]


def busiest_month(
    monthly: Mapping[tuple[int, int], int], year: int
) -> BusiestMonth | None:
    """Return the busiest month of ``year``; the earliest wins a tie.

    ``monthly`` maps ``(year, month)`` to a contribution count. Returns
    ``None`` when the year has no activity.
    """
    in_year = {month: count for (y, month), count in monthly.items() if y == year}
    if not in_year or max(in_year.values()) == 0:
        return None
    best = max(in_year.values())
    return BusiestMonth(
        month=min(m for m, c in in_year.items() if c == best), count=best
    )


def streaks(daily: Mapping[date, int], today: date) -> Streaks:
    """Return the current and longest streak of days with contributions.

    The current streak is still alive while ``today`` has no contribution yet,
    as long as yesterday had one.
    """
    active = {day for day, count in daily.items() if count > 0}
    return Streaks(
        current=_current_streak(active, today), longest=_longest_streak(active)
    )


def _current_streak(active: set[date], today: date) -> int:
    cursor = today if today in active else today - timedelta(days=1)
    length = 0
    while cursor in active:
        length += 1
        cursor -= timedelta(days=1)
    return length


def _longest_streak(active: set[date]) -> int:
    longest = 0
    for day in active:
        if day - timedelta(days=1) in active:
            continue  # not the start of a run
        length = 1
        while day + timedelta(days=length) in active:
            length += 1
        longest = max(longest, length)
    return longest


def weekday_pattern(daily: Mapping[date, int]) -> WeekdayPattern | None:
    """Return contributions per weekday; the earliest weekday wins a tie."""
    totals = dict.fromkeys(range(7), 0)
    for day, count in daily.items():
        totals[day.weekday()] += count
    best = max(totals.values())
    if best == 0:
        return None
    return WeekdayPattern(
        most_productive=min(d for d, total in totals.items() if total == best),
        totals=totals,
    )
