"""Coordinator and data fetcher of one custom query."""

from __future__ import annotations

from datetime import datetime, timedelta

from homeassistant.config_entries import ConfigSubentry
from homeassistant.core import HomeAssistant

from .analytics.query_variables import query_variables
from .api import GitHubError
from .api.query_validation import QueryValidationError, parse_query
from .const import CONF_QUERY, CONF_QUERY_INTERVAL, CONF_QUERY_VARIABLES, SUBENTRY_QUERY
from .coordinator import GitHubPulseCoordinator
from .custom_query import (
    QueryOutcome,
    QueryRenderError,
    resolve_variables,
    run_query,
)
from .models import GitHubPulseConfigEntry
from .query_flow import QueryFormError, definition_from, parse_user_variables
from .settings import Settings

GROUP_QUERY = "query"


def query_subentries(
    entry: GitHubPulseConfigEntry,
) -> list[tuple[str, ConfigSubentry]]:
    """Return the id and data holder of every custom query subentry."""
    return [
        (subentry_id, sub)
        for subentry_id, sub in entry.subentries.items()
        if sub.subentry_type == SUBENTRY_QUERY
    ]


class QueryCoordinator(GitHubPulseCoordinator):
    """Run one custom query on its own interval."""

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: GitHubPulseConfigEntry,
        subentry: ConfigSubentry,
    ) -> None:
        """Create the coordinator for a query subentry."""
        self.subentry = subentry
        super().__init__(
            hass,
            config_entry,
            name=f"GitHub Pulse query {subentry.title}",
            client=config_entry.runtime_data.client,
            update_interval=timedelta(minutes=subentry.data[CONF_QUERY_INTERVAL]),
            groups={GROUP_QUERY: self._run},
            active_groups=(GROUP_QUERY,),
        )

    async def _run(self) -> QueryOutcome:
        """Run the query with fresh helper variables and render its templates.

        A query or template problem is reported like any other fetch failure,
        so the sensor turns unavailable and the reason lands in the logs and
        the diagnostics instead of breaking the whole entry.
        """
        data = dict(self.subentry.data)
        entry = self.config_entry
        zone = Settings.from_options(entry.options).contribution_time_zone
        try:
            parsed = parse_query(data[CONF_QUERY])
            today = datetime.now(zone).date()
            variables = resolve_variables(
                parsed.declared_variables,
                query_variables(today, entry.runtime_data.login, zone),
                parse_user_variables(data.get(CONF_QUERY_VARIABLES, "")),
            )
            return await run_query(
                self.hass, self.client, definition_from(data, variables)
            )
        except (QueryValidationError, QueryRenderError, QueryFormError) as err:
            raise GitHubError(str(err)) from err

    def outcome(self) -> QueryOutcome | None:
        """Return the latest rendered result, if the query has run."""
        return (self.data or {}).get(GROUP_QUERY)
