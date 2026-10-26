"""Tests for the batched repository fetch and coordinator."""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock

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


def _client(**by_alias: dict[str, Any] | None) -> Any:
    async def graphql(query: str, variables: Any = None) -> GraphQLResult:
        aliases = re.findall(r"(r\d+): repository", query)
        return GraphQLResult({a: by_alias.get(a, RAW) for a in aliases}, [])

    client = AsyncMock(spec=GitHubClient)
    client.graphql.side_effect = graphql
    return client


def test_query_has_an_alias_and_variables_per_repository() -> None:
    query, variables = build_query(["a/b", "c/d"])

    assert "r0: repository(owner: $o0, name: $n0)" in query
    assert "r1: repository(owner: $o1, name: $n1)" in query
    assert variables == {"o0": "a", "n0": "b", "o1": "c", "n1": "d"}


async def test_snapshot_reads_counts_ci_state_and_release_downloads() -> None:
    result = await fetch_snapshots(_client(), ["Octocat/Hello-World"])

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

    await fetch_snapshots(one, ["a/r0"])
    await fetch_snapshots(ten, [f"a/r{i}" for i in range(10)])

    assert one.graphql.await_count == ten.graphql.await_count == 1


async def test_very_long_lists_are_split_into_batches() -> None:
    client = _client()

    result = await fetch_snapshots(client, [f"a/r{i}" for i in range(BATCH_SIZE + 1)])

    assert client.graphql.await_count == 2
    assert len(result) == BATCH_SIZE + 1


async def test_a_repository_without_release_or_ci_still_parses() -> None:
    bare = {**RAW, "defaultBranchRef": None, "latestRelease": None}

    result = await fetch_snapshots(_client(r0=bare), ["a/b"])

    snapshot = result["a/b"]
    assert snapshot is not None
    assert snapshot.ci_state is None
    assert snapshot.latest_release is None
    assert snapshot.default_branch is None


async def test_an_unreadable_repository_maps_to_none() -> None:
    result = await fetch_snapshots(_client(r1=None), ["a/ok", "a/hidden"])

    assert result["a/ok"] is not None
    assert result["a/hidden"] is None


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
