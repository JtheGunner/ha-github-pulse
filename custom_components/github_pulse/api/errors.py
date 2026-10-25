"""Typed errors raised by the GitHub API client."""

from __future__ import annotations


class GitHubError(Exception):
    """Base class for every error raised by the API client."""

    def __init__(self, message: str, *, status: int | None = None) -> None:
        """Store the message and the HTTP status, when there is one."""
        super().__init__(message)
        self.status = status


class GitHubAuthError(GitHubError):
    """The token is missing, invalid or expired."""


class GitHubForbiddenError(GitHubError):
    """The token is valid but lacks a scope or permission for the request."""


class GitHubNotFoundError(GitHubError):
    """The resource does not exist, or the token cannot see it."""


class GitHubRateLimitError(GitHubError):
    """A primary or secondary rate limit was hit."""

    def __init__(
        self,
        message: str,
        *,
        status: int | None = None,
        reset_at: float | None = None,
    ) -> None:
        """Store the epoch second at which the limit resets, if known."""
        super().__init__(message, status=status)
        self.reset_at = reset_at


class GitHubTransportError(GitHubError):
    """The request failed before a usable response arrived."""


class GitHubGraphQLError(GitHubError):
    """The GraphQL response contained errors and no usable data."""

    def __init__(self, message: str, *, errors: list[dict[str, object]]) -> None:
        """Keep the raw error objects for callers that need them."""
        super().__init__(message)
        self.errors = errors
