"""Tests for the profile coordinator."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from custom_components.github_pulse.analytics.history import MonthKey
from custom_components.github_pulse.api import GitHubTransportError
from custom_components.github_pulse.const import (
    CONF_HISTORY_YEARS,
    CONF_MODULES,
    CONF_OWNER,
    CONF_TOKEN_TYPE,
    DOMAIN,
)
from custom_components.github_pulse.history_store import HistoryStore
from custom_components.github_pulse.profile_coordinator import (
    GROUP_CURRENT,
    GROUP_HISTORY,
    ProfileCoordinator,
)
from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_ACCESS_TOKEN
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from tests.fake_http import FakeResponse, FakeSession

NOW = datetime(2026, 10, 25, 12, tzinfo=UTC)


def _entry(options: dict[str, object] | None = None) -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        unique_id="octocat",
        data={
            CONF_ACCESS_TOKEN: "token",
            CONF_OWNER: "octocat",
            CONF_TOKEN_TYPE: "classic",
            CONF_MODULES: ["profile"],
        },
        options=options or {CONF_HISTORY_YEARS: 1},
    )


async def _setup(
    hass: HomeAssistant,
    patch_session: Callable[[FakeSession], None],
    session: FakeSession,
    entry: MockConfigEntry,
) -> ProfileCoordinator | None:
    patch_session(session)
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    return (
        entry.runtime_data.profile if entry.state is ConfigEntryState.LOADED else None
    )


async def test_first_refresh_loads_current_periods_and_history(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None]
) -> None:
    session = FakeSession()
    coordinator = await _setup(hass, patch_session, session, _entry())

    assert coordinator is not None
    current = coordinator.data[GROUP_CURRENT]
    assert current.this_month.commits == 10
    assert current.this_month.total(include_restricted=False) == 16
    assert current.this_month.total(include_restricted=True) == 20
    history = coordinator.data[GROUP_HISTORY]
    assert len(history) == 13
    assert MonthKey(2025, 10) in history
    assert coordinator.errors == {}


async def test_the_current_query_asks_for_the_three_comparison_spans(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None]
) -> None:
    session = FakeSession()
    await _setup(hass, patch_session, session, _entry())

    queries = [r.json["query"] for r in session.requests if r.json]
    current = next(q for q in queries if "lastMonth" in q)
    assert "current: contributionsCollection" in current
    assert "lastYear: contributionsCollection" in current


async def test_a_failing_history_group_keeps_the_current_group(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None]
) -> None:
    coordinator = await _setup(hass, patch_session, FakeSession(), _entry())
    assert coordinator is not None
    previous_history = coordinator.data[GROUP_HISTORY]

    with patch.object(
        HistoryStore, "async_refresh", side_effect=GitHubTransportError("down")
    ):
        await coordinator.async_refresh()

    assert coordinator.last_update_success
    assert coordinator.data[GROUP_HISTORY] == previous_history
    assert GROUP_CURRENT in coordinator.data
    assert list(coordinator.errors) == [GROUP_HISTORY]


async def test_bad_credentials_fail_setup_into_reauthentication(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None]
) -> None:
    entry = _entry()
    session = FakeSession(
        FakeResponse(status=401, body={"message": "Bad credentials"}),
        FakeResponse(status=401, body={"message": "Bad credentials"}),
    )

    coordinator = await _setup(hass, patch_session, session, entry)

    assert coordinator is None
    assert entry.state is ConfigEntryState.SETUP_ERROR
    assert any(
        flow["context"]["source"] == "reauth"
        for flow in hass.config_entries.flow.async_progress()
    )


async def test_rate_limited_setup_is_retried_later(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None]
) -> None:
    entry = _entry()
    limited = FakeResponse(
        status=403,
        body={"message": "API rate limit exceeded"},
        headers={"X-RateLimit-Remaining": "0", "Retry-After": "3600"},
    )

    await _setup(hass, patch_session, FakeSession(limited, limited), entry)

    assert entry.state is ConfigEntryState.SETUP_RETRY


@pytest.fixture(autouse=True)
def _freeze(freezer: FrozenDateTimeFactory) -> None:
    freezer.move_to(NOW)
