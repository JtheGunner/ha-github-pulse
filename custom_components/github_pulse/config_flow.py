"""Config flow for the GitHub Pulse integration."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import probatio
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.const import CONF_ACCESS_TOKEN
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import (
    GitHubAuthError,
    GitHubClient,
    GitHubError,
    GitHubRateLimitError,
)
from .api.probe import TokenInfo, fetch_token_info, probe_module
from .const import (
    CONF_CONTRIBUTION_TIME_ZONE,
    CONF_HISTORY_YEARS,
    CONF_INCLUDE_RESTRICTED,
    CONF_LANGUAGE_WEIGHTING,
    CONF_MODULES,
    CONF_OWNER,
    CONF_PROFILE_INTERVAL,
    CONF_REPOSITORY_INTERVAL,
    CONF_TOKEN_TYPE,
    DEFAULT_CONTRIBUTION_TIME_ZONE,
    DEFAULT_HISTORY_YEARS,
    DEFAULT_INCLUDE_RESTRICTED,
    DEFAULT_PROFILE_INTERVAL,
    DEFAULT_REPOSITORY_INTERVAL,
    DOMAIN,
    LANGUAGE_WEIGHTINGS,
    MAX_HISTORY_YEARS,
    MAX_INTERVAL,
    MIN_HISTORY_YEARS,
    MIN_INTERVAL,
    MODULES,
    WEIGHTING_COMMITS,
)
from .settings import is_valid_time_zone

TOKENS_URL = "https://github.com/settings/tokens"

_TOKEN_SELECTOR = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))
_MODULES_SELECTOR = SelectSelector(
    SelectSelectorConfig(
        options=list(MODULES),
        multiple=True,
        translation_key=CONF_MODULES,
        mode=SelectSelectorMode.LIST,
    )
)

STEP_USER_SCHEMA = probatio.Schema(
    {
        probatio.Required(CONF_ACCESS_TOKEN): _TOKEN_SELECTOR,
        probatio.Required(CONF_MODULES, default=list(MODULES)): _MODULES_SELECTOR,
    }
)
STEP_REAUTH_SCHEMA = probatio.Schema(
    {probatio.Required(CONF_ACCESS_TOKEN): _TOKEN_SELECTOR}
)
STEP_RECONFIGURE_SCHEMA = probatio.Schema(
    {probatio.Required(CONF_MODULES): _MODULES_SELECTOR}
)


def _interval_selector() -> NumberSelector:
    return NumberSelector(
        NumberSelectorConfig(
            min=MIN_INTERVAL,
            max=MAX_INTERVAL,
            step=1,
            mode=NumberSelectorMode.BOX,
            unit_of_measurement="min",
        )
    )


def _options_schema(current: Mapping[str, Any]) -> probatio.Schema:
    def default(key: str, fallback: Any) -> Any:
        return current.get(key, fallback)

    return probatio.Schema(
        {
            probatio.Required(
                CONF_PROFILE_INTERVAL,
                default=default(CONF_PROFILE_INTERVAL, DEFAULT_PROFILE_INTERVAL),
            ): _interval_selector(),
            probatio.Required(
                CONF_REPOSITORY_INTERVAL,
                default=default(CONF_REPOSITORY_INTERVAL, DEFAULT_REPOSITORY_INTERVAL),
            ): _interval_selector(),
            probatio.Required(
                CONF_HISTORY_YEARS,
                default=default(CONF_HISTORY_YEARS, DEFAULT_HISTORY_YEARS),
            ): NumberSelector(
                NumberSelectorConfig(
                    min=MIN_HISTORY_YEARS,
                    max=MAX_HISTORY_YEARS,
                    step=1,
                    mode=NumberSelectorMode.BOX,
                    unit_of_measurement="years",
                )
            ),
            probatio.Required(
                CONF_CONTRIBUTION_TIME_ZONE,
                default=default(
                    CONF_CONTRIBUTION_TIME_ZONE, DEFAULT_CONTRIBUTION_TIME_ZONE
                ),
            ): TextSelector(),
            probatio.Required(
                CONF_INCLUDE_RESTRICTED,
                default=default(CONF_INCLUDE_RESTRICTED, DEFAULT_INCLUDE_RESTRICTED),
            ): BooleanSelector(),
            probatio.Required(
                CONF_LANGUAGE_WEIGHTING,
                default=default(CONF_LANGUAGE_WEIGHTING, WEIGHTING_COMMITS),
            ): SelectSelector(
                SelectSelectorConfig(
                    options=list(LANGUAGE_WEIGHTINGS),
                    translation_key=CONF_LANGUAGE_WEIGHTING,
                    mode=SelectSelectorMode.DROPDOWN,
                )
            ),
        }
    )


class _Verification:
    """Outcome of checking a token (and optionally modules) against GitHub."""

    def __init__(self) -> None:
        self.info: TokenInfo | None = None
        self.errors: dict[str, str] = {}
        self.placeholders: dict[str, str] = {}


async def _verify(
    hass: HomeAssistant,
    token: str,
    modules: list[str],
    *,
    expected_login: str | None = None,
) -> _Verification:
    """Check the token, that it belongs to ``expected_login``, and the modules."""
    result = _Verification()
    client = GitHubClient(async_get_clientsession(hass), token)
    try:
        info = await fetch_token_info(client, token)
        if expected_login and info.login.lower() != expected_login.lower():
            result.errors["base"] = "wrong_account"
            result.placeholders["owner"] = expected_login
            return result
        unavailable = [
            m for m in modules if not await probe_module(client, m, info.login)
        ]
    except GitHubAuthError:
        result.errors["base"] = "invalid_auth"
    except GitHubRateLimitError:
        result.errors["base"] = "rate_limit"
    except GitHubError:
        result.errors["base"] = "cannot_connect"
    else:
        if unavailable:
            result.errors["base"] = "module_unavailable"
            result.placeholders["modules"] = ", ".join(unavailable)
        else:
            result.info = info
    return result


class GitHubPulseConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the setup, reauthentication and reconfiguration of an account."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> GitHubPulseOptionsFlow:
        """Return the options flow handler."""
        return GitHubPulseOptionsFlow()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for a token and the modules to enable, then verify both."""
        errors: dict[str, str] = {}
        placeholders = {"tokens_url": TOKENS_URL}

        if user_input is not None:
            token = user_input[CONF_ACCESS_TOKEN].strip()
            modules: list[str] = user_input[CONF_MODULES]
            if not modules:
                errors["base"] = "no_modules"
            else:
                verified = await _verify(self.hass, token, modules)
                errors = verified.errors
                placeholders |= verified.placeholders
                if verified.info:
                    await self.async_set_unique_id(verified.info.login.lower())
                    self._abort_if_unique_id_configured()
                    return self.async_create_entry(
                        title=verified.info.login,
                        data={
                            CONF_ACCESS_TOKEN: token,
                            CONF_OWNER: verified.info.login,
                            CONF_TOKEN_TYPE: verified.info.token_type.value,
                            CONF_MODULES: modules,
                        },
                    )

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                STEP_USER_SCHEMA, user_input
            ),
            errors=errors,
            description_placeholders=placeholders,
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Start reauthentication after GitHub rejected the stored token."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for a new token for the same GitHub account."""
        errors: dict[str, str] = {}
        entry = self._get_reauth_entry()
        placeholders = {"tokens_url": TOKENS_URL, "owner": entry.data[CONF_OWNER]}

        if user_input is not None:
            token = user_input[CONF_ACCESS_TOKEN].strip()
            verified = await _verify(
                self.hass,
                token,
                list(entry.data[CONF_MODULES]),
                expected_login=entry.data[CONF_OWNER],
            )
            errors = verified.errors
            placeholders |= verified.placeholders
            if verified.info:
                return self.async_update_reload_and_abort(
                    entry,
                    data_updates={
                        CONF_ACCESS_TOKEN: token,
                        CONF_TOKEN_TYPE: verified.info.token_type.value,
                    },
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=STEP_REAUTH_SCHEMA,
            errors=errors,
            description_placeholders=placeholders,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change which modules are enabled, keeping the stored token."""
        errors: dict[str, str] = {}
        placeholders: dict[str, str] = {}
        entry = self._get_reconfigure_entry()

        if user_input is not None:
            modules: list[str] = user_input[CONF_MODULES]
            if not modules:
                errors["base"] = "no_modules"
            else:
                verified = await _verify(
                    self.hass,
                    entry.data[CONF_ACCESS_TOKEN],
                    modules,
                    expected_login=entry.data[CONF_OWNER],
                )
                errors = verified.errors
                placeholders |= verified.placeholders
                if verified.info:
                    return self.async_update_reload_and_abort(
                        entry, data_updates={CONF_MODULES: modules}
                    )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                STEP_RECONFIGURE_SCHEMA,
                user_input or {CONF_MODULES: entry.data[CONF_MODULES]},
            ),
            errors=errors,
            description_placeholders=placeholders,
        )


class GitHubPulseOptionsFlow(OptionsFlowWithReload):
    """Handle the options of an entry; saving reloads the entry."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage polling intervals, history depth and contribution settings."""
        errors: dict[str, str] = {}

        if user_input is not None:
            if not is_valid_time_zone(user_input[CONF_CONTRIBUTION_TIME_ZONE]):
                errors[CONF_CONTRIBUTION_TIME_ZONE] = "invalid_time_zone"
            else:
                return self.async_create_entry(
                    data={
                        **user_input,
                        CONF_PROFILE_INTERVAL: int(user_input[CONF_PROFILE_INTERVAL]),
                        CONF_REPOSITORY_INTERVAL: int(
                            user_input[CONF_REPOSITORY_INTERVAL]
                        ),
                        CONF_HISTORY_YEARS: int(user_input[CONF_HISTORY_YEARS]),
                    }
                )

        return self.async_show_form(
            step_id="init",
            data_schema=_options_schema(user_input or self.config_entry.options),
            errors=errors,
        )
