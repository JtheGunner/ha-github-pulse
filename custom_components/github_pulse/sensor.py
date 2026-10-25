"""Sensor platform."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType

from .actions_coordinator import GROUP_RUNS, ActionsCoordinator
from .analytics.actions import summarize
from .const import (
    CONF_DEVICE_CLASS,
    CONF_REPOSITORY,
    CONF_STATE_CLASS,
    CONF_UNIT,
)
from .entity import GitHubPulseEntity, repository_device_info
from .models import GitHubPulseConfigEntry
from .profile_coordinator import ProfileCoordinator
from .query_coordinator import GROUP_QUERY, QueryCoordinator
from .repository_coordinator import (
    GROUP_DOWNLOADS,
    GROUP_OVERVIEW,
    RepositoryCoordinator,
    repository_subentries,
)
from .sensor_actions import ACTIONS_SENSORS, ActionsSensorDescription
from .sensor_profile import PROFILE_SENSORS, ProfileSensorDescription, ProfileView
from .sensor_repository import (
    REPOSITORY_SENSORS,
    RepositorySensorDescription,
    RepositoryView,
    now,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GitHubPulseConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create the sensors of every enabled module."""
    if (profile := entry.runtime_data.profile) is not None:
        async_add_entities(
            ProfileSensor(profile, description) for description in PROFILE_SENSORS
        )
    if (actions := entry.runtime_data.actions) is not None:
        for subentry_id, subentry in repository_subentries(entry):
            full_name = subentry.data[CONF_REPOSITORY]
            if full_name in actions.repositories:
                async_add_entities(
                    (
                        ActionsSensor(actions, full_name, description)
                        for description in ACTIONS_SENSORS
                    ),
                    config_subentry_id=subentry_id,
                )
    for subentry_id, query in entry.runtime_data.queries.items():
        async_add_entities([QuerySensor(query)], config_subentry_id=subentry_id)
    if (repositories := entry.runtime_data.repositories) is not None:
        for subentry_id, subentry in repository_subentries(entry):
            full_name = subentry.data[CONF_REPOSITORY]
            async_add_entities(
                (
                    RepositorySensor(repositories, full_name, description)
                    for description in REPOSITORY_SENSORS
                ),
                config_subentry_id=subentry_id,
            )


class ProfileSensor(GitHubPulseEntity, SensorEntity):
    """A sensor computed from the profile coordinator."""

    coordinator: ProfileCoordinator
    entity_description: ProfileSensorDescription
    _unrecorded_attributes = frozenset({"ranking", "changes_in_points"})

    def __init__(
        self, coordinator: ProfileCoordinator, description: ProfileSensorDescription
    ) -> None:
        """Create the sensor."""
        super().__init__(coordinator, description.key, description.group)
        self.entity_description = description

    def _view(self) -> ProfileView:
        return ProfileView(
            data=self.coordinator.data,
            settings=self.coordinator.settings,
            today=self.coordinator.today(),
        )

    @property
    def native_value(self) -> StateType:
        """Return the state."""
        return self.entity_description.value_fn(self._view())  # type: ignore[no-any-return]

    @property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        """Return the attributes, if the sensor defines any."""
        if self.entity_description.attributes_fn is None:
            return None
        return self.entity_description.attributes_fn(self._view())


class RepositorySensor(GitHubPulseEntity, SensorEntity):
    """A sensor of one tracked repository."""

    coordinator: RepositoryCoordinator
    entity_description: RepositorySensorDescription
    _unrecorded_attributes = frozenset({"url", "name"})

    def __init__(
        self,
        coordinator: RepositoryCoordinator,
        full_name: str,
        description: RepositorySensorDescription,
    ) -> None:
        """Create the sensor for one repository."""
        super().__init__(
            coordinator, f"{full_name.lower()}_{description.key}", description.group
        )
        self.entity_description = description
        self._full_name = full_name
        self._attr_device_info = repository_device_info(
            coordinator.config_entry.entry_id, full_name
        )

    def _view(self) -> RepositoryView | None:
        data = self.coordinator.data or {}
        snapshot = data.get(GROUP_OVERVIEW, {}).get(self._full_name)
        if snapshot is None:
            return None
        return RepositoryView(
            snapshot=snapshot,
            total_downloads=data.get(GROUP_DOWNLOADS, {}).get(self._full_name),
            now=now(),
        )

    @property
    def available(self) -> bool:
        """Return whether GitHub returned this repository."""
        return super().available and self._view() is not None

    @property
    def native_value(self) -> StateType | datetime:
        """Return the state."""
        view = self._view()
        return None if view is None else self.entity_description.value_fn(view)

    @property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        """Return the attributes, if the sensor defines any."""
        view = self._view()
        if view is None or self.entity_description.attributes_fn is None:
            return None
        return self.entity_description.attributes_fn(view)


class ActionsSensor(GitHubPulseEntity, SensorEntity):
    """A workflow-run sensor of one tracked repository."""

    coordinator: ActionsCoordinator
    entity_description: ActionsSensorDescription

    def __init__(
        self,
        coordinator: ActionsCoordinator,
        full_name: str,
        description: ActionsSensorDescription,
    ) -> None:
        """Create the sensor for one repository."""
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
    def native_value(self) -> StateType:
        """Return the state."""
        runs = (self.coordinator.data or {}).get(GROUP_RUNS, {}).get(self._full_name)
        if runs is None:
            return None
        value: StateType = self.entity_description.value_fn(summarize(runs, now()))
        return value


class QuerySensor(GitHubPulseEntity, SensorEntity):
    """A sensor rendered from the result of a custom query."""

    coordinator: QueryCoordinator

    def __init__(self, coordinator: QueryCoordinator) -> None:
        """Create the sensor for one custom query."""
        subentry = coordinator.subentry
        super().__init__(coordinator, f"query_{subentry.subentry_id}", GROUP_QUERY)
        data = subentry.data
        self._attr_name = subentry.title
        self._attr_native_unit_of_measurement = data.get(CONF_UNIT) or None
        if device_class := data.get(CONF_DEVICE_CLASS):
            self._attr_device_class = SensorDeviceClass(device_class)
        if state_class := data.get(CONF_STATE_CLASS):
            self._attr_state_class = SensorStateClass(state_class)

    @property
    def native_value(self) -> StateType:
        """Return the rendered state."""
        outcome = self.coordinator.outcome()
        return None if outcome is None else outcome.state

    @property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        """Return the rendered attributes."""
        outcome = self.coordinator.outcome()
        return None if outcome is None else outcome.attributes
