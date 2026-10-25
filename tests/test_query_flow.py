"""Tests for the custom query subentry flow."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
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
from homeassistant.config_entries import ConfigSubentryData
from homeassistant.const import CONF_ACCESS_TOKEN
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from tests.fake_http import FakeResponse, FakeSession

QUERY = "query { viewer { repositories { totalCount } } }"
COST = FakeResponse(200, {"data": {"pulseCost": {"cost": 1, "nodeCount": 1}}})
RESULT = FakeResponse(200, {"data": {"viewer": {"repositories": {"totalCount": 42}}}})
STATE = "{{ value_json.viewer.repositories.totalCount }}"


def _input(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        CONF_QUERY_NAME: "Repository count",
        CONF_QUERY: QUERY,
        CONF_QUERY_VARIABLES: "",
        CONF_QUERY_INTERVAL: 30,
        CONF_STATE_TEMPLATE: STATE,
        CONF_ATTRIBUTES_TEMPLATE: "",
        CONF_UNIT: "repos",
        CONF_DEVICE_CLASS: "none",
        CONF_STATE_CLASS: "measurement",
    }
    return {**data, **overrides}


async def _setup(
    hass: HomeAssistant,
    patch_session: Callable[[FakeSession], None],
    *responses: FakeResponse,
    subentries: list[ConfigSubentryData] | None = None,
) -> tuple[MockConfigEntry, FakeSession]:
    session = FakeSession(*responses)
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
        subentries_data=subentries or [],
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    return entry, session


async def _submit(
    hass: HomeAssistant, entry: MockConfigEntry, **overrides: Any
) -> dict[str, Any]:
    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, SUBENTRY_QUERY), context={"source": "user"}
    )
    assert result["step_id"] == "user"
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {"preset": "custom"}
    )
    assert result["step_id"] == "details"
    return await hass.config_entries.subentries.async_configure(
        result["flow_id"], _input(**overrides)
    )


async def test_test_run_is_shown_before_saving(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None]
) -> None:
    entry, _ = await _setup(hass, patch_session, COST, RESULT)

    result = await _submit(hass, entry)

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "confirm"
    placeholders = result["description_placeholders"]
    assert placeholders["state"] == "42"
    assert '"totalCount": 42' in placeholders["raw"]


async def test_confirming_creates_the_subentry(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None]
) -> None:
    entry, _ = await _setup(hass, patch_session, COST, RESULT)
    result = await _submit(hass, entry)

    result = await hass.config_entries.subentries.async_configure(result["flow_id"], {})

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Repository count"
    assert result["data"][CONF_QUERY] == QUERY
    assert result["data"][CONF_DEVICE_CLASS] is None
    assert result["data"][CONF_STATE_CLASS] == "measurement"
    assert result["data"][CONF_QUERY_INTERVAL] == 30


@pytest.mark.parametrize(
    "query",
    ["mutation { x }", "subscription { x }", "query { viewer { ", "# c\n mutation{x}"],
)
async def test_non_queries_are_rejected_without_a_request(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None], query: str
) -> None:
    entry, session = await _setup(hass, patch_session)

    result = await _submit(hass, entry, query=query)

    assert result["errors"] == {"base": "invalid_query"}
    assert session.requests == []


@pytest.mark.parametrize(
    ("variables", "query"),
    [
        ("{not json", QUERY),
        ("[1, 2]", QUERY),
        ('{"first": 5}', QUERY),
        (
            "",
            "query($first: Int!) "
            "{ viewer { repositories(first: $first) { totalCount } } }",
        ),
    ],
)
async def test_bad_variables_are_rejected(
    hass: HomeAssistant,
    patch_session: Callable[[FakeSession], None],
    variables: str,
    query: str,
) -> None:
    entry, session = await _setup(hass, patch_session)

    result = await _submit(hass, entry, variables=variables, query=query)

    assert result["errors"] == {"base": "invalid_variables"}
    assert session.requests == []


async def test_helper_variables_fill_declared_variables(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None]
) -> None:
    entry, session = await _setup(hass, patch_session, COST, RESULT)
    query = (
        "query($owner: String!, $start_of_month: DateTime!) "
        "{ user(login: $owner) { contributionsCollection(from: $start_of_month) "
        "{ totalCommitContributions } } }"
    )

    result = await _submit(hass, entry, query=query)

    assert result["step_id"] == "confirm"
    sent = session.requests[0].json["variables"]
    assert sent["owner"] == "octocat"
    assert (
        sent["start_of_month"].endswith("T00:00:00Z") or "T" in sent["start_of_month"]
    )


async def test_an_expensive_query_is_rejected_with_its_cost(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None]
) -> None:
    expensive = FakeResponse(
        200, {"data": {"pulseCost": {"cost": 120, "nodeCount": 9}}}
    )
    entry, _ = await _setup(hass, patch_session, expensive)

    result = await _submit(hass, entry)

    assert result["errors"] == {"base": "too_expensive"}
    assert "120" in result["description_placeholders"]["detail"]


async def test_a_too_short_interval_names_the_minimum(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None]
) -> None:
    pricey = FakeResponse(200, {"data": {"pulseCost": {"cost": 50, "nodeCount": 9}}})
    entry, _ = await _setup(hass, patch_session, pricey)

    result = await _submit(hass, entry, interval=5)

    assert result["errors"] == {"base": "interval_too_short"}
    assert result["description_placeholders"]["detail"] == "6"


async def test_a_failing_template_is_reported(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None]
) -> None:
    entry, _ = await _setup(hass, patch_session, COST, RESULT)

    result = await _submit(hass, entry, state_template="{{ value_json.nope.deeper }}")

    assert result["errors"] == {"base": "template_error"}


async def test_a_github_error_during_the_test_run_is_reported(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None]
) -> None:
    entry, _ = await _setup(
        hass, patch_session, FakeResponse(401, {"message": "Bad credentials"})
    )

    result = await _submit(hass, entry)

    assert result["errors"] == {"base": "invalid_auth"}


async def test_a_name_can_only_be_used_once(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None]
) -> None:
    existing = ConfigSubentryData(
        subentry_type=SUBENTRY_QUERY,
        title="Repository count",
        unique_id="repository count",
        data=_input(),
    )
    entry, _ = await _setup(hass, patch_session, subentries=[existing])

    result = await _submit(hass, entry)

    assert result["errors"] == {"base": "name_in_use"}


async def test_reconfigure_validates_again_and_updates(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None]
) -> None:
    existing = ConfigSubentryData(
        subentry_type=SUBENTRY_QUERY,
        title="Repository count",
        unique_id="repository count",
        data=_input(),
    )
    entry, _ = await _setup(
        hass, patch_session, RESULT, COST, RESULT, subentries=[existing]
    )
    subentry_id = next(iter(entry.subentries))

    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, SUBENTRY_QUERY),
        context={"source": "reconfigure", "subentry_id": subentry_id},
    )
    assert result["step_id"] == "reconfigure"
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], _input(unit="projects")
    )
    assert result["step_id"] == "confirm"
    result = await hass.config_entries.subentries.async_configure(result["flow_id"], {})

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.subentries[subentry_id].data[CONF_UNIT] == "projects"


async def test_a_query_subentry_does_not_disturb_the_repository_platforms(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None]
) -> None:
    existing = ConfigSubentryData(
        subentry_type=SUBENTRY_QUERY,
        title="Repository count",
        unique_id="repository count",
        data=_input(),
    )

    entry, _ = await _setup(hass, patch_session, subentries=[existing])

    assert entry.state.value == "loaded"


async def test_a_preset_prefills_the_details_form(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None]
) -> None:
    entry, _ = await _setup(hass, patch_session)
    result = await hass.config_entries.subentries.async_init(
        (entry.entry_id, SUBENTRY_QUERY), context={"source": "user"}
    )

    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], {"preset": "followers"}
    )

    assert result["step_id"] == "details"
    defaults = {
        str(key): key.default() for key in result["data_schema"].schema if key.default
    }
    assert defaults[CONF_QUERY_NAME] == "Followers"
    assert "followers" in defaults[CONF_QUERY]
    assert defaults[CONF_UNIT] == "followers"
