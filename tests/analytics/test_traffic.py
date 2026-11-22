"""Tests for the repository traffic summaries."""

from datetime import date

from custom_components.github_pulse.analytics.traffic import (
    DailyCount,
    RankedEntry,
    TrafficTotals,
    clone_ratio,
    parse_traffic,
    peak_day,
    visitor_trend,
)

TODAY = date(2026, 11, 20)


def _views(*days: tuple[str, int, int]) -> dict:
    return {
        "count": sum(count for _, count, _ in days),
        "uniques": sum(uniques for _, _, uniques in days),
        "views": [
            {"timestamp": f"{day}T00:00:00Z", "count": count, "uniques": uniques}
            for day, count, uniques in days
        ],
    }


def _clones(count: int = 0, uniques: int = 0) -> dict:
    return {"count": count, "uniques": uniques, "clones": []}


def _traffic(views: dict, clones: dict | None = None):
    return parse_traffic(views, clones or _clones(), [], [])


def test_parse_reads_totals_and_top_five() -> None:
    referrers = [
        {"referrer": f"site{i}", "count": 10 - i, "uniques": 5 - i} for i in range(7)
    ]
    paths = [
        {"path": f"/o/r/{i}", "title": "t", "count": 10 - i, "uniques": 5 - i}
        for i in range(6)
    ]

    traffic = parse_traffic(
        _views(("2026-11-19", 4, 2)), _clones(count=9, uniques=3), referrers, paths
    )

    assert traffic.views == TrafficTotals(count=4, uniques=2)
    assert traffic.clones == TrafficTotals(count=9, uniques=3)
    assert traffic.daily_views == (DailyCount(date(2026, 11, 19), 4, 2),)
    assert len(traffic.referrers) == 5
    assert traffic.referrers[0] == RankedEntry("site0", 10, 5)
    assert len(traffic.paths) == 5
    assert traffic.paths[0] == RankedEntry("/o/r/0", 10, 5)


def test_parse_handles_empty_responses() -> None:
    traffic = parse_traffic({}, {}, [], [])

    assert traffic.views == TrafficTotals(0, 0)
    assert traffic.clones == TrafficTotals(0, 0)
    assert traffic.daily_views == ()
    assert traffic.referrers == ()
    assert traffic.paths == ()


def test_peak_day_picks_most_uniques_and_the_latest_on_a_tie() -> None:
    traffic = _traffic(
        _views(("2026-11-10", 9, 4), ("2026-11-12", 3, 5), ("2026-11-14", 2, 5))
    )

    assert peak_day(traffic) == DailyCount(date(2026, 11, 14), 2, 5)


def test_peak_day_is_none_without_daily_data() -> None:
    assert peak_day(_traffic(_views())) is None


def test_trend_compares_recent_week_to_earlier_days() -> None:
    # Recent complete days are Nov 13-19 (7 days), earlier days Nov 7-12 (6 days).
    traffic = _traffic(
        _views(
            ("2026-11-08", 1, 2),
            ("2026-11-10", 1, 4),
            ("2026-11-14", 1, 7),
            ("2026-11-19", 1, 7),
            ("2026-11-20", 1, 50),  # today is incomplete and ignored
        )
    )

    trend = visitor_trend(traffic, TODAY)

    assert trend is not None
    assert trend.recent_average == 2.0
    assert trend.previous_average == 1.0
    assert trend.percent == 100.0


def test_trend_is_none_without_baseline() -> None:
    only_recent = _traffic(_views(("2026-11-18", 1, 5)))
    only_today = _traffic(_views(("2026-11-20", 1, 5)))
    nothing = _traffic(_views())

    assert visitor_trend(only_recent, TODAY) is None
    assert visitor_trend(only_today, TODAY) is None
    assert visitor_trend(nothing, TODAY) is None


def test_ratio_is_cloners_per_visitor() -> None:
    traffic = _traffic(_views(("2026-11-19", 5, 4)), _clones(count=20, uniques=6))

    assert clone_ratio(traffic) == 1.5


def test_ratio_is_none_without_visitors() -> None:
    assert clone_ratio(_traffic(_views(), _clones(count=3, uniques=2))) is None
