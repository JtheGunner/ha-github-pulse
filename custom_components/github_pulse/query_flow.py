"""Subentry flow that adds and changes a custom GraphQL query sensor."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import probatio
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.config_entries import ConfigSubentryFlow, SubentryFlowResult
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
)

from .analytics.query_variables import query_variables
from .api.errors import GitHubError
from .api.query_validation import (
    MIN_INTERVAL,
    QueryTooExpensiveError,
    QueryValidationError,
    ensure_affordable,
    estimate_cost,
    minimum_interval,
    parse_query,
)
from .const import (
    CONF_ATTRIBUTES_TEMPLATE,
    CONF_DEVICE_CLASS,
    CONF_QUERY,
    CONF_QUERY_INTERVAL,
    CONF_QUERY_NAME,
    CONF_QUERY_VARIABLES,
    CONF_STATE_CLASS,
    CONF_STATE_TEMPLATE,
    CONF_UNIT,
)
from .custom_query import (
    QueryDefinition,
    QueryOutcome,
    QueryRenderError,
    resolve_variables,
    run_query,
)
from .models import GitHubPulseConfigEntry
from .repository_flow import error_code
from .settings import Settings

NONE_CHOICE = "none"
MAX_INTERVAL = 24 * 60
PREVIEW_LENGTH = 800
DEFAULT_QUERY_INTERVAL = 30


class QueryFormError(Exception):
    """A form problem with the error key to show and a detail for the message."""

    def __init__(self, code: str, detail: str = "") -> None:
        """Keep the translation key and the human-readable detail."""
        super().__init__(detail or code)
        self.code = code
        self.detail = detail


@dataclass(frozen=True, slots=True)
class QueryPreview:
    """The outcome of the test run shown before saving."""

    raw: str
    outcome: QueryOutcome


def definition_from(data: dict[str, Any], variables: dict[str, Any]) -> QueryDefinition:
    """Build the engine's definition from stored subentry data."""
    return QueryDefinition(
        name=data[CONF_QUERY_NAME],
        query=data[CONF_QUERY],
        state_template=data[CONF_STATE_TEMPLATE],
        attributes_template=data.get(CONF_ATTRIBUTES_TEMPLATE) or None,
        variables=variables,
    )


def parse_user_variables(raw: str) -> dict[str, Any]:
    """Parse the variables field: empty, or a JSON object."""
    if not raw.strip():
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as err:
        raise QueryFormError("invalid_variables", str(err)) from err
    if not isinstance(value, dict):
        raise QueryFormError("invalid_variables", "expected a JSON object")
    return value


def _schema(defaults: dict[str, Any]) -> probatio.Schema:
    classes = [NONE_CHOICE, *sorted(c.value for c in SensorDeviceClass)]
    state_classes = [NONE_CHOICE, *(c.value for c in SensorStateClass)]
    return probatio.Schema(
        {
            probatio.Required(
                CONF_QUERY_NAME, default=defaults.get(CONF_QUERY_NAME, "")
            ): str,
            probatio.Required(
                CONF_QUERY, default=defaults.get(CONF_QUERY, "")
            ): TextSelector(TextSelectorConfig(multiline=True)),
            probatio.Optional(
                CONF_QUERY_VARIABLES, default=defaults.get(CONF_QUERY_VARIABLES, "")
            ): TextSelector(TextSelectorConfig(multiline=True)),
            probatio.Required(
                CONF_QUERY_INTERVAL,
                default=defaults.get(CONF_QUERY_INTERVAL, DEFAULT_QUERY_INTERVAL),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=MIN_INTERVAL.total_seconds() // 60,
                    max=MAX_INTERVAL,
                    step=1,
                    mode=NumberSelectorMode.BOX,
                    unit_of_measurement="min",
                )
            ),
            probatio.Required(
                CONF_STATE_TEMPLATE, default=defaults.get(CONF_STATE_TEMPLATE, "")
            ): TextSelector(TextSelectorConfig(multiline=True)),
            probatio.Optional(
                CONF_ATTRIBUTES_TEMPLATE,
                default=defaults.get(CONF_ATTRIBUTES_TEMPLATE, ""),
            ): TextSelector(TextSelectorConfig(multiline=True)),
            probatio.Optional(CONF_UNIT, default=defaults.get(CONF_UNIT, "")): str,
            probatio.Optional(
                CONF_DEVICE_CLASS, default=defaults.get(CONF_DEVICE_CLASS, NONE_CHOICE)
            ): SelectSelector(
                SelectSelectorConfig(options=classes, mode=SelectSelectorMode.DROPDOWN)
            ),
            probatio.Optional(
                CONF_STATE_CLASS, default=defaults.get(CONF_STATE_CLASS, NONE_CHOICE)
            ): SelectSelector(
                SelectSelectorConfig(
                    options=state_classes, mode=SelectSelectorMode.DROPDOWN
                )
            ),
        }
    )


