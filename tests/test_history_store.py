"""Tests for the history fetcher and store."""

from __future__ import annotations

import re
from datetime import UTC, date, datetime
from typing import Any
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

from custom_components.github_pulse.analytics.history import MonthKey
from custom_components.github_pulse.api import GitHubClient, GraphQLResult
from custom_components.github_pulse.history_fetch import build_query
from custom_components.github_pulse.history_store import HistoryStore
from homeassistant.core import HomeAssistant

ZONE = ZoneInfo("America/Los_Angeles")
TODAY = date(2026, 10, 25)
NOW = datetime(2026, 10, 25, 12, tzinfo=UTC)
RAW = {
    "totalCommitContributions": 10,
    "totalPullRequestContributions": 2,
    "totalIssueContributions": 1,
    "totalPullRequestReviewContributions": 3,
    "restrictedContributionsCount": 4,
}


def _client() -> Any:
    async def graphql(query: str, variables: Any = None) -> GraphQLResult:
        user = dict.fromkeys(re.findall(r"(m\d{6}): ", query), RAW)
        return GraphQLResult({"user": user}, [])

    client = AsyncMock(spec=GitHubClient)
    client.graphql.side_effect = graphql
    return client


def test_query_uses_one_alias_per_month_in_the_contribution_zone() -> None:
    query = build_query([MonthKey(2026, 3), MonthKey(2026, 4)], ZONE)

    assert "m202603: contributionsCollection" in query
    assert "m202604: contributionsCollection" in query
    assert 'from: "2026-03-01T08:00:00Z"' in query
    assert 'to: "2026-04-01T06:59:59Z"' in query


async def test_backfill_fetches_all_months_in_yearly_requests(
    hass: HomeAssistant,
) -> None:
    store = HistoryStore(hass, "entry")
    client = _client()

    fetched = await store.async_refresh(
        client, "octocat", ZONE, today=TODAY, years=3, now=NOW
    )

    assert fetched == 37
    assert client.graphql.await_count == 4
    assert store.months[MonthKey(2026, 10)].commits == 10


async def test_a_second_refresh_does_not_refetch_fresh_months(
    hass: HomeAssistant,
) -> None:
    store = HistoryStore(hass, "entry")
    client = _client()
    await store.async_refresh(client, "octocat", ZONE, today=TODAY, years=1, now=NOW)
    client.graphql.reset_mock()

    fetched = await store.async_refresh(
        client, "octocat", ZONE, today=TODAY, years=1, now=NOW
    )

    assert fetched == 0
    client.graphql.assert_not_awaited()


async def test_a_restart_does_not_refetch_closed_months(hass: HomeAssistant) -> None:
    first = HistoryStore(hass, "entry")
    await first.async_refresh(_client(), "octocat", ZONE, today=TODAY, years=1, now=NOW)

    second = HistoryStore(hass, "entry")
    await second.async_load()
    client = _client()
    fetched = await second.async_refresh(
        client, "octocat", ZONE, today=TODAY, years=1, now=NOW
    )

    assert fetched == 0
    assert second.months == first.months


async def test_a_corrupt_store_is_discarded_and_refetched(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    hass_storage["github_pulse.history.entry"] = {
        "version": 1,
        "key": "github_pulse.history.entry",
        "data": {"months": {"2026-10": {"stats": {"nope": 1}, "fetched_at": "x"}}},
    }
    store = HistoryStore(hass, "entry")

    await store.async_load()
    fetched = await store.async_refresh(
        _client(), "octocat", ZONE, today=TODAY, years=0, now=NOW
    )

    assert fetched == 1
