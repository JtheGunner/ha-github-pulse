"""Fetch per-repository commits and languages for the language estimate."""

from __future__ import annotations

from typing import Any
from zoneinfo import ZoneInfo

from .analytics.history import MonthKey, chunk_months
from .analytics.languages import COMMIT_CAP, LanguageMonth, RepoActivity, estimate_month
from .analytics.periods import month_range, to_utc_window
from .api import GitHubClient

_TIME = "%Y-%m-%dT%H:%M:%SZ"
_REPO = (
    "commitContributionsByRepository(maxRepositories: 100) { "
    "contributions { totalCount } "
    "repository { languages(first: 20, orderBy: {field: SIZE, direction: DESC}) "
    "{ edges { size node { name } } } } }"
)


def _alias(key: MonthKey) -> str:
    return f"m{key.year:04d}{key.month:02d}"


def build_language_query(keys: list[MonthKey], zone: ZoneInfo) -> str:
    """Return one query with a ``contributionsCollection`` alias per month."""
    parts = []
    for key in keys:
        start, end = to_utc_window(month_range(key.year, key.month), zone)
        window = f'from: "{start:{_TIME}}", to: "{end:{_TIME}}"'
        parts.append(f"{_alias(key)}: contributionsCollection({window}) {{ {_REPO} }}")
    return "query($login: String!) { user(login: $login) { " + " ".join(parts) + " } }"


def parse_repositories(items: list[dict[str, Any]]) -> list[RepoActivity]:
    """Turn the API's per-repository entries into estimator input."""
    repos = []
    for item in items:
        edges = (item.get("repository") or {}).get("languages", {}).get("edges") or []
        languages = {edge["node"]["name"]: edge["size"] for edge in edges}
        repos.append(RepoActivity(item["contributions"]["totalCount"], languages))
    return repos


async def fetch_language_months(
    client: GitHubClient, login: str, keys: list[MonthKey], zone: ZoneInfo
) -> dict[MonthKey, LanguageMonth]:
    """Fetch and estimate the given months, twelve per request."""
    result: dict[MonthKey, LanguageMonth] = {}
    for chunk in chunk_months(keys):
        response = await client.graphql(
            build_language_query(chunk, zone), {"login": login}
        )
        user = response.data["user"]
        for key in chunk:
            repos = parse_repositories(
                user[_alias(key)]["commitContributionsByRepository"]
            )
            result[key] = estimate_month(repos, COMMIT_CAP)
    return result
