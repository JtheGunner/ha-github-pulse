"""The ``query`` service: run a read-only GraphQL query and return its result."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from datetime import datetime
from typing import Any

import probatio
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
)
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .analytics.query_variables import query_variables
from .api import GitHubError
from .api.query_validation import (
    QueryTooExpensiveError,
    QueryValidationError,
    ensure_affordable,
    estimate_cost,
    parse_query,
)
from .const import DOMAIN
from .custom_query import QueryRenderError, resolve_variables
from .models import GitHubPulseConfigEntry
from .settings import Settings

SERVICE_QUERY = "query"
ATTR_CONFIG_ENTRY_ID = "config_entry_id"
ATTR_QUERY = "query"
ATTR_VARIABLES = "variables"
TIMEOUT_SECONDS = 30
MAX_RESPONSE_BYTES = 200_000

type EntryLookup = Callable[[HomeAssistant, str | None], GitHubPulseConfigEntry]

QUERY_SCHEMA = probatio.Schema(
    {
        probatio.Optional(ATTR_CONFIG_ENTRY_ID): cv.string,
        probatio.Required(ATTR_QUERY): cv.string,
        probatio.Optional(ATTR_VARIABLES, default=dict): dict,
    }
)


def async_setup_query_service(hass: HomeAssistant, entry_lookup: EntryLookup) -> None:
    """Register the ``query`` service; ``entry_lookup`` resolves the account."""

    async def _handle(call: ServiceCall) -> ServiceResponse:
        return await _async_query(call, entry_lookup)

    hass.services.async_register(
        DOMAIN,
        SERVICE_QUERY,
        _handle,
        schema=QUERY_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )


def _invalid(key: str, detail: str) -> ServiceValidationError:
    return ServiceValidationError(
        translation_domain=DOMAIN,
        translation_key=key,
        translation_placeholders={"detail": detail},
    )


async def _async_query(call: ServiceCall, entry_lookup: EntryLookup) -> ServiceResponse:
    """Validate the query like a custom query sensor, then run it once."""
    entry = entry_lookup(call.hass, call.data.get(ATTR_CONFIG_ENTRY_ID))
    client = entry.runtime_data.client
    if client.budget.is_low("graphql"):
        raise ServiceValidationError(
            translation_domain=DOMAIN, translation_key="budget_low"
        )
    zone = Settings.from_options(entry.options).contribution_time_zone
    try:
        parsed = parse_query(call.data[ATTR_QUERY])
        variables = resolve_variables(
            parsed.declared_variables,
            query_variables(datetime.now(zone).date(), entry.runtime_data.login, zone),
            call.data[ATTR_VARIABLES],
        )
    except QueryValidationError as err:
        raise _invalid("query_invalid", str(err)) from err
    except QueryRenderError as err:
        raise _invalid("variables_invalid", str(err)) from err

    try:
        async with asyncio.timeout(TIMEOUT_SECONDS):
            cost = await estimate_cost(client, parsed, variables)
            ensure_affordable(cost)
            result = await client.graphql(call.data[ATTR_QUERY], variables)
    except QueryTooExpensiveError as err:
        raise _invalid("query_too_expensive", str(err)) from err
    except QueryValidationError as err:
        raise _invalid("query_invalid", str(err)) from err
    except TimeoutError as err:
        raise HomeAssistantError(
            translation_domain=DOMAIN, translation_key="query_timeout"
        ) from err
    except GitHubError as err:
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="query_failed",
            translation_placeholders={"detail": str(err)},
        ) from err

    size = len(json.dumps(result.data, default=str))
    if size > MAX_RESPONSE_BYTES:
        raise _invalid(
            "response_too_large", f"{size} bytes, the limit is {MAX_RESPONSE_BYTES}"
        )
    response: dict[str, Any] = {
        "data": result.data,
        "errors": result.errors,
        "cost": cost.cost,
    }
    return response
