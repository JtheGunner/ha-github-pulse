"""Run a user-written GraphQL query and render its result with templates."""

from __future__ import annotations

from collections.abc import Collection, Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import TemplateError
from homeassistant.helpers.template import Template

from .api import GraphQLResult

MAX_STATE_LENGTH = 255

type StateValue = str | int | float | bool | None


class GraphQLRunner(Protocol):
    """The part of the API client the engine needs."""

    async def graphql(
        self, query: str, variables: Mapping[str, Any] | None = None
    ) -> GraphQLResult:
        """Run a GraphQL query."""
        ...


class QueryRenderError(Exception):
    """A template failed or rendered something a sensor cannot hold."""


@dataclass(frozen=True, slots=True)
class QueryDefinition:
    """A custom query and how to turn its result into a sensor."""

    name: str
    query: str
    state_template: str
    attributes_template: str | None = None
    variables: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class QueryOutcome:
    """The rendered state and attributes of one query run."""

    state: StateValue
    attributes: dict[str, Any]
    errors: list[dict[str, Any]]
    data: dict[str, Any]


def resolve_variables(
    declared: Collection[str],
    helpers: Mapping[str, Any],
    user: Mapping[str, Any],
) -> dict[str, Any]:
    """Return the values for the variables the query declares.

    User values win over helpers. Helpers the query does not declare are left
    out, because GitHub rejects variables a query does not use.
    """
    unknown = sorted(set(user) - set(declared))
    if unknown:
        msg = f"variables not declared by the query: {', '.join(unknown)}"
        raise QueryRenderError(msg)
    values = {**helpers, **user}
    missing = sorted(set(declared) - set(values))
    if missing:
        msg = f"no value for the declared variables: {', '.join(missing)}"
        raise QueryRenderError(msg)
    return {name: values[name] for name in declared}


async def run_query(
    hass: HomeAssistant, client: GraphQLRunner, definition: QueryDefinition
) -> QueryOutcome:
    """Run the query and render the templates over its ``data`` as ``value_json``.

    GitHub errors propagate as ``GitHubError``; template problems raise
    :class:`QueryRenderError`.
    """
    result = await client.graphql(definition.query, definition.variables)
    context = {"value_json": result.data, "errors": result.errors}
    state = _render_state(hass, definition.state_template, context)
    attributes = (
        _render_attributes(hass, definition.attributes_template, context)
        if definition.attributes_template
        else {}
    )
    return QueryOutcome(state, attributes, result.errors, result.data)


def _render(hass: HomeAssistant, source: str, context: Mapping[str, Any]) -> Any:
    try:
        return Template(source, hass).async_render(
            dict(context), parse_result=True, strict=True
        )
    except TemplateError as err:
        msg = f"template failed: {err}"
        raise QueryRenderError(msg) from err


def _render_state(
    hass: HomeAssistant, source: str, context: Mapping[str, Any]
) -> StateValue:
    value = _render(hass, source, context)
    if value is not None and not isinstance(value, str | int | float | bool):
        msg = "the state template must render a single value, not a list or mapping"
        raise QueryRenderError(msg)
    if isinstance(value, str) and len(value) > MAX_STATE_LENGTH:
        msg = f"the state is longer than {MAX_STATE_LENGTH} characters"
        raise QueryRenderError(msg)
    return value


def _render_attributes(
    hass: HomeAssistant, source: str, context: Mapping[str, Any]
) -> dict[str, Any]:
    value = _render(hass, source, context)
    if not isinstance(value, dict):
        msg = "the attributes template must render a mapping"
        raise QueryRenderError(msg)
    return value
