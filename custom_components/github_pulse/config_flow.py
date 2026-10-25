"""Config flow for the GitHub Pulse integration."""

from __future__ import annotations

from typing import Any

import probatio
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_ACCESS_TOKEN
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
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
from .api.probe import fetch_token_info, probe_module
from .const import CONF_MODULES, CONF_OWNER, CONF_TOKEN_TYPE, DOMAIN, MODULES

TOKENS_URL = "https://github.com/settings/tokens"

STEP_USER_SCHEMA = probatio.Schema(
    {
        probatio.Required(CONF_ACCESS_TOKEN): TextSelector(
            TextSelectorConfig(type=TextSelectorType.PASSWORD)
        ),
        probatio.Required(CONF_MODULES, default=list(MODULES)): SelectSelector(
            SelectSelectorConfig(
                options=list(MODULES),
                multiple=True,
                translation_key=CONF_MODULES,
                mode=SelectSelectorMode.LIST,
            )
        ),
    }
)


async def _unavailable_modules(
    client: GitHubClient, modules: list[str], login: str
) -> list[str]:
    """Return the selected modules the token cannot serve."""
    return [m for m in modules if not await probe_module(client, m, login)]


class GitHubPulseConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the setup of a GitHub account."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for a token and the modules to enable, then verify both."""
        errors: dict[str, str] = {}
        placeholders: dict[str, str] = {"tokens_url": TOKENS_URL}

        if user_input is not None:
            token = user_input[CONF_ACCESS_TOKEN].strip()
            modules: list[str] = user_input[CONF_MODULES]
            if not modules:
                errors["base"] = "no_modules"
            else:
                client = GitHubClient(async_get_clientsession(self.hass), token)
                try:
                    info = await fetch_token_info(client, token)
                    unavailable = await _unavailable_modules(
                        client, modules, info.login
                    )
                except GitHubAuthError:
                    errors["base"] = "invalid_auth"
                except GitHubRateLimitError:
                    errors["base"] = "rate_limit"
                except GitHubError:
                    errors["base"] = "cannot_connect"
                else:
                    if unavailable:
                        errors["base"] = "module_unavailable"
                        placeholders["modules"] = ", ".join(unavailable)
                    else:
                        await self.async_set_unique_id(info.login.lower())
                        self._abort_if_unique_id_configured()
                        return self.async_create_entry(
                            title=info.login,
                            data={
                                CONF_ACCESS_TOKEN: token,
                                CONF_OWNER: info.login,
                                CONF_TOKEN_TYPE: info.token_type.value,
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
