"""Fetch tracked repositories with one batched GraphQL request."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from .analytics.periods import (
    DateRange,
    like_for_like_previous_month,
    like_for_like_previous_year,
    month_to_date,
    to_utc_window,
)
from .api import GitHubClient

BATCH_SIZE = 50
COMMIT_PAGE = 100
_TIME = "%Y-%m-%dT%H:%M:%SZ"

_FIELDS = """
  nameWithOwner stargazerCount forkCount isArchived pushedAt
  watchers { totalCount }
  issues(states: OPEN) { totalCount }
  pullRequests(states: OPEN) { totalCount }
  defaultBranchRef {
    name
    target {
      ... on Commit {
        committedDate statusCheckRollup { state }
        %(history)s
      }
    }
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
class RepositoryActivity:
    """Commit activity of a repository on its default branch, all authors.

    The comparison counts cover the same number of days as ``elapsed_days``, so
    a partial month is never compared with a full one.
    """

    commits_this_month: int
    commits_previous_month: int
    commits_previous_year: int
    active_days: int
    elapsed_days: int
    truncated: bool


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
    activity: RepositoryActivity | None = None


def _history(alias: str, rng: DateRange, zone: ZoneInfo, *, nodes: bool) -> str:
    start, end = to_utc_window(rng, zone)
    window = f'since: "{start:{_TIME}}", until: "{end:{_TIME}}"'
    selection = "totalCount nodes { committedDate }" if nodes else "totalCount"
    first = f", first: {COMMIT_PAGE}" if nodes else ""
    return f"{alias}: history({window}{first}) {{ {selection} }}"


def _history_fields(today: date, zone: ZoneInfo) -> str:
    return " ".join(
        [
            _history("thisMonth", month_to_date(today), zone, nodes=True),
            _history(
                "previousMonth", like_for_like_previous_month(today), zone, nodes=False
            ),
            _history(
                "previousYear", like_for_like_previous_year(today), zone, nodes=False
            ),
        ]
    )


def build_query(
    repositories: Sequence[str], today: date, zone: ZoneInfo
) -> tuple[str, dict[str, str]]:
    """Return one query with a ``repository`` alias per name, plus its variables.

    ``today`` and ``zone`` set the commit windows (see :class:`RepositoryActivity`).
    """
    fields = _FIELDS % {"history": _history_fields(today, zone)}
    declarations: list[str] = []
    selections: list[str] = []
    variables: dict[str, str] = {}
    for index, full_name in enumerate(repositories):
        owner, name = full_name.split("/")
        declarations += [f"$o{index}: String!", f"$n{index}: String!"]
        variables[f"o{index}"], variables[f"n{index}"] = owner, name
        selections.append(
            f"r{index}: repository(owner: $o{index}, name: $n{index}) {{ {fields} }}"
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


def _activity(
    commit: dict[str, Any], today: date, zone: ZoneInfo
) -> RepositoryActivity | None:
    this_month = commit.get("thisMonth")
    if this_month is None:
        return None
    nodes = this_month["nodes"]
    days = {
        datetime.fromisoformat(node["committedDate"]).astimezone(zone).date()
        for node in nodes
    }
    return RepositoryActivity(
        commits_this_month=this_month["totalCount"],
        commits_previous_month=commit["previousMonth"]["totalCount"],
        commits_previous_year=commit["previousYear"]["totalCount"],
        active_days=len(days),
        elapsed_days=today.day,
        truncated=this_month["totalCount"] > len(nodes),
    )


def parse_snapshot(
    raw: dict[str, Any], today: date, zone: ZoneInfo
) -> RepositorySnapshot:
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
        activity=_activity(commit, today, zone),
    )


async def fetch_snapshots(
    client: GitHubClient,
    repositories: Sequence[str],
    *,
    today: date,
    zone: ZoneInfo,
) -> dict[str, RepositorySnapshot | None]:
    """Fetch every repository; one that cannot be read maps to ``None``.

    All names go into one request (in batches of ``BATCH_SIZE`` for very long
    lists), so tracking another repository adds no request.
    """
    result: dict[str, RepositorySnapshot | None] = {}
    for start in range(0, len(repositories), BATCH_SIZE):
        batch = repositories[start : start + BATCH_SIZE]
        query, variables = build_query(batch, today, zone)
        response = await client.graphql(query, variables)
        for index, full_name in enumerate(batch):
            raw = response.data.get(f"r{index}")
            result[full_name] = (
                None if raw is None else parse_snapshot(raw, today, zone)
            )
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
