"""Diagnostics for the GitHub Pulse integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_ACCESS_TOKEN
from homeassistant.core import HomeAssistant

from .models import GitHubPulseConfigEntry

TO_REDACT = {CONF_ACCESS_TOKEN}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: GitHubPulseConfigEntry
) -> dict[str, Any]:
    """Return diagnostics with the access token redacted."""
    data = entry.runtime_data
    return {
        "entry": async_redact_data(entry.as_dict(), TO_REDACT),
        "modules": sorted(data.modules),
        "rate_budget": data.client.budget.as_dict(),
    }
