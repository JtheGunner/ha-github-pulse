"""Tests for diagnostics."""

from __future__ import annotations

import json
from collections.abc import Callable

from custom_components.github_pulse.const import (
    CONF_MODULES,
    CONF_OWNER,
    CONF_TOKEN_TYPE,
    DOMAIN,
)
from custom_components.github_pulse.diagnostics import (
    async_get_config_entry_diagnostics,
)
from homeassistant.const import CONF_ACCESS_TOKEN
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from tests.fake_http import FakeSession


async def test_diagnostics_redact_the_token(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None]
) -> None:
    patch_session(FakeSession())
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="octocat",
        data={
            CONF_ACCESS_TOKEN: "ghp_super_secret",
            CONF_OWNER: "octocat",
            CONF_TOKEN_TYPE: "classic",
            CONF_MODULES: ["repositories", "profile"],
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    entry.runtime_data.client.budget.update_from_headers(
        {
            "X-RateLimit-Limit": "5000",
            "X-RateLimit-Remaining": "4990",
            "X-RateLimit-Reset": "99999999999",
            "X-RateLimit-Resource": "graphql",
        }
    )

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)

    assert "ghp_super_secret" not in json.dumps(diagnostics)
    assert diagnostics["entry"]["data"][CONF_ACCESS_TOKEN] == "**REDACTED**"
    assert diagnostics["entry"]["data"][CONF_OWNER] == "octocat"
    assert diagnostics["modules"] == ["profile", "repositories"]
    assert diagnostics["rate_budget"]["graphql"]["remaining"] == 4990
