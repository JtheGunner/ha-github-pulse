"""Hardening scenarios: large accounts, outages, revoked tokens and rate limits."""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any
from unittest.mock import patch

from custom_components.github_pulse.const import (
    CONF_HISTORY_YEARS,
    CONF_MODULES,
    CONF_OWNER,
    CONF_TOKEN_TYPE,
    DOMAIN,
)
from custom_components.github_pulse.repository_coordinator import GROUP_OVERVIEW
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_ACCESS_TOKEN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from tests.fake_http import FakeResponse, FakeSession, transport_failure
from tests.test_repository_fetch import RAW, _subentry


def _entry(modules: list[str], **extra: Any) -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        unique_id="octocat",
        data={
            CONF_ACCESS_TOKEN: "token",
            CONF_OWNER: "octocat",
            CONF_TOKEN_TYPE: "classic",
            CONF_MODULES: modules,
        },
        options={CONF_HISTORY_YEARS: 1},
        **extra,
    )


class _AccountSession(FakeSession):
    """Answer repository snapshots for any number of repositories.

    ``mode`` switches the whole account: ``"ok"``, ``"revoked"`` (401),
    ``"limited"`` (403 with an empty budget) or ``"offline"``.
    """

    def __init__(self) -> None:
        super().__init__()
        self.mode = "ok"
        self.snapshots = 0

    def request(self, method: str, url: str, **kwargs: Any) -> FakeResponse:
        if self.mode == "revoked":
            return FakeResponse(401, {"message": "Bad credentials"})
        if self.mode == "limited":
            return FakeResponse(
                403,
                {"message": "API rate limit exceeded"},
                {
                    "X-RateLimit-Limit": "5000",
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": "99999999999",
                    "X-RateLimit-Resource": "graphql",
                },
            )
        if self.mode == "offline":
            return transport_failure()
        body = kwargs.get("json")
        if isinstance(body, dict) and "repository(" in body.get("query", ""):
            self.snapshots += 1
            aliases = re.findall(r"(r\d+): repository", body["query"])
            data = {a: {**RAW, "nameWithOwner": f"org/{a}"} for a in aliases}
            return FakeResponse(body={"data": data})
        return super().request(method, url, **kwargs)


async def test_a_large_account_is_fetched_in_batches(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None]
) -> None:
    session = _AccountSession()
    patch_session(session)
    names = [f"org/repo{i:03d}" for i in range(120)]
    entry = _entry(
        ["repositories"], subentries_data=[_subentry(name) for name in names]
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert session.snapshots == 3  # 120 repositories in batches of 50
    registry = er.async_get(hass)
    stars = [e for e in registry.entities.values() if e.unique_id.endswith("_stars")]
    assert len(stars) == 120
    assert len(entry.runtime_data.repositories.data[GROUP_OVERVIEW]) == 120


async def test_starting_offline_retries_instead_of_failing(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None]
) -> None:
    session = _AccountSession()
    session.mode = "offline"
    patch_session(session)
    entry = _entry(["profile"])
    entry.add_to_hass(hass)

    with patch("custom_components.github_pulse.api.client._backoff", return_value=0):
        await hass.config_entries.async_setup(entry.entry_id)

    assert entry.state is ConfigEntryState.SETUP_RETRY
    assert not hass.config_entries.flow.async_progress()


async def test_a_token_revoked_while_running_starts_reauthentication(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None]
) -> None:
    session = _AccountSession()
    patch_session(session)
    entry = _entry(["profile"])
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    coordinator = entry.runtime_data.profile
    assert coordinator.last_update_success

    session.mode = "revoked"
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert not coordinator.last_update_success
    assert any(
        flow["context"]["source"] == "reauth"
        for flow in hass.config_entries.flow.async_progress()
    )


async def test_rate_limit_exhaustion_keeps_last_values_and_recovers(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None]
) -> None:
    session = _AccountSession()
    patch_session(session)
    entry = _entry(["profile"])
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    coordinator = entry.runtime_data.profile
    base_interval = coordinator.update_interval
    registry = er.async_get(hass)
    commits = next(
        e.entity_id
        for e in registry.entities.values()
        if e.unique_id.endswith("_commits_this_month")
    )
    assert hass.states.get(commits).state == "10"

    session.mode = "limited"
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert {"current", "calendar"} <= set(coordinator.errors)
    assert hass.states.get(commits).state == "10"  # the last good value stays
    assert coordinator.update_interval > base_interval  # polling slowed down

    session.mode = "ok"
    coordinator.client.budget._resources.clear()  # the budget reset
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert coordinator.errors == {}
    assert coordinator.update_interval == base_interval
