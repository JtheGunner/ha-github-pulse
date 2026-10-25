"""Runtime data shared by the platforms and coordinators of an entry."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry

from .api import GitHubClient

if TYPE_CHECKING:
    from .profile_coordinator import ProfileCoordinator


@dataclass(slots=True)
class GitHubPulseData:
    """Objects created when an entry is set up."""

    client: GitHubClient
    login: str
    modules: frozenset[str]
    profile: ProfileCoordinator | None = None


type GitHubPulseConfigEntry = ConfigEntry[GitHubPulseData]
