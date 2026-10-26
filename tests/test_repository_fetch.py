"""Tests for the batched repository fetch and coordinator."""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import UTC, date, datetime
from typing import Any
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

from custom_components.github_pulse.api import GitHubClient, GraphQLResult
from custom_components.github_pulse.api.query_validation import parse_query
from custom_components.github_pulse.api.repository import _LIST_QUERY
from custom_components.github_pulse.const import (
    CONF_ACTIONS,
    CONF_MODULES,
    CONF_OWNER,
    CONF_REPOSITORY,
    CONF_TOKEN_TYPE,
    DOMAIN,
    SUBENTRY_REPOSITORY,
)
from custom_components.github_pulse.repository_coordinator import (
    GROUP_OVERVIEW,
    tracked_repositories,
)
from custom_components.github_pulse.repository_fetch import (
    BATCH_SIZE,
    build_query,
    fetch_snapshots,
    fetch_total_downloads,
)
from homeassistant.config_entries import ConfigSubentryData
from homeassistant.const import CONF_ACCESS_TOKEN
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from tests.fake_http import FakeResponse, FakeSession

TODAY = date(2026, 10, 25)
ZONE = ZoneInfo("America/Los_Angeles")

RAW = {
    "nameWithOwner": "Octocat/Hello-World",
    "stargazerCount": 42,
    "forkCount": 7,
    "isArchived": False,
    "pushedAt": "2026-10-24T10:00:00Z",
    "watchers": {"totalCount": 5},
    "issues": {"totalCount": 3},
    "pullRequests": {"totalCount": 2},
    "defaultBranchRef": {
        "name": "main",
        "target": {
            "committedDate": "2026-10-24T09:00:00Z",
            "statusCheckRollup": {"state": "FAILURE"},
            "thisMonth": {
                "totalCount": 4,
                "nodes": [
                    {"committedDate": "2026-10-24T09:00:00Z"},
                    {"committedDate": "2026-10-24T18:00:00Z"},
                    {"committedDate": "2026-10-20T10:00:00Z"},
                    {"committedDate": "2026-10-02T10:00:00Z"},
                ],
            },
            "previousMonth": {"totalCount": 2},
            "previousYear": {"totalCount": 8},
        },
    },
    "latestRelease": {
        "tagName": "v1.2.0",
        "name": "One two",
        "url": "https://github.com/Octocat/Hello-World/releases/tag/v1.2.0",
        "publishedAt": "2026-10-01T00:00:00Z",
        "isPrerelease": False,
        "releaseAssets": {"nodes": [{"downloadCount": 10}, {"downloadCount": 5}]},
    },
}


SEARCH = {"p": {"issueCount": 6}, "i": {"issueCount": 9}}


def _client(**by_alias: dict[str, Any] | None) -> Any:
    async def graphql(query: str, variables: Any = None) -> GraphQLResult:
        aliases = re.findall(r"(r\d+): repository", query)
        data = {a: by_alias.get(a, RAW) for a in aliases}
        for alias in re.findall(r"([pi]\d+): search", query):
            data[alias] = by_alias.get(alias, SEARCH[alias[0]])
        return GraphQLResult(data, [])

    client = AsyncMock(spec=GitHubClient)
    client.graphql.side_effect = graphql
    return client


def test_query_has_an_alias_and_variables_per_repository() -> None:
    query, variables = build_query(["a/b", "c/d"], TODAY, ZONE)

    assert "r0: repository(owner: $o0, name: $n0)" in query
    assert "r1: repository(owner: $o1, name: $n1)" in query
    assert (variables["o0"], variables["n0"]) == ("a", "b")
    assert (variables["o1"], variables["n1"]) == ("c", "d")


