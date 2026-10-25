"""Persistent store for the monthly language estimate."""

from __future__ import annotations

from typing import Any
from zoneinfo import ZoneInfo

from homeassistant.core import HomeAssistant

from .analytics.history import MonthKey
from .analytics.languages import LanguageMonth
from .api import GitHubClient
from .language_fetch import fetch_language_months
from .monthly_store import MonthlyStore


class LanguageStore(MonthlyStore[LanguageMonth]):
    """Raw language scores per month; the weighting is chosen when reading."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        """Create the store."""
        super().__init__(hass, "languages", entry_id)

    async def _fetch(
        self, client: GitHubClient, login: str, keys: list[MonthKey], zone: ZoneInfo
    ) -> dict[MonthKey, LanguageMonth]:
        return await fetch_language_months(client, login, keys, zone)

    def _encode(self, value: LanguageMonth) -> dict[str, Any]:
        return {
            "commit_scores": dict(value.commit_scores),
            "repo_scores": dict(value.repo_scores),
            "unclassified_commits": value.unclassified_commits,
            "repositories": value.repositories,
            "truncated": value.truncated,
        }

    def _decode(self, raw: dict[str, Any]) -> LanguageMonth:
        return LanguageMonth(
            commit_scores={str(k): float(v) for k, v in raw["commit_scores"].items()},
            repo_scores={str(k): float(v) for k, v in raw["repo_scores"].items()},
            unclassified_commits=int(raw["unclassified_commits"]),
            repositories=int(raw["repositories"]),
            truncated=bool(raw["truncated"]),
        )
