"""Persistent store for monthly contribution totals."""

from __future__ import annotations

from typing import Any
from zoneinfo import ZoneInfo

from homeassistant.core import HomeAssistant

from .analytics.history import MonthKey, MonthStats
from .api import GitHubClient
from .history_fetch import fetch_months
from .monthly_store import MonthlyStore


class HistoryStore(MonthlyStore[MonthStats]):
    """Monthly commits, pull requests, issues, reviews and restricted counts."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        """Create the store."""
        super().__init__(hass, "history", entry_id)

    async def _fetch(
        self, client: GitHubClient, login: str, keys: list[MonthKey], zone: ZoneInfo
    ) -> dict[MonthKey, MonthStats]:
        return await fetch_months(client, login, keys, zone)

    def _encode(self, value: MonthStats) -> dict[str, Any]:
        return {
            "commits": value.commits,
            "pull_requests": value.pull_requests,
            "issues": value.issues,
            "reviews": value.reviews,
            "restricted": value.restricted,
        }

    def _decode(self, raw: dict[str, Any]) -> MonthStats:
        return MonthStats(**raw)
