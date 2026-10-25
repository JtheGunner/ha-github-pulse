"""Persistent store for closed months of contribution history."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .analytics.history import MonthKey, MonthStats, months_back, needs_refresh
from .api import GitHubClient
from .const import DOMAIN, LOGGER
from .history_fetch import fetch_months

STORAGE_VERSION = 1


class HistoryStore:
    """Hold monthly stats, fetching only what is missing or stale."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        """Create the store for one config entry."""
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.history.{entry_id}"
        )
        self.months: dict[MonthKey, MonthStats] = {}
        self._fetched_at: dict[MonthKey, datetime] = {}

    async def async_load(self) -> None:
        """Load stored months; a corrupt file is discarded and refetched."""
        try:
            raw = await self._store.async_load()
            self._parse(raw or {})
        except KeyError, TypeError, ValueError:
            LOGGER.warning("Discarding unreadable history store; refetching")
            self.months.clear()
            self._fetched_at.clear()

    def _parse(self, raw: dict[str, Any]) -> None:
        months: dict[MonthKey, MonthStats] = {}
        fetched: dict[MonthKey, datetime] = {}
        for label, item in raw.get("months", {}).items():
            key = MonthKey.parse(label)
            months[key] = MonthStats(**item["stats"])
            fetched[key] = datetime.fromisoformat(item["fetched_at"])
        self.months, self._fetched_at = months, fetched

    async def async_refresh(
        self,
        client: GitHubClient,
        login: str,
        zone: ZoneInfo,
        *,
        today: date,
        years: int,
        now: datetime | None = None,
    ) -> int:
        """Fetch missing and stale months and save; return how many were fetched."""
        now = now or datetime.now(UTC)
        wanted = months_back(today, years)
        due = [
            key
            for key in wanted
            if needs_refresh(key, self._fetched_at.get(key), today, now)
        ]
        if not due:
            return 0
        fetched = await fetch_months(client, login, due, zone)
        for key, stats in fetched.items():
            self.months[key] = stats
            self._fetched_at[key] = now
        await self._store.async_save(self._dump())
        return len(fetched)

    def _dump(self) -> dict[str, Any]:
        return {
            "months": {
                key.label: {
                    "stats": {
                        "commits": s.commits,
                        "pull_requests": s.pull_requests,
                        "issues": s.issues,
                        "reviews": s.reviews,
                        "restricted": s.restricted,
                    },
                    "fetched_at": self._fetched_at[key].isoformat(),
                }
                for key, s in self.months.items()
            }
        }
