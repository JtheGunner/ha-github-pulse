"""Identify a token and check which modules it can serve.

Used by the config flow. Nothing here imports Home Assistant.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from ..const import MODULE_PROFILE, MODULE_REPOSITORIES
from .client import GitHubClient
from .errors import GitHubForbiddenError, GitHubGraphQLError, GitHubNotFoundError

FINE_GRAINED_PREFIX = "github_pat_"

_PROFILE_QUERY = (
    "query($login:String!){user(login:$login){"
    "contributionsCollection{totalCommitContributions}}}"
)
_REPOSITORIES_QUERY = "query{viewer{repositories(first:1){totalCount}}}"


class TokenType(StrEnum):
    """Kind of personal access token."""

    CLASSIC = "classic"
    FINE_GRAINED = "fine_grained"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class TokenInfo:
    """Who a token belongs to and what kind of token it is."""

    login: str
    token_type: TokenType
    scopes: frozenset[str]


def detect_token_type(token: str, scopes_header: str | None) -> TokenType:
    """Classify a token from its prefix and the ``X-OAuth-Scopes`` header."""
    if token.startswith(FINE_GRAINED_PREFIX):
        return TokenType.FINE_GRAINED
    if scopes_header is not None:
        return TokenType.CLASSIC
    return TokenType.UNKNOWN


async def fetch_token_info(client: GitHubClient, token: str) -> TokenInfo:
    """Return the owner and type of the token.

    Raises the client's typed errors when the token is rejected.
    """
    response = await client.rest_get("/user")
    scopes_header = response.headers.get("X-OAuth-Scopes")
    scopes = frozenset(
        scope.strip() for scope in (scopes_header or "").split(",") if scope.strip()
    )
    return TokenInfo(
        login=str(response.data["login"]),
        token_type=detect_token_type(token, scopes_header),
        scopes=scopes,
    )


async def probe_module(client: GitHubClient, module: str, login: str) -> bool:
    """Return whether the token can serve a module.

    A missing permission is a normal answer (``False``); authentication,
    transport and rate-limit errors propagate to the caller.
    """
    if module == MODULE_PROFILE:
        query, variables = _PROFILE_QUERY, {"login": login}
    elif module == MODULE_REPOSITORIES:
        query, variables = _REPOSITORIES_QUERY, {}
    else:
        msg = f"unknown module {module!r}"
        raise ValueError(msg)
    try:
        await client.graphql(query, variables)
    except GitHubForbiddenError, GitHubNotFoundError, GitHubGraphQLError:
        return False
    return True
