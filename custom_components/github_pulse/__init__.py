"""The GitHub Pulse integration."""

from __future__ import annotations

from homeassistant.const import CONF_ACCESS_TOKEN, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType

from .api import GitHubClient
from .const import CONF_MODULES, CONF_OWNER, DOMAIN, MODULE_PROFILE
from .groups import GroupedEntity, active_groups
from .history_store import HistoryStore
from .language_store import LanguageStore
from .models import GitHubPulseConfigEntry, GitHubPulseData
from .profile_coordinator import ProfileCoordinator
from .sensor_profile import PROFILE_SENSORS
from .services import async_setup_services
from .settings import Settings

PLATFORMS: list[Platform] = [Platform.SENSOR]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the integration's services."""
    async_setup_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: GitHubPulseConfigEntry) -> bool:
    """Set up GitHub Pulse from a config entry."""
    entry.runtime_data = GitHubPulseData(
        client=GitHubClient(
            async_get_clientsession(hass), entry.data[CONF_ACCESS_TOKEN]
        ),
        login=entry.data[CONF_OWNER],
        modules=frozenset(entry.data[CONF_MODULES]),
    )
    if MODULE_PROFILE in entry.runtime_data.modules:
        history = HistoryStore(hass, entry.entry_id)
        await history.async_load()
        languages = LanguageStore(hass, entry.entry_id)
        await languages.async_load()
        profile = ProfileCoordinator(
            hass,
            entry,
            settings=Settings.from_options(entry.options),
            history=history,
            languages=languages,
            active_groups=_profile_groups(hass, entry),
        )
        await profile.async_config_entry_first_refresh()
        entry.runtime_data.profile = profile
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: GitHubPulseConfigEntry
) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


def _profile_groups(
    hass: HomeAssistant, entry: GitHubPulseConfigEntry
) -> frozenset[str]:
    """Return the profile data groups needed by the enabled sensors."""
    registry = er.async_get(hass)

    def enabled(key: str) -> bool | None:
        entity_id = registry.async_get_entity_id(
            Platform.SENSOR, DOMAIN, f"{entry.entry_id}_{key}"
        )
        if entity_id is None or (registered := registry.async_get(entity_id)) is None:
            return None
        return not registered.disabled

    return active_groups(
        (
            GroupedEntity(d.key, d.group, d.entity_registry_enabled_default)
            for d in PROFILE_SENSORS
        ),
        enabled,
    )
