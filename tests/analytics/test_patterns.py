"""Tests for busiest month, streaks and weekday patterns."""

from datetime import date, timedelta

from custom_components.github_pulse.analytics.patterns import (
    BusiestMonth,
    Streaks,
    busiest_month,
    streaks,
    weekday_pattern,
)


def _days(start: date, counts: list[int]) -> dict[date, int]:
    return {start + timedelta(days=i): count for i, count in enumerate(counts)}


def test_busiest_month_picks_the_highest_total_of_the_year() -> None:
    monthly = {(2026, 1): 10, (2026, 3): 40, (2026, 4): 25, (2025, 12): 999}

    assert busiest_month(monthly, 2026) == BusiestMonth(month=3, count=40)


def test_busiest_month_prefers_the_earliest_month_on_a_tie() -> None:
    assert busiest_month({(2026, 5): 7, (2026, 2): 7}, 2026) == BusiestMonth(2, 7)


def test_busiest_month_is_none_without_activity() -> None:
    assert busiest_month({}, 2026) is None
    assert busiest_month({(2026, 1): 0, (2026, 2): 0}, 2026) is None
    assert busiest_month({(2025, 6): 50}, 2026) is None


def test_streaks_of_an_empty_history_are_zero() -> None:
    assert streaks({}, date(2026, 10, 25)) == Streaks(current=0, longest=0)


def test_current_streak_counts_back_from_today() -> None:
    today = date(2026, 10, 25)
    daily = _days(today - timedelta(days=4), [1, 2, 3, 1, 5])

    assert streaks(daily, today) == Streaks(current=5, longest=5)


def test_streak_stays_alive_while_today_is_still_empty() -> None:
    today = date(2026, 10, 25)
    daily = _days(today - timedelta(days=3), [1, 1, 1, 0])

    assert streaks(daily, today).current == 3


def test_streak_is_broken_after_a_missed_day() -> None:
    today = date(2026, 10, 25)
    daily = _days(today - timedelta(days=4), [1, 1, 0, 0, 0])

    assert streaks(daily, today).current == 0


def test_longest_streak_can_exceed_the_current_one() -> None:
    today = date(2026, 10, 25)
    daily = _days(today - timedelta(days=9), [1, 1, 1, 1, 1, 0, 1, 1, 0, 1])

    assert streaks(daily, today) == Streaks(current=1, longest=5)


def test_days_with_zero_count_do_not_extend_a_streak() -> None:
    today = date(2026, 10, 25)
    daily = {today: 0, today - timedelta(days=1): 0}

    assert streaks(daily, today) == Streaks(0, 0)


def test_streak_spans_the_year_boundary() -> None:
    today = date(2026, 1, 2)
    daily = _days(date(2025, 12, 30), [1, 1, 1, 1])

    assert streaks(daily, today) == Streaks(current=4, longest=4)


def test_weekday_pattern_finds_the_most_productive_weekday() -> None:
    # 2026-10-05 is a Monday.
    daily = _days(date(2026, 10, 5), [1, 2, 9, 1, 1, 0, 0])

    pattern = weekday_pattern(daily)

    assert pattern is not None
    assert pattern.most_productive == 2  # Wednesday
    assert pattern.totals[2] == 9
    assert len(pattern.totals) == 7


def test_weekday_pattern_sums_over_several_weeks() -> None:
    daily = _days(date(2026, 10, 5), [5, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 6])

    pattern = weekday_pattern(daily)

    assert pattern is not None
    assert pattern.most_productive == 6  # Sunday


def test_weekday_pattern_prefers_the_earliest_weekday_on_a_tie() -> None:
    daily = _days(date(2026, 10, 5), [4, 0, 4, 0, 0, 0, 0])

    pattern = weekday_pattern(daily)

    assert pattern is not None
    assert pattern.most_productive == 0


def test_weekday_pattern_is_none_without_activity() -> None:
    assert weekday_pattern({}) is None
    assert weekday_pattern(_days(date(2026, 10, 5), [0, 0, 0])) is None
