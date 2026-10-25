"""Tests for period math and like-for-like comparisons."""

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import pytest
from custom_components.github_pulse.analytics.periods import (
    DateRange,
    like_for_like_previous_month,
    like_for_like_previous_year,
    month_range,
    month_to_date,
    percent_change,
    previous_month,
    to_utc_window,
)


def test_date_range_counts_days_inclusively() -> None:
    assert DateRange(date(2026, 10, 1), date(2026, 10, 1)).days == 1
    assert DateRange(date(2026, 10, 1), date(2026, 10, 25)).days == 25


def test_date_range_rejects_reversed_bounds() -> None:
    with pytest.raises(ValueError, match="before"):
        DateRange(date(2026, 10, 2), date(2026, 10, 1))


@pytest.mark.parametrize(
    ("year", "month", "last_day"),
    [(2026, 2, 28), (2028, 2, 29), (2026, 4, 30), (2026, 12, 31)],
)
def test_month_range_covers_the_whole_month(
    year: int, month: int, last_day: int
) -> None:
    rng = month_range(year, month)

    assert rng.start == date(year, month, 1)
    assert rng.end == date(year, month, last_day)


def test_previous_month_crosses_the_year_boundary() -> None:
    assert previous_month(2026, 1) == (2025, 12)
    assert previous_month(2026, 10) == (2026, 9)


def test_month_to_date_ends_today() -> None:
    assert month_to_date(date(2026, 10, 25)) == DateRange(
        date(2026, 10, 1), date(2026, 10, 25)
    )


def test_like_for_like_previous_month_has_the_same_number_of_days() -> None:
    rng = like_for_like_previous_month(date(2026, 10, 25))

    assert rng == DateRange(date(2026, 9, 1), date(2026, 9, 25))
    assert rng.days == month_to_date(date(2026, 10, 25)).days


def test_like_for_like_previous_month_is_clamped_to_a_shorter_month() -> None:
    # March 31 has 31 elapsed days, February only has 28.
    assert like_for_like_previous_month(date(2026, 3, 31)) == DateRange(
        date(2026, 2, 1), date(2026, 2, 28)
    )


def test_like_for_like_previous_month_in_january_uses_december() -> None:
    assert like_for_like_previous_month(date(2026, 1, 10)) == DateRange(
        date(2025, 12, 1), date(2025, 12, 10)
    )


def test_like_for_like_previous_year_keeps_the_month() -> None:
    assert like_for_like_previous_year(date(2026, 10, 25)) == DateRange(
        date(2025, 10, 1), date(2025, 10, 25)
    )


def test_like_for_like_previous_year_handles_leap_day() -> None:
    # 2028-02-29 compared with February 2027, which has no 29th.
    assert like_for_like_previous_year(date(2028, 2, 29)) == DateRange(
        date(2027, 2, 1), date(2027, 2, 28)
    )


@pytest.mark.parametrize(
    ("current", "previous", "expected"),
    [(150, 100, 50.0), (50, 100, -50.0), (100, 100, 0.0), (0, 100, -100.0)],
)
def test_percent_change(current: int, previous: int, expected: float) -> None:
    assert percent_change(current, previous) == expected


def test_percent_change_is_undefined_for_a_zero_baseline() -> None:
    assert percent_change(10, 0) is None
    assert percent_change(0, 0) is None


def test_to_utc_window_uses_the_zone_day_boundaries_in_summer() -> None:
    zone = ZoneInfo("America/Los_Angeles")

    start, end = to_utc_window(DateRange(date(2026, 10, 1), date(2026, 10, 25)), zone)

    assert start == datetime(2026, 10, 1, 7, 0, 0, tzinfo=UTC)
    assert end == datetime(2026, 10, 26, 6, 59, 59, tzinfo=UTC)


def test_to_utc_window_follows_daylight_saving_in_winter() -> None:
    zone = ZoneInfo("America/Los_Angeles")

    start, end = to_utc_window(DateRange(date(2026, 3, 1), date(2026, 3, 1)), zone)

    assert start == datetime(2026, 3, 1, 8, 0, 0, tzinfo=UTC)
    assert end == datetime(2026, 3, 2, 7, 59, 59, tzinfo=UTC)


def test_to_utc_window_for_utc_is_the_identity() -> None:
    start, end = to_utc_window(
        DateRange(date(2026, 1, 1), date(2026, 1, 31)), ZoneInfo("UTC")
    )

    assert start == datetime(2026, 1, 1, tzinfo=UTC)
    assert end == datetime(2026, 1, 31, 23, 59, 59, tzinfo=UTC)
