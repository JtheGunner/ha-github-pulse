"""Tests for month planning and the refresh policy."""

from datetime import UTC, date, datetime, timedelta

from custom_components.github_pulse.analytics.history import (
    MonthKey,
    chunk_months,
    months_back,
    needs_refresh,
)

TODAY = date(2026, 10, 25)
NOW = datetime(2026, 10, 25, 12, tzinfo=UTC)


def test_months_back_spans_the_requested_years() -> None:
    keys = months_back(TODAY, 3)

    assert len(keys) == 37
    assert keys[0] == MonthKey(2023, 10)
    assert keys[-1] == MonthKey(2026, 10)


def test_months_back_crosses_the_year_boundary() -> None:
    assert months_back(date(2026, 2, 1), 0) == [MonthKey(2026, 2)]
    assert months_back(date(2026, 1, 5), 1)[0] == MonthKey(2025, 1)


def test_month_label_round_trips() -> None:
    assert MonthKey.parse(MonthKey(2024, 3).label) == MonthKey(2024, 3)


def test_never_fetched_months_are_due() -> None:
    assert needs_refresh(MonthKey(2024, 1), None, TODAY, NOW)


def test_recent_months_refresh_daily() -> None:
    key = MonthKey(2026, 9)

    assert not needs_refresh(key, NOW - timedelta(hours=23), TODAY, NOW)
    assert needs_refresh(key, NOW - timedelta(days=1), TODAY, NOW)


def test_old_months_refresh_weekly() -> None:
    key = MonthKey(2025, 3)

    assert not needs_refresh(key, NOW - timedelta(days=6), TODAY, NOW)
    assert needs_refresh(key, NOW - timedelta(days=7), TODAY, NOW)


def test_the_third_last_month_counts_as_old() -> None:
    key = MonthKey(2026, 7)

    assert not needs_refresh(key, NOW - timedelta(days=3), TODAY, NOW)


def test_chunks_hold_at_most_twelve_months_oldest_first() -> None:
    chunks = chunk_months(months_back(TODAY, 3))

    assert [len(c) for c in chunks] == [12, 12, 12, 1]
    assert chunks[0][0] == MonthKey(2023, 10)
    assert chunk_months([]) == []
