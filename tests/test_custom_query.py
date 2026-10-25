"""Tests for running a custom query and rendering its templates."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest
from custom_components.github_pulse.api import GitHubGraphQLError, GraphQLResult
from custom_components.github_pulse.custom_query import (
    QueryDefinition,
    QueryRenderError,
    run_query,
)
from homeassistant.core import HomeAssistant

DATA = {"viewer": {"repositories": {"totalCount": 42}, "login": "octocat"}}


class StubClient:
    def __init__(self, result: GraphQLResult | Exception) -> None:
        self._result = result
        self.calls: list[tuple[str, Mapping[str, Any] | None]] = []

    async def graphql(
        self, query: str, variables: Mapping[str, Any] | None = None
    ) -> GraphQLResult:
        self.calls.append((query, variables))
        if isinstance(self._result, Exception):
            raise self._result
        return self._result


def _definition(**overrides: Any) -> QueryDefinition:
    fields: dict[str, Any] = {
        "name": "Repository count",
        "query": "query { viewer { login } }",
        "state_template": "{{ value_json.viewer.repositories.totalCount }}",
    }
    return QueryDefinition(**{**fields, **overrides})


async def test_renders_the_state_as_a_number(hass: HomeAssistant) -> None:
    client = StubClient(GraphQLResult(DATA, []))

    outcome = await run_query(hass, client, _definition())

    assert outcome.state == 42
    assert outcome.attributes == {}


async def test_passes_the_variables_to_the_query(hass: HomeAssistant) -> None:
    client = StubClient(GraphQLResult(DATA, []))

    await run_query(hass, client, _definition(variables={"owner": "octocat"}))

    assert client.calls == [("query { viewer { login } }", {"owner": "octocat"})]


async def test_renders_attributes_as_a_mapping(hass: HomeAssistant) -> None:
    client = StubClient(GraphQLResult(DATA, []))

    outcome = await run_query(
        hass,
        client,
        _definition(attributes_template="{{ {'login': value_json.viewer.login} }}"),
    )

    assert outcome.attributes == {"login": "octocat"}


async def test_exposes_partial_errors_to_templates(hass: HomeAssistant) -> None:
    errors = [{"type": "FORBIDDEN", "message": "no"}]
    client = StubClient(GraphQLResult(DATA, errors))

    outcome = await run_query(
        hass, client, _definition(state_template="{{ errors | length }}")
    )

    assert outcome.state == 1
    assert outcome.errors == errors


async def test_undefined_values_are_a_template_error(hass: HomeAssistant) -> None:
    client = StubClient(GraphQLResult(DATA, []))

    with pytest.raises(QueryRenderError, match="template failed"):
        await run_query(
            hass, client, _definition(state_template="{{ value_json.nope.deeper }}")
        )


async def test_syntax_errors_are_a_template_error(hass: HomeAssistant) -> None:
    client = StubClient(GraphQLResult(DATA, []))

    with pytest.raises(QueryRenderError):
        await run_query(hass, client, _definition(state_template="{{ value_json"))


async def test_a_list_state_is_rejected(hass: HomeAssistant) -> None:
    client = StubClient(GraphQLResult(DATA, []))

    with pytest.raises(QueryRenderError, match="single value"):
        await run_query(hass, client, _definition(state_template="{{ [1, 2] }}"))


async def test_an_overlong_state_is_rejected(hass: HomeAssistant) -> None:
    client = StubClient(GraphQLResult(DATA, []))

    with pytest.raises(QueryRenderError, match="255"):
        await run_query(hass, client, _definition(state_template="{{ 'x' * 300 }}"))


async def test_non_mapping_attributes_are_rejected(hass: HomeAssistant) -> None:
    client = StubClient(GraphQLResult(DATA, []))

    with pytest.raises(QueryRenderError, match="mapping"):
        await run_query(hass, client, _definition(attributes_template="plain text"))


async def test_github_errors_propagate(hass: HomeAssistant) -> None:
    client = StubClient(GitHubGraphQLError("bad field", errors=[]))

    with pytest.raises(GitHubGraphQLError):
        await run_query(hass, client, _definition())
