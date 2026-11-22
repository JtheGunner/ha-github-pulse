"""Summaries of the GitHub traffic API (views, clones, referrers, paths).

GitHub only reports the last 14 days. Pure and free of Home Assistant imports.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from .periods import percent_change

TOP_LIMIT = 5
RECENT_DAYS = 7
WINDOW_DAYS = 14


@dataclass(frozen=True, slots=True)
class TrafficTotals:
    """Total and unique counts over the reported window."""

    count: int
    uniques: int


@dataclass(frozen=True, slots=True)
class DailyCount:
    """The counts of one UTC day."""

    day: date
    count: int
    uniques: int


@dataclass(frozen=True, slots=True)
class RankedEntry:
    """One referrer or path of the popular lists."""

    name: str
    count: int
    uniques: int


@dataclass(frozen=True, slots=True)
class RepositoryTraffic:
    """The traffic of one repository over the last 14 days."""

    views: TrafficTotals
    clones: TrafficTotals
    daily_views: tuple[DailyCount, ...]
    referrers: tuple[RankedEntry, ...]
    paths: tuple[RankedEntry, ...]


@dataclass(frozen=True, slots=True)
class VisitorTrend:
    """Daily unique visitors of the last week against the earlier days."""

    percent: float
    recent_average: float
    previous_average: float


def _totals(raw: dict[str, Any]) -> TrafficTotals:
    return TrafficTotals(count=raw.get("count", 0), uniques=raw.get("uniques", 0))


def _day(raw: dict[str, Any]) -> DailyCount:
    stamp = datetime.fromisoformat(raw["timestamp"])
    return DailyCount(stamp.date(), raw["count"], raw["uniques"])


def _ranked(raw: Sequence[dict[str, Any]], name_key: str) -> tuple[RankedEntry, ...]:
    return tuple(
        RankedEntry(item[name_key], item["count"], item["uniques"])
        for item in raw[:TOP_LIMIT]
    )


def parse_traffic(
    views: dict[str, Any],
    clones: dict[str, Any],
    referrers: Sequence[dict[str, Any]],
    paths: Sequence[dict[str, Any]],
) -> RepositoryTraffic:
    """Turn the four traffic responses into one value.

    Missing fields count as zero, so an empty response is valid.
    """
    return RepositoryTraffic(
        views=_totals(views),
        clones=_totals(clones),
        daily_views=tuple(_day(item) for item in views.get("views", [])),
        referrers=_ranked(referrers, "referrer"),
        paths=_ranked(paths, "path"),
    )


def peak_day(traffic: RepositoryTraffic) -> DailyCount | None:
    """Return the day with the most unique visitors; the latest wins a tie."""
    if not traffic.daily_views:
        return None
    return max(traffic.daily_views, key=lambda item: (item.uniques, item.day))


def visitor_trend(traffic: RepositoryTraffic, today: date) -> VisitorTrend | None:
    """Compare the daily visitor average of the last week with the days before it.

    ``today`` is incomplete and ignored. A day without an entry had no visitors.
    ``None`` when the earlier days have no visitors to compare against.
    """
    recent_start = today - timedelta(days=RECENT_DAYS)
    window_start = today - timedelta(days=WINDOW_DAYS - 1)
    recent = sum(
        item.uniques for item in traffic.daily_views if recent_start <= item.day < today
    )
    earlier = sum(
        item.uniques
        for item in traffic.daily_views
        if window_start <= item.day < recent_start
    )
    earlier_days = (recent_start - window_start).days
    previous_average = earlier / earlier_days
    recent_average = recent / RECENT_DAYS
    change = percent_change(recent_average, previous_average)
    if change is None:
        return None
    return VisitorTrend(round(change, 1), recent_average, previous_average)


def clone_ratio(traffic: RepositoryTraffic) -> float | None:
    """Return unique cloners per unique visitor, or ``None`` without visitors."""
    if traffic.views.uniques == 0:
        return None
    return round(traffic.clones.uniques / traffic.views.uniques, 2)
