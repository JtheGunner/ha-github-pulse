"""Base coordinator with demand-based data groups and rate-aware polling."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Collection, Mapping
from datetime import timedelta
from typing import Any, override

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import GitHubAuthError, GitHubClient, GitHubError
from .const import LOGGER
from .models import GitHubPulseConfigEntry

SLOWDOWN_FACTOR = 4

type GroupFetcher = Callable[[], Awaitable[Any]]


class GitHubPulseCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Fetch several independent data groups and merge them into one dict.

    * Only groups in ``active_groups`` are fetched.
    * A group that fails keeps its last good value; the error is kept in
      :attr:`errors`. The update only fails when every active group failed.
    * An authentication error starts reauthentication.
    * While the rate budget of ``rate_resource`` is low, polling slows down.
    """

    config_entry: GitHubPulseConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: GitHubPulseConfigEntry,
        *,
        name: str,
        client: GitHubClient,
        update_interval: timedelta,
        groups: Mapping[str, GroupFetcher],
        active_groups: Collection[str],
        rate_resource: str = "graphql",
    ) -> None:
        """Create the coordinator for the given groups."""
        super().__init__(
            hass,
            LOGGER,
            config_entry=config_entry,
            name=name,
            update_interval=update_interval,
        )
        self.client = client
        self.errors: dict[str, str] = {}
        self._groups = dict(groups)
        self._active = frozenset(active_groups) & self._groups.keys()
        self._base_interval = update_interval
        self._rate_resource = rate_resource

    @property
    def active_groups(self) -> frozenset[str]:
        """Return the groups fetched on every refresh."""
        return self._active

    @override
    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch every active group and merge the results."""
        fetched = await asyncio.gather(
            *(self._fetch(group) for group in sorted(self._active))
        )
        successes = {g: value for g, value, error in fetched if error is None}
        failures = {g: error for g, _, error in fetched if error is not None}

        for error in failures.values():
            if isinstance(error, GitHubAuthError):
                raise ConfigEntryAuthFailed(str(error)) from error
        self.errors = {group: str(error) for group, error in failures.items()}
        self._adapt_interval()

        if failures and not successes:
            first = next(iter(failures.values()))
            raise UpdateFailed(f"Error communicating with GitHub: {first}") from first
        return {**(self.data or {}), **successes}

    async def _fetch(self, group: str) -> tuple[str, Any, GitHubError | None]:
        """Run one group fetcher, returning its value or its error."""
        try:
            return group, await self._groups[group](), None
        except GitHubError as err:
            LOGGER.debug("Group %s failed: %s", group, err)
            return group, None, err

    def _adapt_interval(self) -> None:
        """Slow polling down while the rate budget is nearly spent."""
        low = self.client.budget.is_low(self._rate_resource)
        self.update_interval = (
            self._base_interval * SLOWDOWN_FACTOR if low else self._base_interval
        )
