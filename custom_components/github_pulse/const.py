"""Constants for the GitHub Pulse integration."""

from logging import Logger, getLogger
from typing import Final

DOMAIN: Final = "github_pulse"

LOGGER: Logger = getLogger(__package__)

API_BASE_URL: Final = "https://api.github.com"
GRAPHQL_URL: Final = f"{API_BASE_URL}/graphql"
API_VERSION: Final = "2022-11-28"
REQUEST_TIMEOUT: Final = 30
USER_AGENT: Final = "home-assistant-github-pulse"

ATTRIBUTION: Final = "Data provided by the GitHub API"

CONF_OWNER: Final = "owner"
CONF_MODULES: Final = "modules"
CONF_TOKEN_TYPE: Final = "token_type"  # noqa: S105 - a config key, not a secret

MODULE_PROFILE: Final = "profile"
MODULE_REPOSITORIES: Final = "repositories"
MODULES: Final = (MODULE_PROFILE, MODULE_REPOSITORIES)

# GitHub buckets contribution days in Pacific Time unless a profile time zone is set.
DEFAULT_CONTRIBUTION_TIME_ZONE: Final = "America/Los_Angeles"
DEFAULT_HISTORY_YEARS: Final = 3
