"""Subentry flow that adds and changes a tracked repository."""

from __future__ import annotations

from typing import Any

import probatio
from homeassistant.config_entries import (
    ConfigSubentryFlow,
    SubentryFlowResult,
)
from homeassistant.helpers.selector import (
    BooleanSelector,
    TextSelector,
)

from .api import (
    GitHubAuthError,
    GitHubClient,
    GitHubForbiddenError,
    GitHubNotFoundError,
    GitHubRateLimitError,
)
from .api.errors import GitHubError
from .api.repository import (
    RepositoryInfo,
    can_read_actions,
    fetch_repository,
    parse_repository_name,
)
from .const import CONF_ACTIONS, CONF_REPOSITORY, MODULE_REPOSITORIES
from .models import GitHubPulseConfigEntry


def _schema(repository: str = "", actions: bool = False) -> probatio.Schema:
    return probatio.Schema(
        {
            probatio.Required(CONF_REPOSITORY, default=repository): TextSelector(),
            probatio.Required(CONF_ACTIONS, default=actions): BooleanSelector(),
        }
    )


class RepositorySubentryFlow(ConfigSubentryFlow):
    """Add a repository by name, or change what is tracked for it."""

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Ask for ``owner/name`` and whether to track workflow runs."""
        entry = self._get_entry()
        errors: dict[str, str] = {}
        if MODULE_REPOSITORIES not in entry.data.get("modules", []):
            return self.async_abort(reason="module_disabled")

        if user_input is not None:
            info, error = await self._check(entry, user_input)
            if error is not None:
                errors["base"] = error
            elif info is not None:
                unique_id = info.full_name.lower()
                if any(s.unique_id == unique_id for s in entry.subentries.values()):
                    return self.async_abort(reason="already_configured")
                return self.async_create_entry(
                    title=info.full_name,
                    data={
                        CONF_REPOSITORY: info.full_name,
                        CONF_ACTIONS: user_input[CONF_ACTIONS],
                    },
                    unique_id=unique_id,
                )

        suggested = user_input or {}
        return self.async_show_form(
            step_id="user",
            data_schema=_schema(
                suggested.get(CONF_REPOSITORY, ""), suggested.get(CONF_ACTIONS, False)
            ),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Change whether workflow runs of an existing repository are tracked."""
        entry = self._get_entry()
        subentry = self._get_reconfigure_subentry()
        errors: dict[str, str] = {}

        if user_input is not None:
            if user_input[CONF_ACTIONS] and not await self._actions_allowed(
                entry, subentry.data[CONF_REPOSITORY]
            ):
                errors["base"] = "actions_no_access"
            else:
                return self.async_update_and_abort(
                    entry,
                    subentry,
                    data={**subentry.data, CONF_ACTIONS: user_input[CONF_ACTIONS]},
                )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=probatio.Schema(
                {
                    probatio.Required(
                        CONF_ACTIONS, default=subentry.data.get(CONF_ACTIONS, False)
                    ): BooleanSelector()
                }
            ),
            description_placeholders={"repository": subentry.data[CONF_REPOSITORY]},
            errors=errors,
        )

    async def _actions_allowed(
        self, entry: GitHubPulseConfigEntry, full_name: str
    ) -> bool:
        client: GitHubClient = entry.runtime_data.client
        try:
            return await can_read_actions(client, full_name)
        except GitHubError:
            return False

    async def _check(
        self, entry: GitHubPulseConfigEntry, user_input: dict[str, Any]
    ) -> tuple[RepositoryInfo | None, str | None]:
        """Validate the name, the repository and the optional Actions access."""
        try:
            owner, name = parse_repository_name(user_input[CONF_REPOSITORY])
        except ValueError:
            return None, "invalid_name"
        client: GitHubClient = entry.runtime_data.client
        try:
            info = await fetch_repository(client, owner, name)
            if user_input[CONF_ACTIONS] and not await can_read_actions(
                client, info.full_name
            ):
                return None, "actions_no_access"
        except GitHubError as err:
            return None, _error_code(err)
        return info, None


# Subclasses first: the first matching entry wins.
_ERROR_CODES: tuple[tuple[type[GitHubError], str], ...] = (
    (GitHubNotFoundError, "not_found"),
    (GitHubForbiddenError, "no_access"),
    (GitHubAuthError, "invalid_auth"),
    (GitHubRateLimitError, "rate_limit"),
    (GitHubError, "cannot_connect"),
)


def _error_code(error: GitHubError) -> str:
    return next(code for kind, code in _ERROR_CODES if isinstance(error, kind))
