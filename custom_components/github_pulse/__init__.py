"""The GitHub Pulse integration."""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ACCESS_TOKEN, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType

from .api import GitHubClient
from .const import CONF_MODULES, CONF_OWNER, DOMAIN, MODULE_PROFILE, MODULE_REPOSITORIES
from .groups import GroupedEntity, active_groups
from .history_store import HistoryStore
from .language_store import LanguageStore
from .models import GitHubPulseConfigEntry, GitHubPulseData
from .profile_coordinator import ProfileCoordinator
from .repository_coordinator import (
    RepositoryCoordinator,
    tracked_repositories,
)
from .sensor_profile import PROFILE_SENSORS
from .sensor_repository import REPOSITORY_SENSORS
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
    if MODULE_REPOSITORIES in entry.runtime_data.modules and tracked_repositories(
        entry
    ):
        repositories = RepositoryCoordinator(
            hass,
            entry,
            settings=Settings.from_options(entry.options),
            active_groups=_repository_groups(hass, entry),
        )
        await repositories.async_config_entry_first_refresh()
        entry.runtime_data.repositories = repositories
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload_on_change(entry)))
    return True


def _async_reload_on_change(
    entry: GitHubPulseConfigEntry,
) -> Callable[[HomeAssistant, ConfigEntry[Any]], Coroutine[Any, Any, None]]:
    """Reload when the options change or repositories are added, removed or changed."""
    known = _snapshot(entry)

    async def _listener(hass: HomeAssistant, updated: ConfigEntry[Any]) -> None:
        nonlocal known
        current = _snapshot(updated)
        if current != known:
            known = current
            hass.config_entries.async_schedule_reload(updated.entry_id)

    return _listener


async def async_unload_entry(
    hass: HomeAssistant, entry: GitHubPulseConfigEntry
) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


def _snapshot(entry: ConfigEntry[Any]) -> dict[str, Any]:
    """Return the parts of an entry whose change requires a reload."""
    return {
        "options": dict(entry.options),
        "subentries": {key: dict(sub.data) for key, sub in entry.subentries.items()},
    }


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


def _repository_groups(
    hass: HomeAssistant, entry: GitHubPulseConfigEntry
) -> frozenset[str]:
    """Return the repository data groups needed by the enabled sensors."""
    registry = er.async_get(hass)
    needed: set[str] = set()
    for full_name in tracked_repositories(entry):

        def enabled(key: str, full_name: str = full_name) -> bool | None:
            unique_id = f"{entry.entry_id}_{full_name.lower()}_{key}"
            entity_id = registry.async_get_entity_id(Platform.SENSOR, DOMAIN, unique_id)
            if entity_id is None or (found := registry.async_get(entity_id)) is None:
                return None
            return not found.disabled

        needed |= active_groups(
            (
                GroupedEntity(d.key, d.group, d.entity_registry_enabled_default)
                for d in REPOSITORY_SENSORS
            ),
            enabled,
        )
    return frozenset(needed)
