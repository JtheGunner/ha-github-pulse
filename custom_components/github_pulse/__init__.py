"""The GitHub Pulse integration."""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from functools import partial
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ACCESS_TOKEN, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType

from .actions_coordinator import (
    GROUP_RUNS,
    ActionsCoordinator,
    actions_repositories,
)
from .api import GitHubClient
from .const import CONF_MODULES, CONF_OWNER, DOMAIN, MODULE_PROFILE, MODULE_REPOSITORIES
from .coordinator import GitHubPulseCoordinator
from .events import EventDispatcher
from .groups import GroupedEntity, active_groups
from .history_store import HistoryStore
from .language_store import LanguageStore
from .models import GitHubPulseConfigEntry, GitHubPulseData
from .profile_coordinator import ProfileCoordinator
from .query_coordinator import QueryCoordinator, query_subentries
from .repository_coordinator import (
    RepositoryCoordinator,
    tracked_repositories,
)
from .sensor_actions import ACTIONS_BINARY_SENSORS, ACTIONS_SENSORS
from .sensor_profile import PROFILE_SENSORS
from .sensor_repository import REPOSITORY_SENSORS
from .services import async_setup_services
from .settings import Settings

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.EVENT]

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
    if MODULE_REPOSITORIES in entry.runtime_data.modules and actions_repositories(
        entry
    ):
        actions = ActionsCoordinator(
            hass, entry, active_groups=_actions_groups(hass, entry)
        )
        await actions.async_config_entry_first_refresh()
        entry.runtime_data.actions = actions
    _release_account_device(hass, entry)
    for subentry_id, subentry in query_subentries(entry):
        query = QueryCoordinator(hass, entry, subentry)
        await query.async_refresh()
        entry.runtime_data.queries[subentry_id] = query
    await _async_setup_events(hass, entry)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload_on_change(entry)))
    return True


def _release_account_device(hass: HomeAssistant, entry: GitHubPulseConfigEntry) -> None:
    """Move the account device back out of any subentry.

    Versions before 1.0.3 attached it to the subentry of a custom query, which
    detached the profile sensors from it.
    """
    devices = dr.async_get(hass)
    device = devices.async_get_device_by_identifier(
        (DOMAIN, entry.entry_id), entry.entry_id
    )
    if device is not None and device.config_subentry_id is not None:
        devices.async_update_device(
            device.id,
            new_config_entry_id=entry.entry_id,
            new_config_subentry_id=None,
        )


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
            GroupedEntity(d.key, group, d.entity_registry_enabled_default)
            for d in PROFILE_SENSORS
            for group in (d.group, *d.also_needs)
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


def _actions_groups(
    hass: HomeAssistant, entry: GitHubPulseConfigEntry
) -> frozenset[str]:
    """Return the Actions data groups needed by the enabled entities."""
    registry = er.async_get(hass)
    needed: set[str] = set()
    for full_name in actions_repositories(entry):

        def enabled(key: str, full_name: str = full_name) -> bool | None:
            unique_id = f"{entry.entry_id}_{full_name.lower()}_{key}"
            for platform in (Platform.SENSOR, Platform.BINARY_SENSOR):
                entity_id = registry.async_get_entity_id(platform, DOMAIN, unique_id)
                if entity_id and (found := registry.async_get(entity_id)):
                    return not found.disabled
            return None

        descriptions = [*ACTIONS_SENSORS, *ACTIONS_BINARY_SENSORS]
        needed |= active_groups(
            (
                GroupedEntity(d.key, GROUP_RUNS, d.entity_registry_enabled_default)
                for d in descriptions
            ),
            enabled,
        )
    return frozenset(needed)


async def _async_setup_events(
    hass: HomeAssistant, entry: GitHubPulseConfigEntry
) -> None:
    """Create the dispatcher and subscribe it to every coordinator that feeds it.

    The current data is processed once first: on a fresh install this only
    initialises the stored state, so existing history is not announced.
    """
    data = entry.runtime_data
    dispatcher = EventDispatcher(hass, entry.entry_id)
    await dispatcher.async_load()
    data.events = dispatcher
    for coordinator, handler in (
        (data.actions, dispatcher.handle_runs),
        (data.repositories, dispatcher.handle_repositories),
        (data.profile, dispatcher.handle_search),
    ):
        if coordinator is None:
            continue
        handler(coordinator.data)
        entry.async_on_unload(
            coordinator.async_add_listener(partial(_forward, coordinator, handler))
        )


def _forward(
    coordinator: GitHubPulseCoordinator,
    handler: Callable[[dict[str, Any]], None],
) -> None:
    """Pass fresh coordinator data to a dispatcher handler."""
    handler(coordinator.data)
