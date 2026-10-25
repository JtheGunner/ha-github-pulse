"""Fetch the figures behind the work-in-progress sensors."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .analytics.workflow import average_hours_to_merge, stale_cutoff
from .api import GitHubClient
from .search_fetch import ensure_search_budget

MERGED_SAMPLE = 50


@dataclass(frozen=True, slots=True)
class WipStats:
    """How quickly pull requests merge and how many open ones have gone quiet."""

    hours_to_merge: float | None
    merged_sample: int
    stale_open: int


def _timestamp(value: Any) -> datetime | None:
    return datetime.fromisoformat(value) if isinstance(value, str) else None


async def fetch_wip(client: GitHubClient, login: str, now: datetime) -> WipStats:
    """Average the merge time of the last merged pull requests; count stale ones.

    Raises ``GitHubRateLimitError`` while the search budget is nearly spent.
    """
    ensure_search_budget(client)
    merged = await client.rest_get(
        "/search/issues",
        {
            "q": f"is:pr is:merged author:{login}",
            "per_page": str(MERGED_SAMPLE),
            "sort": "updated",
            "order": "desc",
        },
    )
    pairs = [
        (
            opened,
            _timestamp((item.get("pull_request") or {}).get("merged_at")),
        )
        for item in merged.data.get("items", [])
        if (opened := _timestamp(item.get("created_at"))) is not None
    ]
    stale = await client.rest_get(
        "/search/issues",
        {
            "q": (
                f"is:pr is:open archived:false author:{login} "
                f"updated:<{stale_cutoff(now)}"
            ),
            "per_page": "1",
        },
    )
    return WipStats(
        hours_to_merge=average_hours_to_merge(pairs),
        merged_sample=sum(1 for _, merged_at in pairs if merged_at is not None),
        stale_open=int(stale.data["total_count"]),
    )
