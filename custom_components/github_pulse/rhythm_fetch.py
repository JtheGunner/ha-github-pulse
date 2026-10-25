"""Fetch the timestamps of the account's recent events."""

from __future__ import annotations

from datetime import datetime

from .api import GitHubClient

PAGE_SIZE = "100"
MAX_PAGES = 3  # GitHub keeps at most 300 events


async def fetch_event_times(client: GitHubClient, login: str) -> list[datetime]:
    """Return the creation time of up to 300 recent events, newest first."""
    items = await client.rest_get_pages(
        f"/users/{login}/events", {"per_page": PAGE_SIZE}, max_pages=MAX_PAGES
    )
    return [
        datetime.fromisoformat(item["created_at"])
        for item in items
        if isinstance(item, dict) and item.get("created_at")
    ]
