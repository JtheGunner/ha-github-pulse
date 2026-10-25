"""Pull request searches, which use GitHub's separate and much smaller budget."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .analytics.events import PullRequestRef
from .api import GitHubClient, GitHubRateLimitError

SEARCH_RESOURCE = "search"
PAGE_SIZE = 30
_REPOS_PREFIX = "https://api.github.com/repos/"


@dataclass(frozen=True, slots=True)
class SearchCounts:
    """Open pull requests that involve the account, plus recent merges."""

    review_requested: int
    authored_open: int
    review_pulls: tuple[PullRequestRef, ...] = field(default=())
    merged_pulls: tuple[PullRequestRef, ...] = field(default=())


def _ref(item: dict[str, Any]) -> PullRequestRef:
    return PullRequestRef(
        id=item["id"],
        repository=str(item.get("repository_url", "")).removeprefix(_REPOS_PREFIX),
        number=item["number"],
        title=item.get("title", ""),
        url=item.get("html_url", ""),
    )


async def _search(
    client: GitHubClient, query: str, per_page: int
) -> tuple[int, tuple[PullRequestRef, ...]]:
    response = await client.rest_get(
        "/search/issues",
        {"q": query, "per_page": str(per_page), "sort": "updated", "order": "desc"},
    )
    items = tuple(_ref(item) for item in response.data.get("items", []))
    return int(response.data["total_count"]), items


def ensure_search_budget(client: GitHubClient) -> None:
    """Raise ``GitHubRateLimitError`` while the search budget is nearly spent."""
    if client.budget.is_low(SEARCH_RESOURCE):
        budget = client.budget.get(SEARCH_RESOURCE)
        raise GitHubRateLimitError(
            "search rate budget is low",
            reset_at=None if budget is None else budget.reset_at,
        )


async def fetch_search_counts(client: GitHubClient, login: str) -> SearchCounts:
    """Count pull requests awaiting review and own open ones; list recent merges.

    Raises ``GitHubRateLimitError`` without calling GitHub while the search
    budget is nearly spent, so the caller keeps the last value.
    """
    ensure_search_budget(client)
    review_total, review_pulls = await _search(
        client, f"is:pr is:open archived:false review-requested:{login}", PAGE_SIZE
    )
    authored_total, _ = await _search(
        client, f"is:pr is:open archived:false author:{login}", 1
    )
    _, merged_pulls = await _search(
        client, f"is:pr is:merged author:{login}", PAGE_SIZE
    )
    return SearchCounts(review_total, authored_total, review_pulls, merged_pulls)
