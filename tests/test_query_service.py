"""Tests for the query service."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

import pytest
from custom_components.github_pulse import query_service
from custom_components.github_pulse.const import (
    CONF_MODULES,
    CONF_OWNER,
    CONF_TOKEN_TYPE,
    DOMAIN,
)
from homeassistant.const import CONF_ACCESS_TOKEN
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from tests.fake_http import FakeResponse, FakeSession

QUERY = "query { viewer { login } }"
COST = FakeResponse(200, {"data": {"pulseCost": {"cost": 1, "nodeCount": 1}}})
RESULT = FakeResponse(200, {"data": {"viewer": {"login": "octocat"}}})


async def _setup(
    hass: HomeAssistant,
    patch_session: Callable[[FakeSession], None],
    *responses: FakeResponse,
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
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    return entry, session


async def _call(hass: HomeAssistant, **data: Any) -> dict[str, Any]:
    return await hass.services.async_call(  # type: ignore[no-any-return]
        DOMAIN, "query", data, blocking=True, return_response=True
    )


async def test_returns_data_errors_and_cost(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None]
) -> None:
    _, session = await _setup(hass, patch_session, COST, RESULT)

    response = await _call(hass, query=QUERY)

    assert response == {
        "data": {"viewer": {"login": "octocat"}},
        "errors": [],
        "cost": 1,
    }
    assert "dryRun" in session.requests[0].json["query"]
    assert session.requests[1].json["query"] == QUERY


async def test_variables_and_helpers_are_filled_in(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None]
) -> None:
    _, session = await _setup(hass, patch_session, COST, RESULT)

    await _call(
        hass,
        query="query($owner: String!, $first: Int!) "
        "{ user(login: $owner) { repositories(first: $first) { totalCount } } }",
        variables={"first": 3},
    )

    assert session.requests[1].json["variables"] == {"owner": "octocat", "first": 3}


@pytest.mark.parametrize(
    "query", ["mutation { x }", "subscription { x }", "query {", "# q\nmutation{x}"]
)
async def test_non_queries_are_rejected_without_a_request(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None], query: str
) -> None:
    _, session = await _setup(hass, patch_session)

    with pytest.raises(ServiceValidationError):
        await _call(hass, query=query)

    assert session.requests == []


async def test_undeclared_and_missing_variables_are_rejected(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None]
) -> None:
    _, session = await _setup(hass, patch_session)

    with pytest.raises(ServiceValidationError, match="not declared"):
        await _call(hass, query=QUERY, variables={"nope": 1})
    with pytest.raises(ServiceValidationError, match="no value"):
        await _call(hass, query="query($first: Int!) { viewer { login } }")

    assert session.requests == []


async def test_an_expensive_query_is_rejected_before_it_runs(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None]
) -> None:
    pricey = FakeResponse(200, {"data": {"pulseCost": {"cost": 500, "nodeCount": 1}}})
    _, session = await _setup(hass, patch_session, pricey)

    with pytest.raises(ServiceValidationError, match="500"):
        await _call(hass, query=QUERY)

    assert len(session.requests) == 1


async def test_an_oversized_result_is_rejected(
    hass: HomeAssistant,
    patch_session: Callable[[FakeSession], None],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(query_service, "MAX_RESPONSE_BYTES", 10)
    await _setup(hass, patch_session, COST, RESULT)

    with pytest.raises(ServiceValidationError, match="too large"):
        await _call(hass, query=QUERY)


async def test_a_slow_query_is_cancelled(
    hass: HomeAssistant,
    patch_session: Callable[[FakeSession], None],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def slow(*args: object) -> None:
        await asyncio.sleep(5)

    monkeypatch.setattr(query_service, "TIMEOUT_SECONDS", 0.01)
    monkeypatch.setattr(query_service, "estimate_cost", slow)
    await _setup(hass, patch_session)

    with pytest.raises(HomeAssistantError, match="too long"):
        await _call(hass, query=QUERY)


async def test_github_errors_are_reported(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None]
) -> None:
    await _setup(hass, patch_session, FakeResponse(401, {"message": "Bad credentials"}))

    with pytest.raises(HomeAssistantError, match="could not run"):
        await _call(hass, query=QUERY)


async def test_a_nearly_spent_budget_blocks_the_call(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None]
) -> None:
    entry, session = await _setup(hass, patch_session)
    entry.runtime_data.client.budget.is_low = lambda resource="graphql": True  # type: ignore[method-assign]

    with pytest.raises(ServiceValidationError, match="rate budget"):
        await _call(hass, query=QUERY)

    assert session.requests == []
