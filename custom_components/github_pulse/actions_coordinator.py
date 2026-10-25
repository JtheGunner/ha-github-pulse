"""Coordinator for the workflow runs of repositories with Actions tracking."""

from __future__ import annotations

from collections.abc import Collection
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .actions_fetch import fetch_runs
from .analytics.actions import WorkflowRun
from .api import GitHubForbiddenError, GitHubNotFoundError
from .const import CONF_ACTIONS, CONF_REPOSITORY, SUBENTRY_REPOSITORY
from .coordinator import GitHubPulseCoordinator, GroupFetcher
from .models import GitHubPulseConfigEntry

GROUP_RUNS = "runs"
DEFAULT_INTERVAL = timedelta(minutes=5)


def actions_repositories(entry: GitHubPulseConfigEntry) -> list[str]:
    """Return the repositories whose workflow runs are tracked."""
    return sorted(
        sub.data[CONF_REPOSITORY]
        for sub in entry.subentries.values()
        if sub.subentry_type == SUBENTRY_REPOSITORY and sub.data.get(CONF_ACTIONS)
    )


class ActionsCoordinator(GitHubPulseCoordinator):
    """Refresh workflow runs; a repository the token cannot read becomes ``None``."""

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: GitHubPulseConfigEntry,
        *,
        interval: timedelta = DEFAULT_INTERVAL,
        active_groups: Collection[str] = (GROUP_RUNS,),
    ) -> None:
        """Create the coordinator for the entry's Actions repositories."""
        self.repositories = actions_repositories(config_entry)
        groups: dict[str, GroupFetcher] = {GROUP_RUNS: self._fetch_runs}
        super().__init__(
            hass,
            config_entry,
            name="GitHub Pulse actions",
            client=config_entry.runtime_data.client,
            update_interval=interval,
            groups=groups,
            active_groups=active_groups,
            rate_resource="core",
        )

    async def _fetch_runs(self) -> dict[str, list[WorkflowRun] | None]:
        now = dt_util.utcnow()
        result: dict[str, list[WorkflowRun] | None] = {}
        for full_name in self.repositories:
            try:
                result[full_name] = await fetch_runs(self.client, full_name, now)
            except GitHubForbiddenError, GitHubNotFoundError:
                result[full_name] = None
        return result
