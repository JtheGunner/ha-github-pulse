"""Ready-made custom queries offered as starting points in the flow."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class QueryPreset:
    """A query with the sensor settings that go with it."""

    key: str
    name: str
    query: str
    state_path: str
    unit: str = ""
    state_class: str = "measurement"
    interval: int = 60

    @property
    def state_template(self) -> str:
        """Return the template that reads ``state_path`` from ``value_json``."""
        return "{{ value_json." + self.state_path + " }}"


_MONTH = (
    "query($owner: String!, $start_of_month: DateTime!, $end_of_month: DateTime!) "
    "{ user(login: $owner) { contributionsCollection"
    "(from: $start_of_month, to: $end_of_month) { %s } } }"
)

PRESETS: tuple[QueryPreset, ...] = (
    QueryPreset(
        key="commits_this_month",
        name="Commits this month",
        query=_MONTH % "totalCommitContributions",
        state_path="user.contributionsCollection.totalCommitContributions",
        unit="commits",
    ),
    QueryPreset(
        key="pull_requests_this_month",
        name="Pull requests this month",
        query=_MONTH % "totalPullRequestContributions",
        state_path="user.contributionsCollection.totalPullRequestContributions",
        unit="pull requests",
    ),
    QueryPreset(
        key="contributions_this_year",
        name="Contributions this year",
        query=(
            "query($owner: String!, $start_of_year: DateTime!) "
            "{ user(login: $owner) { contributionsCollection(from: $start_of_year) "
            "{ contributionCalendar { totalContributions } } } }"
        ),
        state_path="user.contributionsCollection.contributionCalendar"
        ".totalContributions",
        unit="contributions",
    ),
    QueryPreset(
        key="public_repositories",
        name="Public repositories",
        query=(
            "query($owner: String!) { user(login: $owner) { "
            "repositories(privacy: PUBLIC, ownerAffiliations: OWNER) "
            "{ totalCount } } }"
        ),
        state_path="user.repositories.totalCount",
        unit="repositories",
    ),
    QueryPreset(
        key="followers",
        name="Followers",
        query=(
            "query($owner: String!) "
            "{ user(login: $owner) { followers { totalCount } } }"
        ),
        state_path="user.followers.totalCount",
        unit="followers",
    ),
)

PRESETS_BY_KEY = {preset.key: preset for preset in PRESETS}
CUSTOM = "custom"
