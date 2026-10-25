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

# GitHub buckets contribution days in Pacific Time unless a profile time zone is set.
DEFAULT_CONTRIBUTION_TIME_ZONE: Final = "America/Los_Angeles"
DEFAULT_HISTORY_YEARS: Final = 3
