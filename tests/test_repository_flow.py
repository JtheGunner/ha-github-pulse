"""Tests for the repository subentry flow."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from custom_components.github_pulse.api.repository import parse_repository_name
from custom_components.github_pulse.const import (
    CONF_ACTIONS,
    CONF_MODULES,
    CONF_OWNER,
    CONF_REPOSITORY,
    CONF_TOKEN_TYPE,
    DOMAIN,
    SUBENTRY_REPOSITORY,
)
from homeassistant.config_entries import ConfigSubentryData
from homeassistant.const import CONF_ACCESS_TOKEN
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from tests.fake_http import FakeResponse, FakeSession

REPO = FakeResponse(
    200,
    {
        "full_name": "Octocat/Hello-World",
        "default_branch": "main",
        "private": False,
        "archived": False,
    },
)
RUNS = FakeResponse(200, {"workflow_runs": []})
NOT_FOUND = FakeResponse(404, {"message": "Not Found"})
FORBIDDEN = FakeResponse(403, {"message": "Resource not accessible"})
BAD_CREDENTIALS = FakeResponse(401, {"message": "Bad credentials"})


async def _setup(
    hass: HomeAssistant,
    patch_session: Callable[[FakeSession], None],
    *responses: FakeResponse,
    modules: list[str] | None = None,
    subentries: list[ConfigSubentryData] | None = None,
) -> MockConfigEntry:
    patch_session(FakeSession(*responses))
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="octocat",
        data={
            CONF_ACCESS_TOKEN: "token",
            CONF_OWNER: "octocat",
            CONF_TOKEN_TYPE: "classic",
            CONF_MODULES: modules or ["repositories"],
        },
        subentries_data=subentries or [],
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    return entry


async def _start(hass: HomeAssistant, entry: MockConfigEntry) -> dict[str, Any]:
    return await hass.config_entries.subentries.async_init(
        (entry.entry_id, SUBENTRY_REPOSITORY), context={"source": "user"}
    )


async def _submit(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    repository: str,
    *,
    actions: bool = False,
) -> dict[str, Any]:
    result = await _start(hass, entry)
    return await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {CONF_REPOSITORY: repository, CONF_ACTIONS: actions},
    )


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("octocat/Hello-World", ("octocat", "Hello-World")),
        ("  octocat/hello.world  ", ("octocat", "hello.world")),
        ("https://github.com/octocat/hello", ("octocat", "hello")),
        ("octocat/hello.git", ("octocat", "hello")),
    ],
)
def test_parse_accepts_common_spellings(value: str, expected: tuple[str, str]) -> None:
    assert parse_repository_name(value) == expected


@pytest.mark.parametrize("value", ["", "octocat", "a/b/c", "a b/c", "/x", "a/"])
def test_parse_rejects_everything_else(value: str) -> None:
    with pytest.raises(ValueError, match="owner/name"):
        parse_repository_name(value)


async def test_a_repository_is_added_with_its_canonical_name(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None]
) -> None:
    entry = await _setup(hass, patch_session, REPO)

    result = await _submit(hass, entry, "octocat/hello-world")

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Octocat/Hello-World"
    (subentry,) = entry.subentries.values()
    assert subentry.data == {
        CONF_REPOSITORY: "Octocat/Hello-World",
        CONF_ACTIONS: False,
    }
    assert subentry.unique_id == "octocat/hello-world"


async def test_actions_access_is_checked_when_requested(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None]
) -> None:
    entry = await _setup(hass, patch_session, REPO, RUNS)

    result = await _submit(hass, entry, "octocat/Hello-World", actions=True)

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert next(iter(entry.subentries.values())).data[CONF_ACTIONS] is True


async def test_missing_actions_permission_is_reported(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None]
) -> None:
    entry = await _setup(hass, patch_session, REPO, FORBIDDEN)

    result = await _submit(hass, entry, "octocat/Hello-World", actions=True)

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "actions_no_access"}
    assert not entry.subentries


@pytest.mark.parametrize(
    ("response", "error"),
    [
        (NOT_FOUND, "not_found"),
        (FORBIDDEN, "no_access"),
        (BAD_CREDENTIALS, "invalid_auth"),
    ],
)
async def test_lookup_failures_are_reported(
    hass: HomeAssistant,
    patch_session: Callable[[FakeSession], None],
    response: FakeResponse,
    error: str,
) -> None:
    entry = await _setup(hass, patch_session, response)

    result = await _submit(hass, entry, "octocat/missing")

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": error}


async def test_a_malformed_name_does_not_reach_github(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None]
) -> None:
    entry = await _setup(hass, patch_session)

    result = await _submit(hass, entry, "not a repository")

    assert result["errors"] == {"base": "invalid_name"}


async def test_a_duplicate_is_aborted_case_insensitively(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None]
) -> None:
    existing = ConfigSubentryData(
        data={CONF_REPOSITORY: "Octocat/Hello-World", CONF_ACTIONS: False},
        subentry_type=SUBENTRY_REPOSITORY,
        title="Octocat/Hello-World",
        unique_id="octocat/hello-world",
    )
    entry = await _setup(hass, patch_session, REPO, subentries=[existing])

    result = await _submit(hass, entry, "OCTOCAT/hello-world")

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert len(entry.subentries) == 1


async def test_the_flow_needs_the_repositories_module(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None]
) -> None:
    entry = await _setup(hass, patch_session, modules=["profile"])

    result = await _start(hass, entry)

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "module_disabled"


async def test_the_actions_toggle_can_be_changed(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None]
) -> None:
    existing = ConfigSubentryData(
        data={CONF_REPOSITORY: "Octocat/Hello-World", CONF_ACTIONS: False},
        subentry_type=SUBENTRY_REPOSITORY,
        title="Octocat/Hello-World",
        unique_id="octocat/hello-world",
    )
    entry = await _setup(hass, patch_session, RUNS, subentries=[existing])
    subentry_id = next(iter(entry.subentries))

    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, SUBENTRY_REPOSITORY),
        context={"source": "reconfigure", "subentry_id": subentry_id},
    )
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {CONF_ACTIONS: True}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.subentries[subentry_id].data[CONF_ACTIONS] is True


async def test_adding_a_repository_reloads_the_entry(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None]
) -> None:
    entry = await _setup(hass, patch_session, REPO)
    runtime_before = entry.runtime_data

    await _submit(hass, entry, "octocat/Hello-World")
    await hass.async_block_till_done()

    assert entry.runtime_data is not runtime_before
