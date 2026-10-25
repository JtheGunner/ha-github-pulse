"""Persistent per-month cache that only fetches what is missing or stale."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import UTC, date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .analytics.history import MonthKey, months_back, needs_refresh
from .api import GitHubClient
from .const import DOMAIN, LOGGER

STORAGE_VERSION = 1


class MonthlyStore[T](ABC):
    """Hold one value per month, refreshed by the policy in ``needs_refresh``."""

    def __init__(self, hass: HomeAssistant, name: str, entry_id: str) -> None:
        """Create the store for one config entry."""
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.{name}.{entry_id}"
        )
        self.months: dict[MonthKey, T] = {}
        self._fetched_at: dict[MonthKey, datetime] = {}

    @abstractmethod
    async def _fetch(
        self, client: GitHubClient, login: str, keys: list[MonthKey], zone: ZoneInfo
    ) -> dict[MonthKey, T]:
        """Fetch the given months from GitHub."""

    @abstractmethod
    def _encode(self, value: T) -> dict[str, Any]:
        """Return a JSON-serialisable form of a month."""

    @abstractmethod
    def _decode(self, raw: dict[str, Any]) -> T:
        """Rebuild a month from its stored form."""

    async def async_load(self) -> None:
        """Load stored months; a corrupt file is discarded and refetched."""
        try:
            raw = await self._store.async_load()
            self._parse(raw or {})
        except KeyError, TypeError, ValueError:
            LOGGER.warning("Discarding unreadable %s; refetching", self._store.key)
            self.months.clear()
            self._fetched_at.clear()

    def _parse(self, raw: dict[str, Any]) -> None:
        months: dict[MonthKey, T] = {}
        fetched: dict[MonthKey, datetime] = {}
        for label, item in raw.get("months", {}).items():
            key = MonthKey.parse(label)
            months[key] = self._decode(item["value"])
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
        due = [
            key
            for key in months_back(today, years)
            if needs_refresh(key, self._fetched_at.get(key), today, now)
        ]
        if not due:
            return 0
        fetched = await self._fetch(client, login, due, zone)
        for key, value in fetched.items():
            self.months[key] = value
            self._fetched_at[key] = now
        await self._store.async_save(self._dump())
        return len(fetched)

    def _dump(self) -> dict[str, Any]:
        return {
            "months": {
                key.label: {
                    "value": self._encode(value),
                    "fetched_at": self._fetched_at[key].isoformat(),
                }
                for key, value in self.months.items()
            }
        }
