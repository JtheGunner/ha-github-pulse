"""Base coordinator with demand-based data groups and rate-aware polling."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Collection, Mapping
from datetime import timedelta
from typing import Any, override

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import (
    GitHubAuthError,
    GitHubClient,
    GitHubError,
    GitHubForbiddenError,
    GitHubRateLimitError,
)
from .const import DOMAIN, LOGGER
from .models import GitHubPulseConfigEntry

SLOWDOWN_FACTOR = 4

ISSUE_RATE_LIMITED = "rate_limited"
ISSUE_FORBIDDEN = "forbidden"
_ISSUE_KINDS = (ISSUE_RATE_LIMITED, ISSUE_FORBIDDEN)

type GroupFetcher = Callable[[], Awaitable[Any]]


class GitHubPulseCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Fetch several independent data groups and merge them into one dict.

    * Only groups in ``active_groups`` are fetched.
    * A group that fails keeps its last good value; the error is kept in
      :attr:`errors`. The update only fails when every active group failed.
    * An authentication error starts reauthentication.
    * A rate-limit or permission error raises a repair issue that clears once
      the group refreshes again.
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
        self._sync_repair_issues(successes, failures)
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

    def _issue_id(self, group: str, kind: str) -> str:
        return f"{self.config_entry.entry_id}_{self.name}_{group}_{kind}"

    def _sync_repair_issues(
        self, successes: Mapping[str, Any], failures: Mapping[str, GitHubError]
    ) -> None:
        """Raise a repair issue per rate-limited or forbidden group, clear the rest."""
        for group in successes:
            for kind in _ISSUE_KINDS:
                ir.async_delete_issue(self.hass, DOMAIN, self._issue_id(group, kind))
        for group, error in failures.items():
            if isinstance(error, GitHubRateLimitError):
                kind = ISSUE_RATE_LIMITED
            elif isinstance(error, GitHubForbiddenError):
                kind = ISSUE_FORBIDDEN
            else:
                continue
            for other in _ISSUE_KINDS:
                if other != kind:
                    ir.async_delete_issue(
                        self.hass, DOMAIN, self._issue_id(group, other)
                    )
            ir.async_create_issue(
                self.hass,
                DOMAIN,
                self._issue_id(group, kind),
                is_fixable=False,
                severity=ir.IssueSeverity.WARNING,
                translation_key=kind,
                translation_placeholders={
                    "name": self.name or "",
                    "group": group,
                    "reset": _format_reset(error),
                    "detail": str(error),
                },
            )

    def _adapt_interval(self) -> None:
        """Slow polling down while the rate budget is nearly spent."""
        low = self.client.budget.is_low(self._rate_resource)
        self.update_interval = (
            self._base_interval * SLOWDOWN_FACTOR if low else self._base_interval
        )


def _format_reset(error: GitHubError) -> str:
    """Return the local time the rate limit resets, or a dash when unknown."""
    reset_at = getattr(error, "reset_at", None)
    if reset_at is None:
        return "-"
    return dt_util.as_local(dt_util.utc_from_timestamp(reset_at)).strftime(
        "%Y-%m-%d %H:%M"
    )
