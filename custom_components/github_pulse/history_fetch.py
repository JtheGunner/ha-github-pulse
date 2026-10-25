"""Fetch monthly contribution totals via aliased GraphQL windows."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from zoneinfo import ZoneInfo

from .analytics.history import MonthKey, MonthStats, chunk_months
from .analytics.periods import DateRange, month_range, to_utc_window
from .api import GitHubClient

_TIME = "%Y-%m-%dT%H:%M:%SZ"
_FIELDS = (
    "totalCommitContributions totalPullRequestContributions "
    "totalIssueContributions totalPullRequestReviewContributions "
    "restrictedContributionsCount"
)


def _alias(key: MonthKey) -> str:
    return f"m{key.year:04d}{key.month:02d}"


def build_ranges_query(ranges: Mapping[str, DateRange], zone: ZoneInfo) -> str:
    """Return one query with a ``contributionsCollection`` alias per range."""
    parts = []
    for alias, rng in ranges.items():
        start, end = to_utc_window(rng, zone)
        window = f'from: "{start:{_TIME}}", to: "{end:{_TIME}}"'
        parts.append(f"{alias}: contributionsCollection({window}) {{ {_FIELDS} }}")
    return "query($login: String!) { user(login: $login) { " + " ".join(parts) + " } }"


def build_query(keys: list[MonthKey], zone: ZoneInfo) -> str:
    """Return a query with one alias per whole calendar month."""
    return build_ranges_query(
        {_alias(key): month_range(key.year, key.month) for key in keys}, zone
    )


def _stats(raw: dict[str, Any]) -> MonthStats:
    return MonthStats(
        commits=raw["totalCommitContributions"],
        pull_requests=raw["totalPullRequestContributions"],
        issues=raw["totalIssueContributions"],
        reviews=raw["totalPullRequestReviewContributions"],
        restricted=raw["restrictedContributionsCount"],
    )


async def fetch_ranges(
    client: GitHubClient,
    login: str,
    ranges: Mapping[str, DateRange],
    zone: ZoneInfo,
) -> dict[str, MonthStats]:
    """Fetch totals for arbitrary day ranges (each at most one year) in one request."""
    response = await client.graphql(build_ranges_query(ranges, zone), {"login": login})
    user = response.data["user"]
    return {alias: _stats(user[alias]) for alias in ranges}


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
