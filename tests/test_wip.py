"""Tests for the work-in-progress figures and sensors."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock

import pytest
from custom_components.github_pulse.analytics.workflow import (
    average_hours_to_merge,
    stale_cutoff,
)
from custom_components.github_pulse.api import (
    GitHubClient,
    GitHubRateLimitError,
    RateBudget,
    RestResponse,
)
from custom_components.github_pulse.const import (
    CONF_HISTORY_YEARS,
    CONF_MODULES,
    CONF_OWNER,
    CONF_TOKEN_TYPE,
    DOMAIN,
)
from custom_components.github_pulse.profile_coordinator import GROUP_WIP
from custom_components.github_pulse.wip_fetch import fetch_wip
from homeassistant.const import CONF_ACCESS_TOKEN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from tests.fake_http import FakeResponse, FakeSession

NOW = datetime(2026, 10, 25, 12, tzinfo=UTC)


def _opened(hours_ago: float) -> datetime:
    return NOW - timedelta(hours=hours_ago)


def test_average_merge_time_over_merged_pull_requests() -> None:
    pairs = [
        (_opened(10), _opened(8)),  # 2 h
        (_opened(30), _opened(24)),  # 6 h
    ]

    assert average_hours_to_merge(pairs) == 4


def test_unmerged_pull_requests_do_not_count() -> None:
    pairs = [(_opened(10), _opened(8)), (_opened(50), None)]

    assert average_hours_to_merge(pairs) == 2


def test_no_pull_requests_gives_none() -> None:
    assert average_hours_to_merge([]) is None


def test_only_open_pull_requests_gives_none() -> None:
    assert average_hours_to_merge([(_opened(5), None), (_opened(9), None)]) is None


def test_a_merge_before_the_opening_is_ignored() -> None:
    assert average_hours_to_merge([(_opened(5), _opened(9))]) is None


def test_stale_cutoff_is_fourteen_days_back() -> None:
    assert stale_cutoff(NOW) == "2026-10-11"


def _client(merged: list[dict[str, Any]], stale: int) -> Any:
    client = AsyncMock(spec=GitHubClient)
    client.budget = RateBudget()
    client.rest_get.side_effect = [
        RestResponse({"total_count": len(merged), "items": merged}, {}),
        RestResponse({"total_count": stale, "items": []}, {}),
    ]
    return client


def _item(opened: str, merged: str | None) -> dict[str, Any]:
    return {"created_at": opened, "pull_request": {"merged_at": merged}}


async def test_fetch_combines_the_merge_time_and_the_stale_count() -> None:
    client = _client(
        [
            _item("2026-10-20T00:00:00Z", "2026-10-20T04:00:00Z"),
            _item("2026-10-21T00:00:00Z", "2026-10-21T08:00:00Z"),
            _item("2026-10-22T00:00:00Z", None),
        ],
        stale=3,
    )

    stats = await fetch_wip(client, "octocat", NOW)

    assert stats.hours_to_merge == 6
    assert stats.merged_sample == 2
    assert stats.stale_open == 3
    queries = [call.args[1]["q"] for call in client.rest_get.await_args_list]
    assert "is:merged author:octocat" in queries[0]
    assert "updated:<2026-10-11" in queries[1]


async def test_zero_pull_requests() -> None:
    stats = await fetch_wip(_client([], stale=0), "octocat", NOW)

    assert (stats.hours_to_merge, stats.merged_sample, stats.stale_open) == (
        None,
        0,
        0,
    )


async def test_a_spent_search_budget_skips_the_requests() -> None:
    client = _client([], stale=0)
    client.budget.update_from_headers(
        {
            "X-RateLimit-Limit": "30",
            "X-RateLimit-Remaining": "0",
            "X-RateLimit-Reset": "99999999999",
            "X-RateLimit-Resource": "search",
        }
    )

    with pytest.raises(GitHubRateLimitError):
        await fetch_wip(client, "octocat", NOW)

    client.rest_get.assert_not_awaited()


class _WipSession(FakeSession):
    def request(self, method: str, url: str, **kwargs: Any) -> FakeResponse:
        if "/search/issues" in url:
            query = (kwargs.get("params") or {}).get("q", "")
            if "is:merged" in query:
                items = [_item("2026-10-20T00:00:00Z", "2026-10-20T06:00:00Z")]
                return FakeResponse(body={"total_count": 1, "items": items})
            if "updated:<" in query:
                return FakeResponse(body={"total_count": 2, "items": []})
            return FakeResponse(body={"total_count": 0, "items": []})
        return super().request(method, url, **kwargs)


async def test_the_sensors_report_the_figures_when_enabled(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None]
) -> None:
    patch_session(_WipSession())
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="octocat",
        data={
            CONF_ACCESS_TOKEN: "token",
            CONF_OWNER: "octocat",
            CONF_TOKEN_TYPE: "classic",
            CONF_MODULES: ["profile"],
        },
        options={CONF_HISTORY_YEARS: 1},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    assert GROUP_WIP not in entry.runtime_data.profile.active_groups

    registry = er.async_get(hass)
    keys = ("average_time_to_merge", "stale_pull_requests")
    for key in keys:
        sensor = next(
            e for e in registry.entities.values() if e.unique_id.endswith(key)
        )
        registry.async_update_entity(sensor.entity_id, disabled_by=None)
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    states = {
        key: hass.states.get(
            next(
                e.entity_id
                for e in registry.entities.values()
                if e.unique_id.endswith(key)
            )
        )
        for key in keys
    }
    assert states["average_time_to_merge"].state == "6.0"
    assert states["average_time_to_merge"].attributes["merged_pull_requests"] == 1
    assert states["stale_pull_requests"].state == "2"
