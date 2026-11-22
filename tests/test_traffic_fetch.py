"""Tests for the repository traffic fetch and its coordinator group."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from custom_components.github_pulse.analytics.traffic import TrafficTotals
from custom_components.github_pulse.api import (
    GitHubClient,
    GitHubForbiddenError,
    GitHubNotFoundError,
    GitHubTransportError,
)
from custom_components.github_pulse.api.client import RestResponse
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
    GROUP_TRAFFIC,
    RepositoryCoordinator,
)
from custom_components.github_pulse.traffic_fetch import fetch_traffic
from homeassistant.config_entries import ConfigSubentryData
from homeassistant.const import CONF_ACCESS_TOKEN
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from tests.fake_http import FakeResponse, FakeSession
from tests.test_repository_fetch import RAW

VIEWS = {
    "count": 4,
    "uniques": 2,
    "views": [{"timestamp": "2026-11-19T00:00:00Z", "count": 4, "uniques": 2}],
}
CLONES = {"count": 9, "uniques": 3, "clones": []}
REFERRERS = [{"referrer": "Google", "count": 4, "uniques": 2}]
PATHS = [{"path": "/a/b", "title": "a/b", "count": 4, "uniques": 2}]

RESPONSES: dict[str, Any] = {
    "/traffic/views": VIEWS,
    "/traffic/clones": CLONES,
    "/traffic/popular/referrers": REFERRERS,
    "/traffic/popular/paths": PATHS,
}


def _client(
    failures: dict[str, Exception] | None = None,
) -> tuple[AsyncMock, list[str]]:
    """Return a client answering the traffic paths, and the paths it was asked."""
    asked: list[str] = []
    failures = failures or {}

    async def rest_get(path: str, params: Any = None) -> RestResponse:
        asked.append(path)
        for full_name, error in failures.items():
            if path.startswith(f"/repos/{full_name}/"):
                raise error
        suffix = path[path.index("/traffic") :]
        return RestResponse(RESPONSES[suffix], {})

    client = AsyncMock(spec=GitHubClient)
    client.rest_get.side_effect = rest_get
    client.budget = MagicMock()
    client.budget.is_low.return_value = False
    return client, asked


async def test_fetch_traffic_reads_the_four_endpoints() -> None:
    client, asked = _client()

    traffic = await fetch_traffic(client, "a/b")

    assert sorted(asked) == [
        "/repos/a/b/traffic/clones",
        "/repos/a/b/traffic/popular/paths",
        "/repos/a/b/traffic/popular/referrers",
        "/repos/a/b/traffic/views",
    ]
    assert traffic is not None
    assert traffic.views == TrafficTotals(count=4, uniques=2)
    assert traffic.clones == TrafficTotals(count=9, uniques=3)
    assert traffic.referrers[0].name == "Google"
    assert traffic.paths[0].name == "/a/b"


@pytest.mark.parametrize(
    "error", [GitHubForbiddenError("no push access"), GitHubNotFoundError("hidden")]
)
async def test_an_unreadable_repository_maps_to_none(error: Exception) -> None:
    client, _ = _client({"a/b": error})

    assert await fetch_traffic(client, "a/b") is None


async def test_other_errors_propagate() -> None:
    client, _ = _client({"a/b": GitHubTransportError("connection reset")})

    with pytest.raises(GitHubTransportError):
        await fetch_traffic(client, "a/b")


def _subentry(name: str) -> ConfigSubentryData:
    return ConfigSubentryData(
        data={CONF_REPOSITORY: name, CONF_ACTIONS: False},
        subentry_type=SUBENTRY_REPOSITORY,
        title=name,
        unique_id=name.lower(),
    )


async def _coordinator(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None]
) -> RepositoryCoordinator:
    patch_session(
        FakeSession(
            FakeResponse(
                body={
                    "data": {
                        "r0": {**RAW, "nameWithOwner": "a/one"},
                        "r1": {**RAW, "nameWithOwner": "b/two"},
                    }
                }
            )
        )
    )
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="octocat",
        data={
            CONF_ACCESS_TOKEN: "token",
            CONF_OWNER: "octocat",
            CONF_TOKEN_TYPE: "classic",
            CONF_MODULES: ["repositories"],
        },
        subentries_data=[_subentry("a/one"), _subentry("b/two")],
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    return RepositoryCoordinator(
        hass,
        entry,
        settings=entry.runtime_data.settings,
        active_groups={GROUP_TRAFFIC},
    )


async def test_one_forbidden_repository_keeps_the_others(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None]
) -> None:
    coordinator = await _coordinator(hass, patch_session)
    client, _ = _client({"b/two": GitHubForbiddenError("no push access")})
    coordinator.client = client

    await coordinator.async_refresh()

    traffic = coordinator.data[GROUP_TRAFFIC]
    assert traffic["b/two"] is None
    assert traffic["a/one"] is not None
    assert traffic["a/one"].views.uniques == 2
