"""Coordinator for the account-wide profile statistics."""

from __future__ import annotations

from collections.abc import Collection, Mapping
from dataclasses import dataclass
from datetime import date
from typing import Any
from zoneinfo import ZoneInfo

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from .analytics.history import MonthKey, MonthStats
from .analytics.languages import LanguageMonth
from .analytics.periods import (
    like_for_like_previous_month,
    like_for_like_previous_year,
    month_to_date,
)
from .analytics.rhythm import Rhythm, rhythm
from .const import WEIGHTING_COMMITS
from .coordinator import GitHubPulseCoordinator, GroupFetcher
from .history_fetch import fetch_daily, fetch_ranges
from .history_store import HistoryStore
from .language_store import LanguageStore
from .models import GitHubPulseConfigEntry
from .rhythm_fetch import fetch_event_times
from .search_fetch import SearchCounts, fetch_search_counts
from .settings import Settings
from .statistics_import import build_series, import_series

GROUP_CURRENT = "current"
GROUP_HISTORY = "history"
GROUP_CALENDAR = "calendar"
GROUP_LANGUAGES = "languages"
GROUP_SEARCH = "search"
GROUP_RHYTHM = "rhythm"
PROFILE_GROUPS = frozenset(
    {
        GROUP_CURRENT,
        GROUP_HISTORY,
        GROUP_CALENDAR,
        GROUP_LANGUAGES,
        GROUP_SEARCH,
        GROUP_RHYTHM,
    }
)


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
        languages: LanguageStore,
        active_groups: Collection[str] = PROFILE_GROUPS,
    ) -> None:
        """Create the coordinator."""
        self._settings = settings
        self._history = history
        self._languages = languages
        groups: dict[str, GroupFetcher] = {
            GROUP_CURRENT: self._fetch_current,
            GROUP_HISTORY: self._fetch_history,
            GROUP_CALENDAR: self._fetch_calendar,
            GROUP_LANGUAGES: self._fetch_languages,
            GROUP_SEARCH: self._fetch_search,
            GROUP_RHYTHM: self._fetch_rhythm,
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

    async def _async_update_data(self) -> dict[str, Any]:
        """Refresh the groups, then import statistics when the user opted in."""
        data = await super()._async_update_data()
        if self._settings.import_statistics:
            self._import_statistics(data)
        return data

    def _import_statistics(self, data: Mapping[str, Any]) -> None:
        series = build_series(
            self.config_entry.runtime_data.login,
            data.get(GROUP_HISTORY, {}),
            data.get(GROUP_LANGUAGES, {}),
            zone=self._settings.contribution_time_zone,
            include_restricted=self._settings.include_restricted,
            by_commits=self._settings.language_weighting == WEIGHTING_COMMITS,
        )
        import_series(self.hass, series)

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

    async def _fetch_languages(self) -> dict[MonthKey, LanguageMonth]:
        await self._languages.async_refresh(
            self.client,
            self.config_entry.runtime_data.login,
            self._settings.contribution_time_zone,
            today=self.today(),
            years=self._settings.history_years,
        )
        return dict(self._languages.months)

    async def _fetch_search(self) -> SearchCounts:
        return await fetch_search_counts(
            self.client, self.config_entry.runtime_data.login
        )

    async def _fetch_rhythm(self) -> Rhythm:
        times = await fetch_event_times(
            self.client, self.config_entry.runtime_data.login
        )
        return rhythm(times, dt_util.get_default_time_zone())
