"""Tests for the preset query library."""

from __future__ import annotations

from datetime import date
from zoneinfo import ZoneInfo

import pytest
from custom_components.github_pulse.analytics.periods import month_range
from custom_components.github_pulse.analytics.query_variables import (
    HELPER_NAMES,
    query_variables,
)
from custom_components.github_pulse.api import GraphQLResult
from custom_components.github_pulse.api.query_validation import parse_query
from custom_components.github_pulse.custom_query import (
    QueryDefinition,
    resolve_variables,
    run_query,
)
from custom_components.github_pulse.history_fetch import _stats, build_ranges_query
from custom_components.github_pulse.query_presets import PRESETS, PRESETS_BY_KEY
from homeassistant.core import HomeAssistant

PACIFIC = ZoneInfo("America/Los_Angeles")
TODAY = date(2026, 10, 25)


class StubClient:
    def __init__(self, data: dict) -> None:
        self._data = data

    async def graphql(self, query: str, variables: object = None) -> GraphQLResult:
        return GraphQLResult(self._data, [])


@pytest.mark.parametrize("preset", PRESETS, ids=lambda p: p.key)
def test_every_preset_is_a_valid_query_whose_variables_are_helpers(preset) -> None:
    parsed = parse_query(preset.query)

    assert parsed.declared_variables <= HELPER_NAMES
    resolve_variables(
        parsed.declared_variables, query_variables(TODAY, "octocat", PACIFIC), {}
    )


def test_month_presets_use_the_same_window_as_the_built_in_sensors() -> None:
    built_in = build_ranges_query({"m": month_range(TODAY.year, TODAY.month)}, PACIFIC)
    variables = query_variables(TODAY, "octocat", PACIFIC)

    assert f'from: "{variables["start_of_month"]}"' in built_in
    assert f'to: "{variables["end_of_month"]}"' in built_in


@pytest.mark.parametrize(
    ("key", "field"),
    [
        ("commits_this_month", "commits"),
        ("pull_requests_this_month", "pull_requests"),
    ],
)
async def test_a_month_preset_yields_the_value_of_the_built_in_sensor(
    hass: HomeAssistant, key: str, field: str
) -> None:
    raw = {
        "totalCommitContributions": 37,
        "totalPullRequestContributions": 5,
        "totalIssueContributions": 2,
        "totalPullRequestReviewContributions": 9,
        "restrictedContributionsCount": 4,
    }
    preset = PRESETS_BY_KEY[key]
    client = StubClient({"user": {"contributionsCollection": raw}})

    outcome = await run_query(
        hass,
        client,
        QueryDefinition(preset.name, preset.query, preset.state_template),
    )

    assert outcome.state == getattr(_stats(raw), field)
