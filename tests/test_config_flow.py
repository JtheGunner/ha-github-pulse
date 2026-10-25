"""Tests for the config flow."""

from __future__ import annotations

from collections.abc import Callable

from custom_components.github_pulse.config_flow import DOCS_URL
from custom_components.github_pulse.const import (
    CONF_MODULES,
    CONF_OWNER,
    CONF_TOKEN_TYPE,
    DOMAIN,
)
from homeassistant.config_entries import SOURCE_USER, ConfigEntryState
from homeassistant.const import CONF_ACCESS_TOKEN
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from tests.fake_http import FakeResponse, FakeSession

USER_OK = FakeResponse(200, {"login": "Octocat"}, {"X-OAuth-Scopes": "repo"})
GRAPHQL_OK = FakeResponse(200, {"data": {"ok": True}})
GRAPHQL_DENIED = FakeResponse(
    200, {"errors": [{"type": "INSUFFICIENT_SCOPES", "message": "no"}]}
)
BAD_CREDENTIALS = FakeResponse(401, {"message": "Bad credentials"})


async def _start(hass: HomeAssistant) -> str:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["description_placeholders"] == {
        "tokens_url": "https://github.com/settings/tokens",
        "docs_url": DOCS_URL,
    }
    return result["flow_id"]


async def _submit(
    hass: HomeAssistant,
    flow_id: str,
    modules: list[str] | None = None,
    token: str = "ghp_secret",
):
    return await hass.config_entries.flow.async_configure(
        flow_id,
        {
            CONF_ACCESS_TOKEN: token,
            CONF_MODULES: ["profile", "repositories"] if modules is None else modules,
        },
    )


async def test_successful_setup_creates_an_entry(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None]
) -> None:
    patch_session(FakeSession(USER_OK, GRAPHQL_OK, GRAPHQL_OK))

    result = await _submit(hass, await _start(hass))

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Octocat"
    assert result["data"] == {
        CONF_ACCESS_TOKEN: "ghp_secret",
        CONF_OWNER: "Octocat",
        CONF_TOKEN_TYPE: "classic",
        CONF_MODULES: ["profile", "repositories"],
    }
    assert result["result"].unique_id == "octocat"


async def test_only_selected_modules_are_probed(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None]
) -> None:
    session = FakeSession(USER_OK, GRAPHQL_OK)
    patch_session(session)

    result = await _submit(hass, await _start(hass), modules=["profile"])

    assert result["type"] is FlowResultType.CREATE_ENTRY
    rest = [r.url for r in session.requests if r.method == "GET"]
    assert rest == ["https://api.github.com/user"]  # no repository probe
    assert session.requests[1].method == "POST"  # the profile probe


async def test_invalid_token_is_reported(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None]
) -> None:
    patch_session(FakeSession(BAD_CREDENTIALS))

    result = await _submit(hass, await _start(hass))

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_unavailable_module_is_named_in_the_error(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None]
) -> None:
    patch_session(FakeSession(USER_OK, GRAPHQL_OK, GRAPHQL_DENIED))

    result = await _submit(hass, await _start(hass))

    assert result["errors"] == {"base": "module_unavailable"}
    assert result["description_placeholders"]["modules"] == "repositories"


async def test_selecting_no_module_is_rejected(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None]
) -> None:
    session = FakeSession()
    patch_session(session)

    result = await _submit(hass, await _start(hass), modules=[])

    assert result["errors"] == {"base": "no_modules"}
    assert session.requests == []


async def test_rate_limit_is_reported(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None]
) -> None:
    patch_session(
        FakeSession(
            FakeResponse(
                403,
                {"message": "API rate limit exceeded"},
                {"X-RateLimit-Remaining": "0"},
            )
        )
    )

    result = await _submit(hass, await _start(hass))

    assert result["errors"] == {"base": "rate_limit"}


async def test_unexpected_github_error_is_reported_as_connection_problem(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None]
) -> None:
    patch_session(FakeSession(FakeResponse(422, {"message": "Validation Failed"})))

    result = await _submit(hass, await _start(hass))

    assert result["errors"] == {"base": "cannot_connect"}


async def test_token_whitespace_is_stripped(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None]
) -> None:
    patch_session(FakeSession(USER_OK, GRAPHQL_OK))

    result = await _submit(
        hass, await _start(hass), modules=["profile"], token="  ghp_secret \n"
    )

    assert result["data"][CONF_ACCESS_TOKEN] == "ghp_secret"


async def test_same_account_cannot_be_added_twice(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None]
) -> None:
    MockConfigEntry(domain=DOMAIN, unique_id="octocat", data={}).add_to_hass(hass)
    patch_session(FakeSession(USER_OK, GRAPHQL_OK))

    result = await _submit(hass, await _start(hass), modules=["profile"])

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_entry_loads_and_unloads(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None]
) -> None:
    patch_session(FakeSession())
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="octocat",
        data={
            CONF_ACCESS_TOKEN: "ghp_secret",
            CONF_OWNER: "Octocat",
            CONF_TOKEN_TYPE: "classic",
            CONF_MODULES: ["profile"],
        },
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.LOADED
    assert entry.runtime_data.login == "Octocat"
    assert entry.runtime_data.modules == {"profile"}

    assert await hass.config_entries.async_unload(entry.entry_id)
    assert entry.state is ConfigEntryState.NOT_LOADED
