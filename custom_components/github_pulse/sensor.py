"""Sensor platform."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType

from .entity import GitHubPulseEntity
from .models import GitHubPulseConfigEntry
from .profile_coordinator import ProfileCoordinator
from .sensor_profile import PROFILE_SENSORS, ProfileSensorDescription, ProfileView


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
