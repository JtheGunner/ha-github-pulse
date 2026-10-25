"""Tests for the language fetcher and store."""

from __future__ import annotations

import re
from datetime import UTC, date, datetime
from typing import Any
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import pytest
from custom_components.github_pulse.analytics.history import MonthKey
from custom_components.github_pulse.analytics.languages import shares
from custom_components.github_pulse.api import GitHubClient, GraphQLResult
from custom_components.github_pulse.language_fetch import (
    build_language_query,
    parse_repositories,
)
from custom_components.github_pulse.language_store import LanguageStore
from homeassistant.core import HomeAssistant

ZONE = ZoneInfo("America/Los_Angeles")
TODAY = date(2026, 10, 25)
NOW = datetime(2026, 10, 25, 12, tzinfo=UTC)
ENTRY = {
    "contributions": {"totalCount": 4},
    "repository": {
        "languages": {
            "edges": [
                {"size": 300, "node": {"name": "PHP"}},
                {"size": 100, "node": {"name": "Shell"}},
            ]
        }
    },
}


def _client() -> Any:
    async def graphql(query: str, variables: Any = None) -> GraphQLResult:
        user = {
            alias: {"commitContributionsByRepository": [ENTRY]}
            for alias in re.findall(r"(m\d{6}): ", query)
        }
        return GraphQLResult({"user": user}, [])

    client = AsyncMock(spec=GitHubClient)
    client.graphql.side_effect = graphql
    return client


def test_query_asks_for_repository_languages_per_month() -> None:
    query = build_language_query([MonthKey(2026, 3)], ZONE)

    assert "m202603: contributionsCollection" in query
    assert "commitContributionsByRepository(maxRepositories: 100)" in query
    assert "languages(first: 20" in query


def test_parse_handles_a_repository_the_token_cannot_read() -> None:
    repos = parse_repositories(
        [{"contributions": {"totalCount": 3}, "repository": None}]
    )

    assert repos[0].commits == 3
    assert repos[0].languages == {}


def test_parse_reads_language_bytes() -> None:
    assert parse_repositories([ENTRY])[0].languages == {"PHP": 300, "Shell": 100}


async def test_months_are_estimated_and_survive_a_restart(
    hass: HomeAssistant,
) -> None:
    first = LanguageStore(hass, "entry")
    client = _client()
    fetched = await first.async_refresh(
        client, "octocat", ZONE, today=TODAY, years=1, now=NOW
    )

    second = LanguageStore(hass, "entry")
    await second.async_load()
    client.graphql.reset_mock()
    refetched = await second.async_refresh(
        client, "octocat", ZONE, today=TODAY, years=1, now=NOW
    )

    assert fetched == 13
    assert refetched == 0
    month = second.months[MonthKey(2026, 10)]
    assert shares(month, by_commits=True) == pytest.approx({"PHP": 0.75, "Shell": 0.25})
    assert month == first.months[MonthKey(2026, 10)]
