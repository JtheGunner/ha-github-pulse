"""Fetch monthly contribution totals via aliased GraphQL windows."""

from __future__ import annotations

from typing import Any
from zoneinfo import ZoneInfo

from .analytics.history import MonthKey, MonthStats, chunk_months
from .analytics.periods import month_range, to_utc_window
from .api import GitHubClient

_TIME = "%Y-%m-%dT%H:%M:%SZ"
_FIELDS = (
    "totalCommitContributions totalPullRequestContributions "
    "totalIssueContributions totalPullRequestReviewContributions "
    "restrictedContributionsCount"
)


def _alias(key: MonthKey) -> str:
    return f"m{key.year:04d}{key.month:02d}"


def build_query(keys: list[MonthKey], zone: ZoneInfo) -> str:
    """Return one query with a ``contributionsCollection`` alias per month."""
    parts = []
    for key in keys:
        start, end = to_utc_window(month_range(key.year, key.month), zone)
        window = f'from: "{start:{_TIME}}", to: "{end:{_TIME}}"'
        parts.append(
            f"{_alias(key)}: contributionsCollection({window}) {{ {_FIELDS} }}"
        )
    return "query($login: String!) { user(login: $login) { " + " ".join(parts) + " } }"


def _stats(raw: dict[str, Any]) -> MonthStats:
    return MonthStats(
        commits=raw["totalCommitContributions"],
        pull_requests=raw["totalPullRequestContributions"],
        issues=raw["totalIssueContributions"],
        reviews=raw["totalPullRequestReviewContributions"],
        restricted=raw["restrictedContributionsCount"],
    )


async def fetch_months(
    client: GitHubClient, login: str, keys: list[MonthKey], zone: ZoneInfo
) -> dict[MonthKey, MonthStats]:
    """Fetch the given months, one request per chunk of up to twelve months."""
    result: dict[MonthKey, MonthStats] = {}
    for chunk in chunk_months(keys):
        response = await client.graphql(build_query(chunk, zone), {"login": login})
        user = response.data["user"]
        for key in chunk:
            result[key] = _stats(user[_alias(key)])
    return result
