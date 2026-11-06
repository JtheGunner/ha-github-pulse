"""Tests for the typed options."""

from datetime import timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest
from custom_components.github_pulse.const import (
    CONF_CONTRIBUTION_TIME_ZONE,
    CONF_HISTORY_YEARS,
    CONF_INCLUDE_RESTRICTED,
    CONF_LANGUAGE_WEIGHTING,
    CONF_PROFILE_INTERVAL,
    CONF_REPOSITORY_INTERVAL,
)
from custom_components.github_pulse.settings import Settings, async_resolve_time_zone
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError
from homeassistant.util import dt as dt_util


async def test_defaults_apply_to_empty_options(hass: HomeAssistant) -> None:
    settings = await Settings.async_from_options(hass, {})

    assert settings.profile_interval == timedelta(minutes=15)
    assert settings.repository_interval == timedelta(minutes=15)
    assert settings.history_years == 3
    assert settings.contribution_time_zone == ZoneInfo("America/Los_Angeles")
    assert settings.include_restricted is True
    assert settings.language_weighting == "commit_weighted"


async def test_stored_options_override_the_defaults(hass: HomeAssistant) -> None:
    settings = await Settings.async_from_options(
        hass,
        {
            CONF_PROFILE_INTERVAL: 30,
            CONF_REPOSITORY_INTERVAL: 60,
            CONF_HISTORY_YEARS: 5,
            CONF_CONTRIBUTION_TIME_ZONE: "Europe/Zurich",
            CONF_INCLUDE_RESTRICTED: False,
            CONF_LANGUAGE_WEIGHTING: "repo_count",
        },
    )

    assert settings.profile_interval == timedelta(minutes=30)
    assert settings.repository_interval == timedelta(hours=1)
    assert settings.history_years == 5
    assert settings.contribution_time_zone == ZoneInfo("Europe/Zurich")
    assert settings.include_restricted is False
    assert settings.language_weighting == "repo_count"


async def test_unknown_time_zone_falls_back_to_the_default(
    hass: HomeAssistant,
) -> None:
    settings = await Settings.async_from_options(
        hass, {CONF_CONTRIBUTION_TIME_ZONE: "Mars/Base"}
    )

    assert settings.contribution_time_zone == ZoneInfo("America/Los_Angeles")


async def test_resolve_time_zone(hass: HomeAssistant) -> None:
    assert await async_resolve_time_zone(hass, "Europe/Zurich") == ZoneInfo(
        "Europe/Zurich"
    )
    assert await async_resolve_time_zone(hass, "Mars/Base") is None
    assert await async_resolve_time_zone(hass, "") is None


async def test_unresolvable_default_aborts_the_setup(hass: HomeAssistant) -> None:
    with (
        patch.object(dt_util, "async_get_time_zone", return_value=None),
        pytest.raises(ConfigEntryError),
    ):
        await Settings.async_from_options(hass, {})