class QuerySubentryFlow(ConfigSubentryFlow):
    """Add or change a custom query, showing a test run before saving."""

    def __init__(self) -> None:
        """Start without a pending query."""
        self._pending: dict[str, Any] = {}
        self._preview: QueryPreview | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Collect the query and its sensor settings, validate and test-run it."""
        return await self._form("user", user_input, {})

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Change an existing query; it is validated and test-run again."""
        subentry = self._get_reconfigure_subentry()
        return await self._form("reconfigure", user_input, dict(subentry.data))

    async def async_step_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Show the raw result and the rendered state, then save."""
        assert self._preview is not None  # noqa: S101
        if user_input is None:
            return self.async_show_form(
                step_id="confirm",
                description_placeholders={
                    "query_name": self._pending[CONF_QUERY_NAME],
                    "raw": self._preview.raw,
                    "state": str(self._preview.outcome.state),
                },
            )
        title = self._pending[CONF_QUERY_NAME]
        if self.source == "reconfigure":
            return self.async_update_and_abort(
                self._get_entry(),
                self._get_reconfigure_subentry(),
                title=title,
                data=self._pending,
            )
        return self.async_create_entry(
            title=title,
            data=self._pending,
            unique_id=title.strip().lower(),
        )

    async def _form(
        self, step_id: str, user_input: dict[str, Any] | None, defaults: dict[str, Any]
    ) -> SubentryFlowResult:
        errors: dict[str, str] = {}
        placeholders = {"detail": ""}
        if user_input is not None:
            try:
                self._check_unique(user_input)
                self._preview = await self._validate(user_input)
            except QueryFormError as err:
                errors["base"] = err.code
                placeholders["detail"] = err.detail
            else:
                self._pending = _normalise(user_input)
                return await self.async_step_confirm()
        return self.async_show_form(
            step_id=step_id,
            data_schema=_schema(user_input or defaults),
            errors=errors,
            description_placeholders=placeholders,
        )

    def _check_unique(self, user_input: dict[str, Any]) -> None:
        unique_id = user_input[CONF_QUERY_NAME].strip().lower()
        own = self._get_reconfigure_subentry() if self.source == "reconfigure" else None
        for subentry in self._get_entry().subentries.values():
            if subentry is not own and subentry.unique_id == unique_id:
                raise QueryFormError("name_in_use")

    async def _validate(self, user_input: dict[str, Any]) -> QueryPreview:
        entry: GitHubPulseConfigEntry = self._get_entry()
        client = entry.runtime_data.client
        zone = Settings.from_options(entry.options).contribution_time_zone
        try:
            parsed = parse_query(user_input[CONF_QUERY])
        except QueryValidationError as err:
            raise QueryFormError("invalid_query", str(err)) from err
        helpers = query_variables(
            datetime.now(zone).date(), entry.runtime_data.login, zone
        )
        user_variables = parse_user_variables(user_input.get(CONF_QUERY_VARIABLES, ""))
        try:
            variables = resolve_variables(
                parsed.declared_variables, helpers, user_variables
            )
        except QueryRenderError as err:
            raise QueryFormError("invalid_variables", str(err)) from err
        try:
            cost = await estimate_cost(client, parsed, variables)
            ensure_affordable(cost)
            floor = minimum_interval(cost)
            if timedelta(minutes=user_input[CONF_QUERY_INTERVAL]) < floor:
                raise QueryFormError(
                    "interval_too_short", str(math.ceil(floor.total_seconds() / 60))
                )
            definition = definition_from(user_input, variables)
            outcome = await run_query(self.hass, client, definition)
        except QueryTooExpensiveError as err:
            raise QueryFormError("too_expensive", str(err)) from err
        except QueryValidationError as err:
            raise QueryFormError("invalid_query", str(err)) from err
        except QueryRenderError as err:
            raise QueryFormError("template_error", str(err)) from err
        except GitHubError as err:
            raise QueryFormError(error_code(err), str(err)) from err
        return QueryPreview(_excerpt(outcome), outcome)


def _excerpt(outcome: QueryOutcome) -> str:
    text = json.dumps(outcome.data, default=str, indent=2)
    return text if len(text) <= PREVIEW_LENGTH else text[:PREVIEW_LENGTH] + " …"


def _normalise(user_input: dict[str, Any]) -> dict[str, Any]:
    data = dict(user_input)
    data[CONF_QUERY_NAME] = data[CONF_QUERY_NAME].strip()
    data[CONF_QUERY_INTERVAL] = int(data[CONF_QUERY_INTERVAL])
    for key in (CONF_DEVICE_CLASS, CONF_STATE_CLASS):
        if data.get(key) == NONE_CHOICE:
            data[key] = None
    return data
