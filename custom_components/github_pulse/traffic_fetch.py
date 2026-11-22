"""Fetch the traffic of a repository (needs push access to the repository)."""

from __future__ import annotations

import asyncio

from .analytics.traffic import RepositoryTraffic, parse_traffic
from .api import GitHubClient, GitHubForbiddenError, GitHubNotFoundError


async def fetch_traffic(
    client: GitHubClient, full_name: str
) -> RepositoryTraffic | None:
    """Fetch views, clones, referrers and paths of the last 14 days.

    ``None`` when the token cannot read the traffic of this repository. Other
    errors propagate.
    """
    base = f"/repos/{full_name}/traffic"
    try:
        views, clones, referrers, paths = await asyncio.gather(
            client.rest_get(f"{base}/views"),
            client.rest_get(f"{base}/clones"),
            client.rest_get(f"{base}/popular/referrers"),
            client.rest_get(f"{base}/popular/paths"),
        )
    except GitHubForbiddenError, GitHubNotFoundError:
        return None
    return parse_traffic(views.data, clones.data, referrers.data, paths.data)
