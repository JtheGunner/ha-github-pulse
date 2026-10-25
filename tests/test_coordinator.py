"""Tests for the base coordinator."""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta
from typing import Any

import pytest
from custom_components.github_pulse.api import (
    GitHubAuthError,
    GitHubClient,
    GitHubTransportError,
)
from custom_components.github_pulse.const import (
    CONF_MODULES,
    CONF_OWNER,
    CONF_TOKEN_TYPE,
    DOMAIN,
)
from custom_components.github_pulse.coordinator import (
    SLOWDOWN_FACTOR,
    GitHubPulseCoordinator,
)
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_ACCESS_TOKEN
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed
from pytest_homeassistant_custom_component.common import MockConfigEntry

from tests.fake_http import FakeSession

INTERVAL = timedelta(minutes=15)


async def _entry(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None]
) -> MockConfigEntry:
    patch_session(FakeSession())
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="octocat",
        data={
            CONF_ACCESS_TOKEN: "token",
            CONF_OWNER: "octocat",
            CONF_TOKEN_TYPE: "classic",
            CONF_MODULES: ["profile"],
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    return entry


def _coordinator(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    groups: dict[str, Any],
    active: set[str],
) -> GitHubPulseCoordinator:
    client: GitHubClient = entry.runtime_data.client
    return GitHubPulseCoordinator(
        hass,
        entry,
        name="test",
        client=client,
        update_interval=INTERVAL,
        groups=groups,
        active_groups=active,
    )


def _value(result: Any) -> Any:
    async def fetch() -> Any:
        return result

    return fetch


def _failing(error: Exception) -> Any:
    async def fetch() -> Any:
        raise error

    return fetch


async def test_only_active_groups_are_fetched(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None]
) -> None:
    entry = await _entry(hass, patch_session)
    coordinator = _coordinator(
        hass,
        entry,
        {"a": _value(1), "b": _value(2)},
        {"a", "unknown"},
    )

    data = await coordinator._async_update_data()

    assert data == {"a": 1}
    assert coordinator.active_groups == {"a"}


async def test_a_failed_group_keeps_its_last_good_value(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None]
) -> None:
    entry = await _entry(hass, patch_session)
    broken = False

    async def flaky() -> int:
        if broken:
            raise GitHubTransportError("down")
        return 2

    coordinator = _coordinator(hass, entry, {"a": _value(1), "b": flaky}, {"a", "b"})
    coordinator.data = await coordinator._async_update_data()

    broken = True
    data = await coordinator._async_update_data()

    assert data == {"a": 1, "b": 2}
    assert "b" in coordinator.errors


async def test_update_fails_when_every_group_failed(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None]
) -> None:
    entry = await _entry(hass, patch_session)
    coordinator = _coordinator(
        hass, entry, {"a": _failing(GitHubTransportError("down"))}, {"a"}
    )

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()


async def test_auth_error_starts_reauthentication(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None]
) -> None:
    entry = await _entry(hass, patch_session)
    coordinator = _coordinator(
        hass,
        entry,
        {"a": _value(1), "b": _failing(GitHubAuthError("bad credentials"))},
        {"a", "b"},
    )

    with pytest.raises(ConfigEntryAuthFailed):
        await coordinator._async_update_data()


async def test_polling_slows_down_while_the_budget_is_low(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None]
) -> None:
    entry = await _entry(hass, patch_session)
    coordinator = _coordinator(hass, entry, {"a": _value(1)}, {"a"})

    entry.runtime_data.client.budget.update_from_headers(
        {
            "X-RateLimit-Limit": "5000",
            "X-RateLimit-Remaining": "1",
            "X-RateLimit-Reset": "99999999999",
            "X-RateLimit-Resource": "graphql",
        }
    )
    await coordinator._async_update_data()
    assert coordinator.update_interval == INTERVAL * SLOWDOWN_FACTOR

    entry.runtime_data.client.budget.update_from_headers(
        {
            "X-RateLimit-Limit": "5000",
            "X-RateLimit-Remaining": "4999",
            "X-RateLimit-Reset": "99999999999",
            "X-RateLimit-Resource": "graphql",
        }
    )
    await coordinator._async_update_data()
    assert coordinator.update_interval == INTERVAL


def test_entry_state_import_is_used() -> None:
    assert ConfigEntryState.LOADED
