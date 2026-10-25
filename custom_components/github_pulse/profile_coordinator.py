"""Coordinator for the account-wide profile statistics."""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
from datetime import date
from zoneinfo import ZoneInfo

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .analytics.history import MonthKey, MonthStats
from .analytics.periods import (
    like_for_like_previous_month,
    like_for_like_previous_year,
    month_to_date,
)
from .coordinator import GitHubPulseCoordinator, GroupFetcher
from .history_fetch import fetch_daily, fetch_ranges
from .history_store import HistoryStore
from .models import GitHubPulseConfigEntry
from .settings import Settings

GROUP_CURRENT = "current"
GROUP_HISTORY = "history"
GROUP_CALENDAR = "calendar"
PROFILE_GROUPS = frozenset({GROUP_CURRENT, GROUP_HISTORY, GROUP_CALENDAR})


@dataclass(frozen=True, slots=True)
class CurrentPeriods:
    """The month so far next to the equally long spans it is compared with."""

    today: date
    this_month: MonthStats
    previous_month: MonthStats
    previous_year: MonthStats


class ProfileCoordinator(GitHubPulseCoordinator):
    """Fetch the current period and keep the monthly history up to date."""

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: GitHubPulseConfigEntry,
        *,
        settings: Settings,
        history: HistoryStore,
        active_groups: Collection[str] = PROFILE_GROUPS,
    ) -> None:
        """Create the coordinator."""
        self._settings = settings
        self._history = history
        groups: dict[str, GroupFetcher] = {
            GROUP_CURRENT: self._fetch_current,
            GROUP_HISTORY: self._fetch_history,
            GROUP_CALENDAR: self._fetch_calendar,
        }
        super().__init__(
            hass,
            config_entry,
            name="GitHub Pulse profile",
            client=config_entry.runtime_data.client,
            update_interval=settings.profile_interval,
            groups=groups,
            active_groups=active_groups,
        )

    @property
    def settings(self) -> Settings:
        """Return the options this coordinator was created with."""
        return self._settings

    def today(self) -> date:
        """Return today's date in the contribution time zone."""
        return dt_util.utcnow().astimezone(self._settings.contribution_time_zone).date()

    async def _fetch_current(self) -> CurrentPeriods:
        today = self.today()
        ranges = {
            "current": month_to_date(today),
            "lastMonth": like_for_like_previous_month(today),
            "lastYear": like_for_like_previous_year(today),
        }
        stats = await fetch_ranges(
            self.client,
            self.config_entry.runtime_data.login,
            ranges,
            self._settings.contribution_time_zone,
        )
        return CurrentPeriods(
            today, stats["current"], stats["lastMonth"], stats["lastYear"]
        )

    async def _fetch_history(self) -> dict[MonthKey, MonthStats]:
        zone: ZoneInfo = self._settings.contribution_time_zone
        await self._history.async_refresh(
            self.client,
            self.config_entry.runtime_data.login,
            zone,
            today=self.today(),
            years=self._settings.history_years,
        )
        return dict(self._history.months)

    async def _fetch_calendar(self) -> dict[date, int]:
        return await fetch_daily(
            self.client,
            self.config_entry.runtime_data.login,
            self.today(),
            self._settings.contribution_time_zone,
        )
