"""Tests for adding a custom query to an entry that is already running."""

from __future__ import annotations

from collections.abc import Callable

from custom_components.github_pulse.const import (
    CONF_MODULES,
    CONF_OWNER,
    CONF_TOKEN_TYPE,
    DOMAIN,
    SUBENTRY_QUERY,
)
from homeassistant.const import CONF_ACCESS_TOKEN
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from tests.fake_http import FakeSession
from tests.test_query_flow import COST, RESULT, _input


async def test_adding_a_query_to_a_running_entry_creates_no_device(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None]
) -> None:
    session = FakeSession()
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
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    devices_before = {d.id for d in dr.async_get(hass).devices}

    session._responses.extend([COST, RESULT])
    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, SUBENTRY_QUERY), context={"source": "user"}
    )
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {"preset": "custom"}
    )
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], _input()
    )
    result = await hass.config_entries.subentries.async_configure(result["flow_id"], {})
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert {d.id for d in dr.async_get(hass).devices} == devices_before
    (subentry_id,) = entry.subentries
    (query,) = [
        e
        for e in er.async_get(hass).entities.values()
        if e.platform == DOMAIN and e.config_subentry_id == subentry_id
    ]
    assert query.device_id is None
