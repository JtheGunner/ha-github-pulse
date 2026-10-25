"""Runtime data shared by the platforms and coordinators of an entry."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry

from .api import GitHubClient


@dataclass(slots=True)
class GitHubPulseData:
    """Objects created when an entry is set up."""

    client: GitHubClient
    login: str
    modules: frozenset[str]


type GitHubPulseConfigEntry = ConfigEntry[GitHubPulseData]
