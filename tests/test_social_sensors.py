"""Tests for the optional follower and following sensors."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from custom_components.github_pulse.const import (
    CONF_HISTORY_YEARS,
    CONF_MODULES,
    CONF_OWNER,
    CONF_TOKEN_TYPE,
    DOMAIN,
)
from custom_components.github_pulse.profile_coordinator import GROUP_SOCIAL
from homeassistant.const import CONF_ACCESS_TOKEN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from tests.fake_http import FakeResponse, FakeSession


class _SocialSession(FakeSession):
    def __init__(self) -> None:
        super().__init__()
        self.social_requests: list[dict[str, Any]] = []
        self.social_response = FakeResponse(
            body={
                "data": {
                    "user": {
                        "followers": {"totalCount": 42},
                        "following": {"totalCount": 0},
                    }
                }
            }
        )

    def request(self, method: str, url: str, **kwargs: Any) -> FakeResponse:
        payload = kwargs.get("json") or {}
        if "followers { totalCount }" in payload.get("query", ""):
            self.social_requests.append(payload)
            return self.social_response
        return super().request(method, url, **kwargs)


async def _setup(
    hass: HomeAssistant,
    patch_session: Callable[[FakeSession], None],
    session: _SocialSession,
) -> MockConfigEntry:
    patch_session(session)
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
    return entry


@pytest.mark.parametrize("enabled", ["followers", "following"])
async def test_social_counts_are_fetched_only_when_needed(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None], enabled: str
) -> None:
    session = _SocialSession()
    entry = await _setup(hass, patch_session, session)
    assert GROUP_SOCIAL not in entry.runtime_data.profile.active_groups
    assert not session.social_requests

    registry = er.async_get(hass)
    sensors = {
        key: next(e for e in registry.entities.values() if e.unique_id.endswith(key))
        for key in ("followers", "following")
    }
    assert all(sensor.disabled for sensor in sensors.values())
    registry.async_update_entity(sensors[enabled].entity_id, disabled_by=None)
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    assert len(session.social_requests) == 1
    assert session.social_requests[0]["variables"] == {"login": "octocat"}
    assert hass.states.get(sensors[enabled].entity_id).state == (
        "42" if enabled == "followers" else "0"
    )
    other = "following" if enabled == "followers" else "followers"
    assert hass.states.get(sensors[other].entity_id) is None


async def test_failed_social_group_is_isolated_and_recovers(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None]
) -> None:
    session = _SocialSession()
    good_response = session.social_response
    failed_response = FakeResponse(
        body={
            "data": {"user": None},
            "errors": [{"message": "Could not resolve following"}],
        }
    )
    entry = await _setup(hass, patch_session, session)
    registry = er.async_get(hass)
    sensors = {
        key: next(e for e in registry.entities.values() if e.unique_id.endswith(key))
        for key in ("followers", "following", "commits_this_month")
    }
    for key in ("followers", "following"):
        registry.async_update_entity(sensors[key].entity_id, disabled_by=None)
    session.social_response = failed_response
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    coordinator = entry.runtime_data.profile
    assert GROUP_SOCIAL in coordinator.errors
    assert GROUP_SOCIAL not in coordinator.data
    assert hass.states.get(sensors["followers"].entity_id).state == "unavailable"
    assert hass.states.get(sensors["following"].entity_id).state == "unavailable"
    assert hass.states.get(sensors["commits_this_month"].entity_id).state == "10"

    session.social_response = good_response
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert GROUP_SOCIAL not in coordinator.errors
    assert len(session.social_requests) == 2
    assert hass.states.get(sensors["followers"].entity_id).state == "42"
    assert hass.states.get(sensors["following"].entity_id).state == "0"

    session.social_response = failed_response
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert GROUP_SOCIAL in coordinator.errors
    assert coordinator.last_update_success
    assert hass.states.get(sensors["followers"].entity_id).state == "42"
    assert hass.states.get(sensors["following"].entity_id).state == "0"
    assert hass.states.get(sensors["commits_this_month"].entity_id).state == "10"
