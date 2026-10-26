"""Subentry flow that adds and changes a tracked repository."""

from __future__ import annotations

from types import MappingProxyType
from typing import Any

import probatio
from homeassistant.config_entries import (
    ConfigSubentry,
    ConfigSubentryFlow,
    SubentryFlowResult,
)
from homeassistant.helpers.selector import (
    BooleanSelector,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
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
    list_accessible_repositories,
    parse_repository_name,
)
from .const import (
    CONF_ACTIONS,
    CONF_REPOSITORIES,
    CONF_REPOSITORY,
    MODULE_REPOSITORIES,
    SUBENTRY_REPOSITORY,
)
from .models import GitHubPulseConfigEntry


def _schema(
    options: list[str], repositories: list[str] | None = None, actions: bool = False
) -> probatio.Schema:
    """Return the form: a multi-select that also accepts typed names."""
    return probatio.Schema(
        {
            probatio.Required(CONF_REPOSITORIES, default=repositories or []): (
                SelectSelector(
                    SelectSelectorConfig(
                        options=options,
                        multiple=True,
                        custom_value=True,
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                )
            ),
            probatio.Required(CONF_ACTIONS, default=actions): BooleanSelector(),
        }
    )


class RepositorySubentryFlow(ConfigSubentryFlow):
    """Add repositories from a list or by name, or change what is tracked."""

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Pick one or more repositories and whether to track workflow runs."""
        entry = self._get_entry()
        errors: dict[str, str] = {}
        placeholders: dict[str, str] = {}
        if MODULE_REPOSITORIES not in entry.data.get("modules", []):
            return self.async_abort(reason="module_disabled")

        tracked = {s.unique_id for s in entry.subentries.values()}
        if user_input is not None:
            selected = _unique_names(user_input[CONF_REPOSITORIES])
            if not selected:
                errors["base"] = "no_repository"
            elif all(name.lower() in tracked for name in selected):
                return self.async_abort(reason="already_configured")
            else:
                infos, failed, error = await self._check_all(
                    entry,
                    [n for n in selected if n.lower() not in tracked],
                    user_input[CONF_ACTIONS],
                )
                if error is not None:
                    errors["base"] = error
                    placeholders["repository"] = failed
                else:
                    return self._create_all(entry, infos, user_input[CONF_ACTIONS])

        suggested = user_input or {}
        names = list(await self._selectable(entry, tracked))
        return self.async_show_form(
            step_id="user",
            data_schema=_schema(
                names,
                suggested.get(CONF_REPOSITORIES),
                suggested.get(CONF_ACTIONS, False),
            ),
            errors=errors,
            description_placeholders=placeholders,
        )

    async def _selectable(
        self, entry: GitHubPulseConfigEntry, tracked: set[str | None]
    ) -> tuple[str, ...]:
        """Return the repositories to offer; an empty list means typing only."""
        client: GitHubClient = entry.runtime_data.client
        try:
            names = await list_accessible_repositories(client)
        except GitHubError:
            return ()
        return tuple(n for n in names if n.lower() not in tracked)

    async def _check_all(
        self, entry: GitHubPulseConfigEntry, names: list[str], actions: bool
    ) -> tuple[list[RepositoryInfo], str, str | None]:
        """Validate every name; stop at the first problem and name that repository."""
        infos: list[RepositoryInfo] = []
        for name in names:
            info, error = await self._check(entry, name, actions)
            if error is not None:
                return [], name, error
            if info is not None:
                infos.append(info)
        return infos, "", None

    def _create_all(
        self,
        entry: GitHubPulseConfigEntry,
        infos: list[RepositoryInfo],
        actions: bool,
    ) -> SubentryFlowResult:
        """Add all but the last repository directly and finish with the last one.

        A subentry flow creates one subentry; the others are added to the entry
        by hand. Reloads triggered by each addition are coalesced.
        """
        *others, last = infos
        for info in others:
            self.hass.config_entries.async_add_subentry(entry, _subentry(info, actions))
        return self.async_create_entry(
            title=last.full_name,
            data={CONF_REPOSITORY: last.full_name, CONF_ACTIONS: actions},
            unique_id=last.full_name.lower(),
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
        self, entry: GitHubPulseConfigEntry, value: str, actions: bool
    ) -> tuple[RepositoryInfo | None, str | None]:
        """Validate the name, the repository and the optional Actions access."""
        try:
            owner, name = parse_repository_name(value)
        except ValueError:
            return None, "invalid_name"
        client: GitHubClient = entry.runtime_data.client
        try:
            info = await fetch_repository(client, owner, name)
            if actions and not await can_read_actions(client, info.full_name):
                return None, "actions_no_access"
        except GitHubError as err:
            return None, error_code(err)
        return info, None


def _unique_names(values: list[str]) -> list[str]:
    """Drop blanks and case-insensitive duplicates, keeping the order."""
    seen: dict[str, str] = {}
    for value in values:
        if value.strip():
            seen.setdefault(value.strip().lower(), value.strip())
    return list(seen.values())


def _subentry(info: RepositoryInfo, actions: bool) -> ConfigSubentry:
    return ConfigSubentry(
        data=MappingProxyType({CONF_REPOSITORY: info.full_name, CONF_ACTIONS: actions}),
        subentry_type=SUBENTRY_REPOSITORY,
        title=info.full_name,
        unique_id=info.full_name.lower(),
    )


# Subclasses first: the first matching entry wins.
_ERROR_CODES: tuple[tuple[type[GitHubError], str], ...] = (
    (GitHubNotFoundError, "not_found"),
    (GitHubForbiddenError, "no_access"),
    (GitHubAuthError, "invalid_auth"),
    (GitHubRateLimitError, "rate_limit"),
    (GitHubError, "cannot_connect"),
)


def error_code(error: GitHubError) -> str:
    return next(code for kind, code in _ERROR_CODES if isinstance(error, kind))
