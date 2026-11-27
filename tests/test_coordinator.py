"""Tests for the base coordinator."""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta
from typing import Any

import pytest
from custom_components.github_pulse.api import (
    GitHubAuthError,
    GitHubClient,
    GitHubForbiddenError,
    GitHubRateLimitError,
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
from homeassistant.helpers import issue_registry as ir
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


def _issue_ids(hass: HomeAssistant) -> set[str]:
    return {
        issue_id for domain, issue_id in ir.async_get(hass).issues if domain == DOMAIN
    }


async def test_rate_limit_failure_raises_a_repair_issue(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None]
) -> None:
    entry = await _entry(hass, patch_session)
    coordinator = _coordinator(
        hass,
        entry,
        {
            "a": _value(1),
            "b": _failing(GitHubRateLimitError("limit", reset_at=1893456000.0)),
        },
        {"a", "b"},
    )

    await coordinator._async_update_data()

    issue = ir.async_get(hass).async_get_issue(
        DOMAIN, f"{entry.entry_id}_test_b_rate_limited"
    )
    assert issue is not None
    assert issue.translation_key == "rate_limited"
    assert issue.is_fixable is False
    assert issue.translation_placeholders is not None
    assert issue.translation_placeholders["group"] == "b"
    assert issue.translation_placeholders["reset"][:4] in {"2029", "2030"}


async def test_rate_limit_without_reset_time_still_raises_an_issue(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None]
) -> None:
    entry = await _entry(hass, patch_session)
    coordinator = _coordinator(
        hass, entry, {"a": _failing(GitHubRateLimitError("limit"))}, {"a"}
    )

    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()

    assert f"{entry.entry_id}_test_a_rate_limited" in _issue_ids(hass)


async def test_forbidden_failure_raises_a_repair_issue(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None]
) -> None:
    entry = await _entry(hass, patch_session)
    coordinator = _coordinator(
        hass,
        entry,
        {"a": _value(1), "b": _failing(GitHubForbiddenError("no scope"))},
        {"a", "b"},
    )

    await coordinator._async_update_data()

    assert f"{entry.entry_id}_test_b_forbidden" in _issue_ids(hass)


async def test_other_failures_raise_no_repair_issue(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None]
) -> None:
    entry = await _entry(hass, patch_session)
    coordinator = _coordinator(
        hass,
        entry,
        {"a": _value(1), "b": _failing(GitHubTransportError("down"))},
        {"a", "b"},
    )

    await coordinator._async_update_data()

    assert _issue_ids(hass) == set()


async def test_repair_issue_clears_after_a_successful_refresh(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None]
) -> None:
    entry = await _entry(hass, patch_session)
    limited = True

    async def flaky() -> int:
        if limited:
            raise GitHubRateLimitError("limit")
        return 2

    coordinator = _coordinator(hass, entry, {"a": _value(1), "b": flaky}, {"a", "b"})
    await coordinator._async_update_data()
    assert f"{entry.entry_id}_test_b_rate_limited" in _issue_ids(hass)

    limited = False
    await coordinator._async_update_data()

    assert _issue_ids(hass) == set()


async def test_switching_error_kind_replaces_the_issue(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None]
) -> None:
    entry = await _entry(hass, patch_session)
    error: GitHubRateLimitError | GitHubForbiddenError = GitHubRateLimitError("limit")

    async def flaky() -> int:
        raise error

    coordinator = _coordinator(hass, entry, {"a": _value(1), "b": flaky}, {"a", "b"})
    await coordinator._async_update_data()
    error = GitHubForbiddenError("no scope")
    await coordinator._async_update_data()

    assert _issue_ids(hass) == {f"{entry.entry_id}_test_b_forbidden"}


async def test_unloading_the_entry_removes_its_repair_issues(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None]
) -> None:
    entry = await _entry(hass, patch_session)
    coordinator = _coordinator(
        hass,
        entry,
        {"a": _value(1), "b": _failing(GitHubRateLimitError("limit"))},
        {"a", "b"},
    )
    await coordinator._async_update_data()
    assert _issue_ids(hass)

    assert await hass.config_entries.async_unload(entry.entry_id)

    assert _issue_ids(hass) == set()


def test_entry_state_import_is_used() -> None:
    assert ConfigEntryState.LOADED
