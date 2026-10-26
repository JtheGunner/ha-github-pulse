"""Tests for the sensor of a custom query."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from custom_components.github_pulse.const import (
    CONF_ATTRIBUTES_TEMPLATE,
    CONF_DEVICE_CLASS,
    CONF_MODULES,
    CONF_OWNER,
    CONF_QUERY,
    CONF_QUERY_INTERVAL,
    CONF_QUERY_NAME,
    CONF_QUERY_VARIABLES,
    CONF_STATE_CLASS,
    CONF_STATE_TEMPLATE,
    CONF_TOKEN_TYPE,
    CONF_UNIT,
    DOMAIN,
    SUBENTRY_QUERY,
)
from homeassistant.config_entries import ConfigEntryState, ConfigSubentryData
from homeassistant.const import CONF_ACCESS_TOKEN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from tests.fake_http import FakeResponse, FakeSession

RESULT = FakeResponse(
    200,
    {"data": {"viewer": {"login": "octocat", "repositories": {"totalCount": 42}}}},
)


def _data(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        CONF_QUERY_NAME: "Repository count",
        CONF_QUERY: "query { viewer { login repositories { totalCount } } }",
        CONF_QUERY_VARIABLES: "",
        CONF_QUERY_INTERVAL: 30,
        CONF_STATE_TEMPLATE: "{{ value_json.viewer.repositories.totalCount }}",
        CONF_ATTRIBUTES_TEMPLATE: "{{ {'login': value_json.viewer.login} }}",
        CONF_UNIT: "repos",
        CONF_DEVICE_CLASS: None,
        CONF_STATE_CLASS: "measurement",
    }
    return {**data, **overrides}


async def _setup(
    hass: HomeAssistant,
    patch_session: Callable[[FakeSession], None],
    response: FakeResponse,
    **overrides: Any,
) -> MockConfigEntry:
    patch_session(FakeSession(response))
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
                subentry_type=SUBENTRY_QUERY,
                title="Repository count",
                unique_id="repository count",
                data=_data(**overrides),
            )
        ],
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _entity_id(hass: HomeAssistant) -> str:
    registry = er.async_get(hass)
    entities = [e for e in registry.entities.values() if e.platform == DOMAIN]
    assert len(entities) == 1
    return entities[0].entity_id


async def test_the_sensor_shows_the_rendered_result(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None]
) -> None:
    await _setup(hass, patch_session, RESULT)

    state = hass.states.get(_entity_id(hass))

    assert state is not None
    assert state.state == "42"
    assert state.name == "Repository count"
    assert state.attributes["login"] == "octocat"
    assert state.attributes["unit_of_measurement"] == "repos"
    assert state.attributes["state_class"] == "measurement"


async def test_device_class_is_applied(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None]
) -> None:
    await _setup(
        hass,
        patch_session,
        RESULT,
        device_class="data_size",
        unit="MB",
        state_template="{{ 5 }}",
    )

    state = hass.states.get(_entity_id(hass))

    assert state is not None
    assert state.attributes["device_class"] == "data_size"


async def test_a_failing_template_makes_the_sensor_unavailable_not_the_entry(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None]
) -> None:
    entry = await _setup(
        hass, patch_session, RESULT, state_template="{{ value_json.nope.deeper }}"
    )

    state = hass.states.get(_entity_id(hass))

    assert entry.state is ConfigEntryState.LOADED
    assert state is not None
    assert state.state == "unavailable"


async def test_a_github_error_makes_the_sensor_unavailable_not_the_entry(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None]
) -> None:
    entry = await _setup(
        hass, patch_session, FakeResponse(422, {"message": "Validation Failed"})
    )

    state = hass.states.get(_entity_id(hass))

    assert entry.state is ConfigEntryState.LOADED
    assert state is not None
    assert state.state == "unavailable"


async def test_a_saved_mutation_is_never_sent(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None]
) -> None:
    session = FakeSession(RESULT)
    patch_session(session)
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
                subentry_type=SUBENTRY_QUERY,
                title="Evil",
                unique_id="evil",
                data=_data(**{CONF_QUERY: "mutation { addStar { id } }"}),
            )
        ],
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)

    assert session.requests == []


async def _setup_profile_with_query(
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
        subentries_data=[
            ConfigSubentryData(
                subentry_type=SUBENTRY_QUERY,
                title="Repository count",
                unique_id="repository count",
                data=_data(),
            )
        ],
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _account_device(hass: HomeAssistant, entry: MockConfigEntry) -> dr.DeviceEntry:
    device = dr.async_get(hass).async_get_device_by_identifier(
        (DOMAIN, entry.entry_id), entry.entry_id
    )
    assert device is not None
    return device


async def test_a_query_leaves_the_account_device_to_the_profile_sensors(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None]
) -> None:
    entry = await _setup_profile_with_query(hass, patch_session)

    device = _account_device(hass, entry)
    assert device.config_subentry_id is None
    registry = er.async_get(hass)
    (query,) = [
        e
        for e in registry.entities.values()
        if e.platform == DOMAIN and "_query_" in e.unique_id
    ]
    assert query.device_id is None
    profile = [
        e
        for e in registry.entities.values()
        if e.platform == DOMAIN and e.config_subentry_id is None
    ]
    assert profile
    assert all(e.device_id == device.id for e in profile)


async def test_an_account_device_moved_into_a_subentry_is_released_on_setup(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None]
) -> None:
    entry = await _setup_profile_with_query(hass, patch_session)
    query_id = next(iter(entry.subentries))
    device = _account_device(hass, entry)
    dr.async_get(hass).async_update_device(
        device.id,
        new_config_entry_id=entry.entry_id,
        new_config_subentry_id=query_id,
    )
    assert _account_device(hass, entry).config_subentry_id == query_id

    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    assert _account_device(hass, entry).config_subentry_id is None
