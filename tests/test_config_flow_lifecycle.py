"""Tests for reauthentication, reconfiguration and the options flow."""

from __future__ import annotations

from collections.abc import Callable

from custom_components.github_pulse.const import (
    CONF_CONTRIBUTION_TIME_ZONE,
    CONF_HISTORY_YEARS,
    CONF_INCLUDE_RESTRICTED,
    CONF_LANGUAGE_WEIGHTING,
    CONF_MODULES,
    CONF_OWNER,
    CONF_PROFILE_INTERVAL,
    CONF_REPOSITORY_INTERVAL,
    CONF_TOKEN_TYPE,
    DOMAIN,
)
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_ACCESS_TOKEN
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from tests.fake_http import FakeResponse, FakeSession

USER_OK = FakeResponse(200, {"login": "octocat"}, {"X-OAuth-Scopes": "repo"})
OTHER_USER = FakeResponse(200, {"login": "mallory"}, {"X-OAuth-Scopes": "repo"})
GRAPHQL_OK = FakeResponse(200, {"data": {"ok": True}})
GRAPHQL_DENIED = FakeResponse(
    200, {"errors": [{"type": "INSUFFICIENT_SCOPES", "message": "no"}]}
)
BAD_CREDENTIALS = FakeResponse(401, {"message": "Bad credentials"})


def _entry(hass: HomeAssistant, modules: list[str] | None = None) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="octocat",
        data={
            CONF_ACCESS_TOKEN: "ghp_old",
            CONF_OWNER: "octocat",
            CONF_TOKEN_TYPE: "classic",
            CONF_MODULES: modules or ["profile"],
        },
    )
    entry.add_to_hass(hass)
    return entry


async def test_reauth_replaces_the_token(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None]
) -> None:
    patch_session(FakeSession(USER_OK, GRAPHQL_OK))
    entry = _entry(hass)

    result = await entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_ACCESS_TOKEN: " ghp_new "}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_ACCESS_TOKEN] == "ghp_new"
    assert entry.data[CONF_OWNER] == "octocat"


async def test_reauth_rejects_a_token_of_another_account(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None]
) -> None:
    patch_session(FakeSession(OTHER_USER))
    entry = _entry(hass)

    result = await entry.start_reauth_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_ACCESS_TOKEN: "ghp_new"}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "wrong_account"}
    assert entry.data[CONF_ACCESS_TOKEN] == "ghp_old"


async def test_reauth_reports_an_invalid_token(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None]
) -> None:
    patch_session(FakeSession(BAD_CREDENTIALS))
    entry = _entry(hass)

    result = await entry.start_reauth_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_ACCESS_TOKEN: "ghp_bad"}
    )

    assert result["errors"] == {"base": "invalid_auth"}


async def test_reconfigure_changes_the_modules(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None]
) -> None:
    patch_session(FakeSession(USER_OK, GRAPHQL_OK, GRAPHQL_OK))
    entry = _entry(hass)

    result = await entry.start_reconfigure_flow(hass)
    assert result["step_id"] == "reconfigure"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_MODULES: ["profile", "repositories"]}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data[CONF_MODULES] == ["profile", "repositories"]
    assert entry.data[CONF_ACCESS_TOKEN] == "ghp_old"


async def test_reconfigure_rejects_a_module_the_token_cannot_serve(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None]
) -> None:
    patch_session(FakeSession(USER_OK, GRAPHQL_DENIED))
    entry = _entry(hass)

    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_MODULES: ["repositories"]}
    )

    assert result["errors"] == {"base": "module_unavailable"}
    assert entry.data[CONF_MODULES] == ["profile"]


async def test_reconfigure_requires_a_module(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None]
) -> None:
    patch_session(FakeSession())
    entry = _entry(hass)

    result = await entry.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_MODULES: []}
    )

    assert result["errors"] == {"base": "no_modules"}


VALID_OPTIONS = {
    CONF_PROFILE_INTERVAL: 30,
    CONF_REPOSITORY_INTERVAL: 60,
    CONF_HISTORY_YEARS: 5,
    CONF_CONTRIBUTION_TIME_ZONE: "Europe/Zurich",
    CONF_INCLUDE_RESTRICTED: False,
    CONF_LANGUAGE_WEIGHTING: "repo_count",
}


async def test_options_are_saved(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None]
) -> None:
    patch_session(FakeSession())
    entry = _entry(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["step_id"] == "init"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], VALID_OPTIONS
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == VALID_OPTIONS
    assert entry.state is ConfigEntryState.LOADED


async def test_options_reject_an_unknown_time_zone(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None]
) -> None:
    patch_session(FakeSession())
    entry = _entry(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {**VALID_OPTIONS, CONF_CONTRIBUTION_TIME_ZONE: "Mars/Base"}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_CONTRIBUTION_TIME_ZONE: "invalid_time_zone"}
    assert entry.options == {}
