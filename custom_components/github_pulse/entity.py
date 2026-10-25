"""Base entity for GitHub Pulse."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ATTRIBUTION, DOMAIN
from .coordinator import GitHubPulseCoordinator


class GitHubPulseEntity(CoordinatorEntity[GitHubPulseCoordinator]):
    """An entity that belongs to the account device of a config entry."""

    _attr_has_entity_name = True
    _attr_attribution = ATTRIBUTION

    def __init__(
        self, coordinator: GitHubPulseCoordinator, key: str, group: str
    ) -> None:
        """Create the entity for one data group of the coordinator."""
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self._group = group
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=f"GitHub {entry.runtime_data.login}",
            manufacturer="GitHub",
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def available(self) -> bool:
        """Return whether the entity's data group has loaded at least once."""
        return super().available and self._group in (self.coordinator.data or {})


def repository_device_info(entry_id: str, full_name: str) -> DeviceInfo:
    """Return the device shared by all entities of one tracked repository."""
    return DeviceInfo(
        identifiers={(DOMAIN, f"{entry_id}_{full_name.lower()}")},
        name=full_name,
        manufacturer="GitHub",
        entry_type=DeviceEntryType.SERVICE,
        configuration_url=f"https://github.com/{full_name}",
    )
