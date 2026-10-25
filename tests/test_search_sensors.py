"""Tests for the search-API sensors and their separate rate budget."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any
from unittest.mock import AsyncMock

import pytest
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
from custom_components.github_pulse.profile_coordinator import GROUP_SEARCH
from custom_components.github_pulse.search_fetch import fetch_search_counts
from homeassistant.const import CONF_ACCESS_TOKEN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from tests.fake_http import FakeResponse, FakeSession

SEARCH_HEADERS = {
    "X-RateLimit-Limit": "30",
    "X-RateLimit-Remaining": "0",
    "X-RateLimit-Reset": "99999999999",
    "X-RateLimit-Resource": "search",
}


def _client(totals: list[int], budget: RateBudget | None = None) -> Any:
    client = AsyncMock(spec=GitHubClient)
    client.budget = budget or RateBudget()
    client.rest_get.side_effect = [
        RestResponse({"total_count": total}, {}) for total in totals
    ]
    return client


async def test_counts_come_from_two_searches() -> None:
    client = _client([3, 5])

    counts = await fetch_search_counts(client, "octocat")

    assert (counts.review_requested, counts.authored_open) == (3, 5)
    queries = [call.args[1]["q"] for call in client.rest_get.await_args_list]
    assert "review-requested:octocat" in queries[0]
    assert "author:octocat" in queries[1]
    assert all("is:pr is:open" in q for q in queries)


async def test_empty_results_count_as_zero() -> None:
    counts = await fetch_search_counts(_client([0, 0]), "octocat")

    assert (counts.review_requested, counts.authored_open) == (0, 0)


async def test_an_exhausted_search_budget_skips_the_request() -> None:
    budget = RateBudget()
    budget.update_from_headers(SEARCH_HEADERS)
    client = _client([], budget)

    with pytest.raises(GitHubRateLimitError) as raised:
        await fetch_search_counts(client, "octocat")

    client.rest_get.assert_not_awaited()
    assert raised.value.reset_at == 99999999999


async def test_a_spent_core_budget_does_not_block_search() -> None:
    budget = RateBudget()
    budget.update_from_headers({**SEARCH_HEADERS, "X-RateLimit-Resource": "core"})

    counts = await fetch_search_counts(_client([1, 2], budget), "octocat")

    assert counts.review_requested == 1


class _SearchSession(FakeSession):
    def request(self, method: str, url: str, **kwargs: Any) -> FakeResponse:
        if "/search/issues" in url:
            query = (kwargs.get("params") or {}).get("q", "")
            total = 4 if "review-requested" in query else 7
            return FakeResponse(body={"total_count": total})
        return super().request(method, url, **kwargs)


async def test_the_sensors_report_the_counts_when_enabled(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None]
) -> None:
    patch_session(_SearchSession())
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
    assert GROUP_SEARCH not in entry.runtime_data.profile.active_groups

    registry = er.async_get(hass)
    for key in ("review_requests", "authored_open_pull_requests"):
        sensor = next(
            e for e in registry.entities.values() if e.unique_id.endswith(key)
        )
        registry.async_update_entity(sensor.entity_id, disabled_by=None)
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    states = {
        e.unique_id.split("_", 1)[1]: hass.states.get(e.entity_id).state
        for e in registry.entities.values()
        if e.unique_id.endswith(("review_requests", "authored_open_pull_requests"))
    }
    assert states == {"review_requests": "4", "authored_open_pull_requests": "7"}
