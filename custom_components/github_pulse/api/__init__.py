"""GitHub API client, free of Home Assistant imports."""

from .client import GitHubClient, GraphQLResult, RestResponse
from .errors import (
    GitHubAuthError,
    GitHubError,
    GitHubForbiddenError,
    GitHubGraphQLError,
    GitHubNotFoundError,
    GitHubRateLimitError,
    GitHubTransportError,
)
from .rate_budget import RateBudget, ResourceBudget

__all__ = [
    "GitHubAuthError",
    "GitHubClient",
    "GitHubError",
    "GitHubForbiddenError",
    "GitHubGraphQLError",
    "GitHubNotFoundError",
    "GitHubRateLimitError",
    "GitHubTransportError",
    "GraphQLResult",
    "RateBudget",
    "ResourceBudget",
    "RestResponse",
]
