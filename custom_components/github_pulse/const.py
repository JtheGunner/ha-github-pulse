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

CONF_PROFILE_INTERVAL: Final = "profile_interval"
CONF_REPOSITORY_INTERVAL: Final = "repository_interval"
CONF_HISTORY_YEARS: Final = "history_years"
CONF_CONTRIBUTION_TIME_ZONE: Final = "contribution_time_zone"
CONF_INCLUDE_RESTRICTED: Final = "include_restricted"
CONF_LANGUAGE_WEIGHTING: Final = "language_weighting"
CONF_IMPORT_STATISTICS: Final = "import_statistics"
CONF_REPOSITORY: Final = "repository"
CONF_ACTIONS: Final = "actions"
CONF_QUERY_NAME: Final = "name"
CONF_QUERY: Final = "query"
CONF_QUERY_VARIABLES: Final = "variables"
CONF_QUERY_INTERVAL: Final = "interval"
CONF_STATE_TEMPLATE: Final = "state_template"
CONF_ATTRIBUTES_TEMPLATE: Final = "attributes_template"
CONF_UNIT: Final = "unit"
CONF_DEVICE_CLASS: Final = "device_class"
CONF_STATE_CLASS: Final = "state_class"

SUBENTRY_REPOSITORY: Final = "repository"
SUBENTRY_QUERY: Final = "query"

WEIGHTING_COMMITS: Final = "commit_weighted"
WEIGHTING_REPOSITORIES: Final = "repo_count"
LANGUAGE_WEIGHTINGS: Final = (WEIGHTING_COMMITS, WEIGHTING_REPOSITORIES)

DEFAULT_PROFILE_INTERVAL: Final = 15  # minutes
DEFAULT_REPOSITORY_INTERVAL: Final = 15  # minutes
MIN_INTERVAL: Final = 5
MAX_INTERVAL: Final = 1440
MIN_HISTORY_YEARS: Final = 1
MAX_HISTORY_YEARS: Final = 10

MODULE_PROFILE: Final = "profile"
MODULE_REPOSITORIES: Final = "repositories"
MODULES: Final = (MODULE_PROFILE, MODULE_REPOSITORIES)

# GitHub buckets contribution days in Pacific Time unless a profile time zone is set.
DEFAULT_CONTRIBUTION_TIME_ZONE: Final = "America/Los_Angeles"
DEFAULT_HISTORY_YEARS: Final = 3
DEFAULT_INCLUDE_RESTRICTED: Final = True
DEFAULT_IMPORT_STATISTICS: Final = False
