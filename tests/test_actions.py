"""Tests for the Actions coordinator and entities."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import pytest
from custom_components.github_pulse.actions_coordinator import (
    GROUP_RUNS,
    actions_repositories,
)
from custom_components.github_pulse.const import (
    CONF_ACTIONS,
    CONF_MODULES,
    CONF_OWNER,
    CONF_REPOSITORY,
    CONF_TOKEN_TYPE,
    DOMAIN,
    SUBENTRY_REPOSITORY,
)
from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import ConfigSubentryData
from homeassistant.const import CONF_ACCESS_TOKEN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from tests.fake_http import FakeResponse, FakeSession
from tests.test_repository_fetch import RAW

NOW = datetime(2026, 10, 25, 12, tzinfo=UTC)


def _run(
    run_id: int, status: str, conclusion: str | None, created: str
) -> dict[str, Any]:
    return {
        "id": run_id,
        "name": "CI",
        "head_branch": "main",
        "status": status,
        "conclusion": conclusion,
        "created_at": created,
        "run_started_at": created,
        "updated_at": created,
        "html_url": f"https://github.com/o/r/actions/runs/{run_id}",
    }


RUNS = {
    "workflow_runs": [
        _run(3, "in_progress", None, "2026-10-25T11:00:00Z"),
        _run(2, "completed", "failure", "2026-10-25T10:00:00Z"),
        _run(1, "completed", "success", "2026-10-24T10:00:00Z"),
    ]
}


class _Session(FakeSession):
    """Answer the repository query and the workflow-run listings."""

    def request(self, method: str, url: str, **kwargs: Any) -> FakeResponse:
        if "/actions/runs" in url:
            if "hidden" in url:
                return FakeResponse(status=404, body={"message": "Not Found"})
            return FakeResponse(body=RUNS)
        return FakeResponse(body={"data": {"r0": RAW, "r1": RAW, "r2": RAW}})


def _subentry(name: str, *, actions: bool) -> ConfigSubentryData:
    return ConfigSubentryData(
        data={CONF_REPOSITORY: name, CONF_ACTIONS: actions},
        subentry_type=SUBENTRY_REPOSITORY,
        title=name,
        unique_id=name.lower(),
    )


@pytest.fixture(autouse=True)
def _freeze(freezer: FrozenDateTimeFactory) -> None:
    freezer.move_to(NOW)


async def _setup(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None]
) -> MockConfigEntry:
    patch_session(_Session())
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="octocat",
        data={
            CONF_ACCESS_TOKEN: "token",
            CONF_OWNER: "octocat",
            CONF_TOKEN_TYPE: "classic",
            CONF_MODULES: ["repositories"],
        },
        subentries_data=[
            _subentry("o/with-actions", actions=True),
            _subentry("o/hidden-actions", actions=True),
            _subentry("o/without", actions=False),
        ],
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _state(hass: HomeAssistant, repo: str, key: str) -> Any:
    registry = er.async_get(hass)
    entity = next(
        (
            e
            for e in registry.entities.values()
            if e.unique_id.endswith(f"{repo}_{key}")
        ),
        None,
    )
    return None if entity is None else hass.states.get(entity.entity_id)


async def test_only_repositories_with_the_toggle_are_tracked(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None]
) -> None:
    entry = await _setup(hass, patch_session)

    assert actions_repositories(entry) == ["o/hidden-actions", "o/with-actions"]
    assert _state(hass, "o/without", "actions_last_result") is None


async def test_default_entities_report_the_latest_state(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None]
) -> None:
    await _setup(hass, patch_session)

    assert _state(hass, "o/with-actions", "actions_last_result").state == "failure"
    assert _state(hass, "o/with-actions", "actions_running").state == "on"


async def test_optional_entities_are_disabled_until_enabled(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None]
) -> None:
    entry = await _setup(hass, patch_session)
    assert _state(hass, "o/with-actions", "actions_runs_today") is None
    registry = er.async_get(hass)
    for key in ("actions_runs_today", "actions_failure_rate_30d"):
        entity = next(
            e
            for e in registry.entities.values()
            if e.unique_id.endswith(f"o/with-actions_{key}")
        )
        registry.async_update_entity(entity.entity_id, disabled_by=None)
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    assert _state(hass, "o/with-actions", "actions_runs_today").state == "2"
    assert _state(hass, "o/with-actions", "actions_failure_rate_30d").state == "50.0"


async def test_a_repository_without_actions_access_is_unavailable(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None]
) -> None:
    entry = await _setup(hass, patch_session)

    assert (
        _state(hass, "o/hidden-actions", "actions_last_result").state == "unavailable"
    )
    assert entry.runtime_data.actions.data[GROUP_RUNS]["o/hidden-actions"] is None
    assert _state(hass, "o/with-actions", "actions_last_result").state == "failure"
