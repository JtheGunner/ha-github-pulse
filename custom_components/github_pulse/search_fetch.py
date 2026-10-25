"""Counts from the search API, which has its own, much smaller rate budget."""

from __future__ import annotations

from dataclasses import dataclass

from .api import GitHubClient, GitHubRateLimitError

SEARCH_RESOURCE = "search"


@dataclass(frozen=True, slots=True)
class SearchCounts:
    """Open pull requests that involve the account."""

    review_requested: int
    authored_open: int


async def _count(client: GitHubClient, query: str) -> int:
    response = await client.rest_get("/search/issues", {"q": query, "per_page": "1"})
    return int(response.data["total_count"])


async def fetch_search_counts(client: GitHubClient, login: str) -> SearchCounts:
    """Count pull requests awaiting the account's review and its own open ones.

    Raises ``GitHubRateLimitError`` without calling GitHub while the search
    budget is nearly spent, so the caller keeps the last value.
    """
    if client.budget.is_low(SEARCH_RESOURCE):
        budget = client.budget.get(SEARCH_RESOURCE)
        raise GitHubRateLimitError(
            "search rate budget is low",
            reset_at=None if budget is None else budget.reset_at,
        )
    review_requested = await _count(
        client, f"is:pr is:open archived:false review-requested:{login}"
    )
    authored = await _count(client, f"is:pr is:open archived:false author:{login}")
    return SearchCounts(review_requested, authored)