async def test_snapshot_reads_counts_ci_state_and_release_downloads() -> None:
    result = await fetch_snapshots(
        _client(), ["Octocat/Hello-World"], today=TODAY, zone=ZONE
    )

    snapshot = result["Octocat/Hello-World"]
    assert snapshot is not None
    assert (snapshot.stars, snapshot.forks, snapshot.watchers) == (42, 7, 5)
    assert (snapshot.open_issues, snapshot.open_pull_requests) == (3, 2)
    assert snapshot.ci_state == "FAILURE"
    assert snapshot.default_branch == "main"
    assert snapshot.last_commit_at == datetime(2026, 10, 24, 9, tzinfo=UTC)
    assert snapshot.latest_release is not None
    assert snapshot.latest_release.tag == "v1.2.0"
    assert snapshot.latest_release.downloads == 15


async def test_adding_a_repository_does_not_add_a_request() -> None:
    one, ten = _client(), _client()

    await fetch_snapshots(one, ["a/r0"], today=TODAY, zone=ZONE)
    names = [f"a/r{i}" for i in range(10)]
    await fetch_snapshots(ten, names, today=TODAY, zone=ZONE)

    assert one.graphql.await_count == ten.graphql.await_count == 1


async def test_very_long_lists_are_split_into_batches() -> None:
    client = _client()

    names = [f"a/r{i}" for i in range(BATCH_SIZE + 1)]
    result = await fetch_snapshots(client, names, today=TODAY, zone=ZONE)

    assert client.graphql.await_count == 2
    assert len(result) == BATCH_SIZE + 1


async def test_a_repository_without_release_or_ci_still_parses() -> None:
    bare = {**RAW, "defaultBranchRef": None, "latestRelease": None}

    result = await fetch_snapshots(_client(r0=bare), ["a/b"], today=TODAY, zone=ZONE)

    snapshot = result["a/b"]
    assert snapshot is not None
    assert snapshot.ci_state is None
    assert snapshot.latest_release is None
    assert snapshot.default_branch is None
    assert snapshot.activity is None


async def test_an_unreadable_repository_maps_to_none() -> None:
    result = await fetch_snapshots(
        _client(r1=None), ["a/ok", "a/hidden"], today=TODAY, zone=ZONE
    )

    assert result["a/ok"] is not None
    assert result["a/hidden"] is None


async def test_activity_counts_commits_and_active_days_of_all_authors() -> None:
    result = await fetch_snapshots(
        _client(), ["Octocat/Hello-World"], today=TODAY, zone=ZONE
    )

    activity = result["Octocat/Hello-World"].activity
    assert activity is not None
    assert activity.commits_this_month == 4
    assert activity.commits_previous_month == 2
    assert activity.commits_previous_year == 8
    assert activity.active_days == 3
    assert activity.elapsed_days == 25
    assert activity.truncated is False


async def test_active_days_follow_the_contribution_time_zone() -> None:
    late = {
        **RAW,
        "defaultBranchRef": {
            "name": "main",
            "target": {
                **RAW["defaultBranchRef"]["target"],
                "thisMonth": {
                    "totalCount": 2,
                    "nodes": [
                        {"committedDate": "2026-10-02T03:00:00Z"},
                        {"committedDate": "2026-10-02T10:00:00Z"},
                    ],
                },
            },
        },
    }

    result = await fetch_snapshots(_client(r0=late), ["a/b"], today=TODAY, zone=ZONE)

    # 03:00 UTC is still October 1st in Pacific time.
    assert result["a/b"].activity.active_days == 2


async def test_a_busy_month_is_flagged_as_truncated() -> None:
    busy = {
        **RAW,
        "defaultBranchRef": {
            "name": "main",
            "target": {
                **RAW["defaultBranchRef"]["target"],
                "thisMonth": {
                    "totalCount": 250,
                    "nodes": [{"committedDate": "2026-10-24T09:00:00Z"}] * 100,
                },
            },
        },
    }

    result = await fetch_snapshots(_client(r0=busy), ["a/b"], today=TODAY, zone=ZONE)

    activity = result["a/b"].activity
    assert activity.commits_this_month == 250
    assert activity.truncated is True


