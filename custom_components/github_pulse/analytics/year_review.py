"""A summary of one calendar year, free of Home Assistant imports."""

from __future__ import annotations

from calendar import month_name
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date

from .history import MonthKey, MonthStats
from .languages import LanguageMonth, combine, shares
from .patterns import BusiestMonth, busiest_month, streaks


@dataclass(frozen=True, slots=True)
class YearInReview:
    """The headline figures of a year. Missing data stays ``None``."""

    year: int
    contributions: int
    commits: int
    pull_requests: int
    reviews: int
    issues: int
    active_months: int
    busiest_month: BusiestMonth | None
    top_language: str | None
    longest_streak: int | None


def year_in_review(
    year: int,
    months: Mapping[MonthKey, MonthStats],
    languages: Mapping[MonthKey, LanguageMonth],
    daily: Mapping[date, int],
    *,
    include_restricted: bool,
    by_commits: bool,
) -> YearInReview:
    """Summarise ``year`` from the stored monthly, language and daily data.

    The daily calendar only reaches back a year, so the longest streak is
    ``None`` when it holds no days of ``year``. A year without data gives zero
    totals and no busiest month or language.
    """
    in_year = {key: stats for key, stats in months.items() if key.year == year}
    totals = {
        (key.year, key.month): stats.total(include_restricted=include_restricted)
        for key, stats in in_year.items()
    }
    ranking = shares(
        combine(m for key, m in languages.items() if key.year == year),
        by_commits=by_commits,
    )
    days = {day: n for day, n in daily.items() if day.year == year}
    return YearInReview(
        year=year,
        contributions=sum(totals.values()),
        commits=sum(s.commits for s in in_year.values()),
        pull_requests=sum(s.pull_requests for s in in_year.values()),
        reviews=sum(s.reviews for s in in_year.values()),
        issues=sum(s.issues for s in in_year.values()),
        active_months=sum(1 for total in totals.values() if total > 0),
        busiest_month=busiest_month(totals, year),
        top_language=next(iter(ranking), None),
        longest_streak=streaks(days, date(year, 12, 31)).longest if days else None,
    )


def summary(review: YearInReview) -> str:
    """Return a one-line description of the year."""
    if review.contributions == 0:
        return f"{review.year}: no contributions recorded"
    parts = [f"{review.contributions:,} contributions"]
    if review.busiest_month is not None:
        parts.append(f"busiest in {month_name[review.busiest_month.month]}")
    if review.top_language is not None:
        parts.append(f"mostly {review.top_language}")
    if review.longest_streak:
        parts.append(f"longest streak {review.longest_streak} days")
    return f"{review.year}: " + ", ".join(parts)
