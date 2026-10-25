"""Sensor platform."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType

from .const import CONF_REPOSITORY, DOMAIN
from .entity import GitHubPulseEntity
from .models import GitHubPulseConfigEntry
from .profile_coordinator import ProfileCoordinator
from .repository_coordinator import (
    GROUP_DOWNLOADS,
    GROUP_OVERVIEW,
    RepositoryCoordinator,
)
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
    if (repositories := entry.runtime_data.repositories) is not None:
        for subentry_id, subentry in entry.subentries.items():
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
        entry = coordinator.config_entry
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{entry.entry_id}_{full_name.lower()}")},
            name=full_name,
            manufacturer="GitHub",
            entry_type=DeviceEntryType.SERVICE,
            configuration_url=f"https://github.com/{full_name}",
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