async def test_the_query_asks_for_the_comparison_windows_in_the_same_request() -> None:
    query, _ = build_query(["a/b"], TODAY, ZONE)

    assert 'thisMonth: history(since: "2026-10-01T07:00:00Z"' in query
    assert 'until: "2026-10-26T06:59:59Z"' in query
    assert 'previousMonth: history(since: "2026-09-01T07:00:00Z"' in query
    assert 'previousYear: history(since: "2025-10-01T07:00:00Z"' in query


def test_the_query_counts_pull_requests_and_issues_created_this_month() -> None:
    query, variables = build_query(["a/b"], TODAY, ZONE)

    assert "p0: search(query: $p0, type: ISSUE, first: 1) { issueCount }" in query
    assert "i0: search(query: $i0, type: ISSUE, first: 1) { issueCount }" in query
    window = "created:2026-10-01T07:00:00Z..2026-10-26T06:59:59Z"
    assert variables["p0"] == f"repo:a/b is:pr {window}"
    assert variables["i0"] == f"repo:a/b is:issue {window}"


async def test_snapshot_reads_the_pull_request_and_issue_counts() -> None:
    result = await fetch_snapshots(_client(), ["a/b"], today=TODAY, zone=ZONE)

    snapshot = result["a/b"]
    assert snapshot is not None
    assert (snapshot.pull_requests_this_month, snapshot.issues_this_month) == (6, 9)


async def test_a_missing_search_result_leaves_the_counts_unknown() -> None:
    result = await fetch_snapshots(
        _client(p0=None, i0=None), ["a/b"], today=TODAY, zone=ZONE
    )

    snapshot = result["a/b"]
    assert snapshot is not None
    assert snapshot.pull_requests_this_month is None
    assert snapshot.issues_this_month is None


async def test_total_downloads_sum_every_release_asset() -> None:
    client = AsyncMock(spec=GitHubClient)
    client.rest_get_pages.return_value = [
        {"assets": [{"download_count": 4}, {"download_count": 6}]},
        {"assets": []},
        {},
    ]

    assert await fetch_total_downloads(client, "a/b") == 10


def _subentry(name: str) -> ConfigSubentryData:
    return ConfigSubentryData(
        data={CONF_REPOSITORY: name, CONF_ACTIONS: False},
        subentry_type=SUBENTRY_REPOSITORY,
        title=name,
        unique_id=name.lower(),
    )


async def test_the_coordinator_loads_every_tracked_repository(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None]
) -> None:
    session = FakeSession(
        FakeResponse(
            body={
                "data": {
                    "r0": {**RAW, "nameWithOwner": "a/one"},
                    "r1": {**RAW, "nameWithOwner": "b/two", "stargazerCount": 1},
                }
            }
        )
    )
    patch_session(session)
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="octocat",
        data={
            CONF_ACCESS_TOKEN: "token",
            CONF_OWNER: "octocat",
            CONF_TOKEN_TYPE: "classic",
            CONF_MODULES: ["repositories"],
        },
        subentries_data=[_subentry("b/two"), _subentry("a/one")],
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)

    coordinator = entry.runtime_data.repositories
    assert tracked_repositories(entry) == ["a/one", "b/two"]
    assert coordinator.data[GROUP_OVERVIEW]["a/one"].stars == 42
    assert coordinator.data[GROUP_OVERVIEW]["b/two"].stars == 1
    assert len(session.requests) == 1


async def test_without_repositories_no_coordinator_is_created(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None]
) -> None:
    patch_session(FakeSession())
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="octocat",
        data={
            CONF_ACCESS_TOKEN: "token",
            CONF_OWNER: "octocat",
            CONF_TOKEN_TYPE: "classic",
            CONF_MODULES: ["repositories"],
        },
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)

    assert entry.runtime_data.repositories is None


def test_the_listing_query_is_valid_graphql() -> None:
    assert parse_query(_LIST_QUERY).declared_variables == frozenset()
