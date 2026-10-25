"""Coordinator for the tracked repositories."""

from __future__ import annotations

import asyncio
from collections.abc import Collection

from homeassistant.config_entries import ConfigSubentry
from homeassistant.core import HomeAssistant

from .const import CONF_REPOSITORY, SUBENTRY_REPOSITORY
from .coordinator import GitHubPulseCoordinator, GroupFetcher
from .models import GitHubPulseConfigEntry
from .repository_fetch import (
    RepositorySnapshot,
    fetch_snapshots,
    fetch_total_downloads,
)
from .settings import Settings

GROUP_OVERVIEW = "overview"
GROUP_DOWNLOADS = "downloads"
REPOSITORY_GROUPS = frozenset({GROUP_OVERVIEW, GROUP_DOWNLOADS})


def repository_subentries(
    entry: GitHubPulseConfigEntry,
) -> list[tuple[str, ConfigSubentry]]:
    """Return the id and data holder of every repository subentry."""
    return [
        (subentry_id, sub)
        for subentry_id, sub in entry.subentries.items()
        if sub.subentry_type == SUBENTRY_REPOSITORY
    ]


def tracked_repositories(entry: GitHubPulseConfigEntry) -> list[str]:
    """Return the full names of the repositories added as subentries."""
    return sorted(
        sub.data[CONF_REPOSITORY]
        for sub in entry.subentries.values()
        if sub.subentry_type == SUBENTRY_REPOSITORY
    )


class RepositoryCoordinator(GitHubPulseCoordinator):
    """Refresh all tracked repositories together."""

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: GitHubPulseConfigEntry,
        *,
        settings: Settings,
        active_groups: Collection[str] = REPOSITORY_GROUPS,
    ) -> None:
        """Create the coordinator for the entry's tracked repositories."""
        self.repositories = tracked_repositories(config_entry)
        groups: dict[str, GroupFetcher] = {
            GROUP_OVERVIEW: self._fetch_overview,
            GROUP_DOWNLOADS: self._fetch_downloads,
        }
        super().__init__(
            hass,
            config_entry,
            name="GitHub Pulse repositories",
            client=config_entry.runtime_data.client,
            update_interval=settings.repository_interval,
            groups=groups,
            active_groups=active_groups,
        )

    async def _fetch_overview(self) -> dict[str, RepositorySnapshot | None]:
        return await fetch_snapshots(self.client, self.repositories)

    async def _fetch_downloads(self) -> dict[str, int]:
        totals = await asyncio.gather(
            *(fetch_total_downloads(self.client, name) for name in self.repositories)
        )
        return dict(zip(self.repositories, totals, strict=True))
