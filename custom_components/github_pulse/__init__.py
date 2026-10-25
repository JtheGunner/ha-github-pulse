"""The GitHub Pulse integration."""

from __future__ import annotations

from homeassistant.const import CONF_ACCESS_TOKEN, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import GitHubClient
from .const import CONF_MODULES, CONF_OWNER
from .models import GitHubPulseConfigEntry, GitHubPulseData

PLATFORMS: list[Platform] = []


async def async_setup_entry(hass: HomeAssistant, entry: GitHubPulseConfigEntry) -> bool:
    """Set up GitHub Pulse from a config entry."""
    entry.runtime_data = GitHubPulseData(
        client=GitHubClient(
            async_get_clientsession(hass), entry.data[CONF_ACCESS_TOKEN]
        ),
        login=entry.data[CONF_OWNER],
        modules=frozenset(entry.data[CONF_MODULES]),
    )
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: GitHubPulseConfigEntry
) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
