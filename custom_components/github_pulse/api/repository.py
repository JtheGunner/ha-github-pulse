"""Repository lookups used when a repository is added."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .client import GitHubClient
from .errors import GitHubForbiddenError

_NAME = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_LIST_LIMIT = 100
_LIST_QUERY = (
    f"query{{viewer{{repositories(first:{_LIST_LIMIT},isArchived:false,"
    "affiliations:[OWNER,COLLABORATOR,ORGANIZATION_MEMBER],"
    "ownerAffiliations:[OWNER,COLLABORATOR,ORGANIZATION_MEMBER],"
    "orderBy:{field:PUSHED_AT,direction:DESC}){nodes{nameWithOwner}}}}"
)


@dataclass(frozen=True, slots=True)
class RepositoryInfo:
    """The facts about a repository needed to track it."""

    full_name: str
    default_branch: str
    private: bool
    archived: bool


def parse_repository_name(value: str) -> tuple[str, str]:
    """Split ``owner/name``; raise ``ValueError`` for anything else."""
    cleaned = value.strip().removeprefix("https://github.com/").strip("/")
    cleaned = cleaned.removesuffix(".git")
    if not _NAME.match(cleaned):
        msg = f"{value!r} is not in the form owner/name"
        raise ValueError(msg)
    owner, name = cleaned.split("/")
    return owner, name


async def fetch_repository(
    client: GitHubClient, owner: str, name: str
) -> RepositoryInfo:
    """Fetch a repository; errors (not found, forbidden, ...) propagate."""
    response = await client.rest_get(f"/repos/{owner}/{name}")
    data = response.data
    return RepositoryInfo(
        full_name=data["full_name"],
        default_branch=data["default_branch"],
        private=bool(data["private"]),
        archived=bool(data["archived"]),
    )


async def can_read_actions(client: GitHubClient, full_name: str) -> bool:
    """Return whether the token may read workflow runs of the repository."""
    try:
        await client.rest_get(f"/repos/{full_name}/actions/runs", {"per_page": "1"})
    except GitHubForbiddenError:
        return False
    return True


async def list_accessible_repositories(client: GitHubClient) -> tuple[str, ...]:
    """Return the most recently pushed repositories the token can read.

    Archived repositories are left out. A classic token lists everything it can
    see; a fine-grained token lists the repositories selected for it. Errors
    propagate so the caller can fall back to typing a name.
    """
    result = await client.graphql(_LIST_QUERY)
    viewer = (result.data or {}).get("viewer") or {}
    nodes = (viewer.get("repositories") or {}).get("nodes") or []
    return tuple(node["nameWithOwner"] for node in nodes if node)
