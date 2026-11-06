"""Diagnostics for the GitHub Pulse integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_ACCESS_TOKEN
from homeassistant.core import HomeAssistant

from .const import (
    CONF_ATTRIBUTES_TEMPLATE,
    CONF_OWNER,
    CONF_QUERY,
    CONF_QUERY_NAME,
    CONF_QUERY_VARIABLES,
    CONF_REPOSITORY,
    CONF_STATE_TEMPLATE,
)
from .models import GitHubPulseConfigEntry

# The GitHub login appears in the title, the unique ID and the owner, and may
# appear in the repository names and in the query name, text, variables and
# templates of the subentries, so all of them are redacted along with the token.
TO_REDACT = {
    CONF_ACCESS_TOKEN,
    CONF_OWNER,
    CONF_REPOSITORY,
    CONF_QUERY,
    CONF_QUERY_NAME,
    CONF_QUERY_VARIABLES,
    CONF_STATE_TEMPLATE,
    CONF_ATTRIBUTES_TEMPLATE,
    "title",
    "unique_id",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: GitHubPulseConfigEntry
) -> dict[str, Any]:
    """Return diagnostics with the token and the account name redacted."""
    data = entry.runtime_data
    return {
        "entry": async_redact_data(entry.as_dict(), TO_REDACT),
        "modules": sorted(data.modules),
        "rate_budget": data.client.budget.as_dict(),
    }
