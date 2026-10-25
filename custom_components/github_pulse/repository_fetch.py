"""Fetch tracked repositories with one batched GraphQL request."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .api import GitHubClient

BATCH_SIZE = 50

_FIELDS = """
  nameWithOwner stargazerCount forkCount isArchived pushedAt
  watchers { totalCount }
  issues(states: OPEN) { totalCount }
  pullRequests(states: OPEN) { totalCount }
  defaultBranchRef {
    name
    target { ... on Commit { committedDate statusCheckRollup { state } } }
  }
  latestRelease {
    tagName name url publishedAt isPrerelease
    releaseAssets(first: 100) { nodes { downloadCount } }
  }
"""


@dataclass(frozen=True, slots=True)
class ReleaseInfo:
    """The latest published release of a repository."""

    tag: str
    name: str | None
    url: str
    published_at: datetime | None
    prerelease: bool
    downloads: int


@dataclass(frozen=True, slots=True)
class RepositorySnapshot:
    """The state of one tracked repository."""

    full_name: str
    stars: int
    forks: int
    watchers: int
    open_issues: int
    open_pull_requests: int
    archived: bool
    pushed_at: datetime | None
    default_branch: str | None
    last_commit_at: datetime | None
    ci_state: str | None
    latest_release: ReleaseInfo | None


def build_query(repositories: Sequence[str]) -> tuple[str, dict[str, str]]:
    """Return one query with a ``repository`` alias per name, plus its variables."""
    declarations: list[str] = []
    selections: list[str] = []
    variables: dict[str, str] = {}
    for index, full_name in enumerate(repositories):
        owner, name = full_name.split("/")
        declarations += [f"$o{index}: String!", f"$n{index}: String!"]
        variables[f"o{index}"], variables[f"n{index}"] = owner, name
        selections.append(
            f"r{index}: repository(owner: $o{index}, name: $n{index}) {{ {_FIELDS} }}"
        )
    return f"query({', '.join(declarations)}) {{ {' '.join(selections)} }}", variables


def _time(value: str | None) -> datetime | None:
    return None if value is None else datetime.fromisoformat(value)


def _release(raw: dict[str, Any] | None) -> ReleaseInfo | None:
    if raw is None:
        return None
    assets = raw.get("releaseAssets", {}).get("nodes") or []
    return ReleaseInfo(
        tag=raw["tagName"],
        name=raw.get("name"),
        url=raw["url"],
        published_at=_time(raw.get("publishedAt")),
        prerelease=bool(raw.get("isPrerelease")),
        downloads=sum(asset["downloadCount"] for asset in assets),
    )


def parse_snapshot(raw: dict[str, Any]) -> RepositorySnapshot:
    """Turn one repository object of the response into a snapshot."""
    branch = raw.get("defaultBranchRef") or {}
    commit = branch.get("target") or {}
    rollup = commit.get("statusCheckRollup") or {}
    return RepositorySnapshot(
        full_name=raw["nameWithOwner"],
        stars=raw["stargazerCount"],
        forks=raw["forkCount"],
        watchers=raw["watchers"]["totalCount"],
        open_issues=raw["issues"]["totalCount"],
        open_pull_requests=raw["pullRequests"]["totalCount"],
        archived=bool(raw["isArchived"]),
        pushed_at=_time(raw.get("pushedAt")),
        default_branch=branch.get("name"),
        last_commit_at=_time(commit.get("committedDate")),
        ci_state=rollup.get("state"),
        latest_release=_release(raw.get("latestRelease")),
    )


async def fetch_snapshots(
    client: GitHubClient, repositories: Sequence[str]
) -> dict[str, RepositorySnapshot | None]:
    """Fetch every repository; one that cannot be read maps to ``None``.

    All names go into one request (in batches of ``BATCH_SIZE`` for very long
    lists), so tracking another repository adds no request.
    """
    result: dict[str, RepositorySnapshot | None] = {}
    for start in range(0, len(repositories), BATCH_SIZE):
        batch = repositories[start : start + BATCH_SIZE]
        query, variables = build_query(batch)
        response = await client.graphql(query, variables)
        for index, full_name in enumerate(batch):
            raw = response.data.get(f"r{index}")
            result[full_name] = None if raw is None else parse_snapshot(raw)
    return result


async def fetch_total_downloads(client: GitHubClient, full_name: str) -> int:
    """Sum the download counts of every release asset (REST, ETag cached)."""
    releases = await client.rest_get_pages(
        f"/repos/{full_name}/releases", {"per_page": "100"}
    )
    return sum(
        asset["download_count"]
        for release in releases
        for asset in release.get("assets", [])
    )
