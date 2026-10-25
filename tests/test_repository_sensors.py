"""State and attribute snapshots of the repository sensors."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import pytest
from custom_components.github_pulse.const import (
    CONF_ACTIONS,
    CONF_MODULES,
    CONF_OWNER,
    CONF_REPOSITORY,
    CONF_TOKEN_TYPE,
    DOMAIN,
    SUBENTRY_REPOSITORY,
)
from custom_components.github_pulse.sensor_repository import REPOSITORY_SENSORS
from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import ConfigSubentryData
from homeassistant.const import CONF_ACCESS_TOKEN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from tests.fake_http import FakeResponse, FakeSession
from tests.test_repository_fetch import RAW

NOW = datetime(2026, 10, 25, 12, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _freeze(freezer: FrozenDateTimeFactory) -> None:
    freezer.move_to(NOW)


class _Session(FakeSession):
    """Answer the batched repository query; the second repo is unreadable."""

    def request(self, method: str, url: str, **kwargs: Any) -> FakeResponse:
        if "/releases" in url:
            return FakeResponse(
                body=[{"assets": [{"download_count": 100}, {"download_count": 20}]}]
            )
        return FakeResponse(body={"data": {"r0": RAW, "r1": None}})


async def _setup(
    hass: HomeAssistant,
    patch_session: Callable[[FakeSession], None],
    *,
    names: tuple[str, ...] = ("Octocat/Hello-World", "octocat/hidden"),
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
            ConfigSubentryData(
                data={CONF_REPOSITORY: name, CONF_ACTIONS: False},
                subentry_type=SUBENTRY_REPOSITORY,
                title=name,
                unique_id=name.lower(),
            )
            for name in names
        ],
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _state(hass: HomeAssistant, repo: str, key: str) -> Any:
    registry = er.async_get(hass)
    unique_id = next(
        e.unique_id
        for e in registry.entities.values()
        if e.unique_id.endswith(f"{repo.lower()}_{key}")
    )
    entity_id = registry.async_get_entity_id("sensor", DOMAIN, unique_id)
    return hass.states.get(entity_id)


async def test_default_sensors_report_the_fixture(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None]
) -> None:
    await _setup(hass, patch_session)
    repo = "Octocat/Hello-World"

    assert _state(hass, repo, "stars").state == "42"
    assert _state(hass, repo, "forks").state == "7"
    assert _state(hass, repo, "open_issues").state == "3"
    assert _state(hass, repo, "open_pull_requests").state == "2"
    release = _state(hass, repo, "latest_release")
    assert release.state == "v1.2.0"
    assert release.attributes["url"].endswith("/releases/tag/v1.2.0")
    assert release.attributes["prerelease"] is False
    assert _state(hass, repo, "ci_state").state == "failure"


async def test_optional_sensors_are_disabled_by_default(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None]
) -> None:
    await _setup(hass, patch_session, names=("Octocat/Hello-World",))
    registry = er.async_get(hass)

    for description in REPOSITORY_SENSORS:
        entry = next(
            e
            for e in registry.entities.values()
            if e.unique_id.endswith(f"hello-world_{description.key}")
        )
        expected = (
            None
            if description.entity_registry_enabled_default
            else er.RegistryEntryDisabler.INTEGRATION
        )
        assert entry.disabled_by is expected, description.key


async def test_each_repository_gets_its_own_device_and_subentry_link(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None]
) -> None:
    entry = await _setup(hass, patch_session)
    devices = dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)

    assert {d.name for d in devices} == {"Octocat/Hello-World", "octocat/hidden"}
    registry = er.async_get(hass)
    subentry_ids = {
        e.config_subentry_id
        for e in registry.entities.values()
        if e.config_entry_id == entry.entry_id
    }
    assert subentry_ids == set(entry.subentries)


async def test_an_unreadable_repository_is_unavailable_not_broken(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None]
) -> None:
    await _setup(hass, patch_session)

    assert _state(hass, "octocat/hidden", "stars").state == "unavailable"
    assert _state(hass, "Octocat/Hello-World", "stars").state == "42"


async def test_enabling_the_downloads_sensor_fetches_that_group(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None]
) -> None:
    entry = await _setup(hass, patch_session, names=("Octocat/Hello-World",))
    registry = er.async_get(hass)
    total = next(
        e for e in registry.entities.values() if e.unique_id.endswith("total_downloads")
    )
    days = next(
        e
        for e in registry.entities.values()
        if e.unique_id.endswith("days_since_last_commit")
    )
    registry.async_update_entity(total.entity_id, disabled_by=None)
    registry.async_update_entity(days.entity_id, disabled_by=None)
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get(total.entity_id).state == "120"
    assert hass.states.get(days.entity_id).state == "1"
