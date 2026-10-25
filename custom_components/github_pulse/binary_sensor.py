"""Binary sensor platform."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .actions_coordinator import GROUP_RUNS, ActionsCoordinator
from .analytics.actions import summarize
from .const import CONF_REPOSITORY
from .entity import GitHubPulseEntity, repository_device_info
from .models import GitHubPulseConfigEntry
from .sensor_actions import ACTIONS_BINARY_SENSORS, ActionsBinarySensorDescription
from .sensor_repository import now


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GitHubPulseConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create the Actions binary sensors of every repository that tracks runs."""
    if (actions := entry.runtime_data.actions) is None:
        return
    for subentry_id, subentry in entry.subentries.items():
        full_name = subentry.data[CONF_REPOSITORY]
        if full_name in actions.repositories:
            async_add_entities(
                (
                    ActionsBinarySensor(actions, full_name, description)
                    for description in ACTIONS_BINARY_SENSORS
                ),
                config_subentry_id=subentry_id,
            )


class ActionsBinarySensor(GitHubPulseEntity, BinarySensorEntity):
    """Whether a workflow of a repository is running right now."""

    coordinator: ActionsCoordinator
    entity_description: ActionsBinarySensorDescription

    def __init__(
        self,
        coordinator: ActionsCoordinator,
        full_name: str,
        description: ActionsBinarySensorDescription,
    ) -> None:
        """Create the binary sensor for one repository."""
        super().__init__(
            coordinator, f"{full_name.lower()}_{description.key}", GROUP_RUNS
        )
        self.entity_description = description
        self._full_name = full_name
        self._attr_device_info = repository_device_info(
            coordinator.config_entry.entry_id, full_name
        )

    @property
    def available(self) -> bool:
        """Return whether the token could read this repository's runs."""
        runs = (self.coordinator.data or {}).get(GROUP_RUNS, {}).get(self._full_name)
        return super().available and runs is not None

    @property
    def is_on(self) -> bool | None:
        """Return whether a run is in progress."""
        runs = (self.coordinator.data or {}).get(GROUP_RUNS, {}).get(self._full_name)
        if runs is None:
            return None
        return self.entity_description.value_fn(summarize(runs, now()))
