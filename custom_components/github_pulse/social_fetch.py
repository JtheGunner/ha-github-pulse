"""Fetch account follower and following counts."""

from __future__ import annotations

from .api import GitHubClient, GitHubGraphQLError


async def fetch_social_counts(client: GitHubClient, login: str) -> dict[str, int]:
    """Fetch both public counts in one GraphQL request."""
    query = (
        "query($login: String!) { user(login: $login) { "
        "followers { totalCount } following { totalCount } } }"
    )
    response = await client.graphql(query, {"login": login})
    user = response.data["user"]
    if user is None:
        raise GitHubGraphQLError(
            "GitHub user data is unavailable", errors=response.errors
        )
    return {key: user[key]["totalCount"] for key in ("followers", "following")}
