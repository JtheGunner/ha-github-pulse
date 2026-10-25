"""Tests for the variable helpers of custom queries."""

from __future__ import annotations

from datetime import date
from zoneinfo import ZoneInfo

from custom_components.github_pulse.analytics.query_variables import (
    HELPER_NAMES,
    query_variables,
)

PACIFIC = ZoneInfo("America/Los_Angeles")


def test_offers_exactly_the_documented_helpers() -> None:
    assert set(query_variables(date(2026, 10, 25), "octocat", PACIFIC)) == HELPER_NAMES


def test_month_bounds_follow_the_time_zone() -> None:
    variables = query_variables(date(2026, 10, 25), "octocat", PACIFIC)

    assert variables["start_of_month"] == "2026-10-01T07:00:00Z"
    assert variables["end_of_month"] == "2026-11-01T06:59:59Z"


def test_year_helpers() -> None:
    variables = query_variables(date(2026, 10, 25), "octocat", PACIFIC)

    assert variables["start_of_year"] == "2026-01-01T08:00:00Z"
    assert variables["one_year_ago"] == "2025-10-25T07:00:00Z"
    assert variables["owner"] == "octocat"


def test_leap_day_maps_to_the_28th_a_year_earlier() -> None:
    variables = query_variables(date(2028, 2, 29), "octocat", ZoneInfo("UTC"))

    assert variables["one_year_ago"] == "2027-02-28T00:00:00Z"


def test_utc_zone_has_no_offset() -> None:
    variables = query_variables(date(2026, 1, 15), "octocat", ZoneInfo("UTC"))

    assert variables["start_of_month"] == "2026-01-01T00:00:00Z"
    assert variables["end_of_month"] == "2026-01-31T23:59:59Z"
