"""Event platform: entities that trigger when new activity is detected."""

from __future__ import annotations

from homeassistant.components.event import EventEntity, EventEntityDescription
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .analytics.events import (
    PR_MERGED,
    RELEASE_PUBLISHED,
    REVIEW_REQUESTED,
    WORKFLOW_FAILED,
    WORKFLOW_RECOVERED,
    DetectedEvent,
)
from .const import ATTRIBUTION, CONF_ACTIONS, CONF_REPOSITORY, DOMAIN
from .entity import repository_device_info
from .events import EventDispatcher
from .models import GitHubPulseConfigEntry

ACCOUNT_EVENT_TYPES = [REVIEW_REQUESTED, PR_MERGED]
RELEASE_EVENT_TYPES = [RELEASE_PUBLISHED]
WORKFLOW_EVENT_TYPES = [WORKFLOW_FAILED, WORKFLOW_RECOVERED]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GitHubPulseConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create the event entities."""
    dispatcher = entry.runtime_data.events
    if dispatcher is None:
        return
    if entry.runtime_data.profile is not None:
        async_add_entities([AccountEvents(dispatcher, entry)])
    if entry.runtime_data.repositories is not None:
        for subentry_id, subentry in entry.subentries.items():
            full_name = subentry.data[CONF_REPOSITORY]
            types = list(RELEASE_EVENT_TYPES)
            if subentry.data.get(CONF_ACTIONS):
                types += WORKFLOW_EVENT_TYPES
            async_add_entities(
                [RepositoryEvents(dispatcher, entry, full_name, types)],
                config_subentry_id=subentry_id,
            )


class _Events(EventEntity):
    """Common behaviour: subscribe to the dispatcher and forward its events."""

    _attr_has_entity_name = True
    _attr_attribution = ATTRIBUTION
    _attr_should_poll = False

    def __init__(self, dispatcher: EventDispatcher) -> None:
        self._dispatcher = dispatcher

    def _wants(self, event: DetectedEvent) -> bool:
        raise NotImplementedError

    async def async_added_to_hass(self) -> None:
        """Start listening when the entity is added."""
        self.async_on_remove(self._dispatcher.async_add_listener(self._handle))

    @callback
    def _handle(self, event: DetectedEvent) -> None:
        if self._wants(event) and event.type in self.event_types:
            self._trigger_event(event.type, dict(event.data))
            self.async_write_ha_state()


class RepositoryEvents(_Events):
    """Workflow and release events of one repository."""

    entity_description = EventEntityDescription(
        key="repository_events", translation_key="repository_events"
    )

    def __init__(
        self,
        dispatcher: EventDispatcher,
        entry: GitHubPulseConfigEntry,
        full_name: str,
        event_types: list[str],
    ) -> None:
        """Create the entity for one repository."""
        super().__init__(dispatcher)
        self._full_name = full_name
        self._attr_event_types = event_types
        self._attr_unique_id = f"{entry.entry_id}_{full_name.lower()}_events"
        self._attr_device_info = repository_device_info(entry.entry_id, full_name)

    def _wants(self, event: DetectedEvent) -> bool:
        return event.repository == self._full_name


class AccountEvents(_Events):
    """Review requests and merged pull requests of the account."""

    entity_description = EventEntityDescription(
        key="account_events",
        translation_key="account_events",
        entity_registry_enabled_default=False,
    )
    _attr_event_types = ACCOUNT_EVENT_TYPES

    def __init__(
        self, dispatcher: EventDispatcher, entry: GitHubPulseConfigEntry
    ) -> None:
        """Create the account entity."""
        super().__init__(dispatcher)
        self._attr_unique_id = f"{entry.entry_id}_account_events"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=f"GitHub {entry.runtime_data.login}",
            manufacturer="GitHub",
            entry_type=DeviceEntryType.SERVICE,
        )

    def _wants(self, event: DetectedEvent) -> bool:
        return event.type in ACCOUNT_EVENT_TYPES
