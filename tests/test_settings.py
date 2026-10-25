"""Tests for the typed options."""

from datetime import timedelta
from zoneinfo import ZoneInfo

from custom_components.github_pulse.const import (
    CONF_CONTRIBUTION_TIME_ZONE,
    CONF_HISTORY_YEARS,
    CONF_INCLUDE_RESTRICTED,
    CONF_LANGUAGE_WEIGHTING,
    CONF_PROFILE_INTERVAL,
    CONF_REPOSITORY_INTERVAL,
)
from custom_components.github_pulse.settings import Settings, is_valid_time_zone


def test_defaults_apply_to_empty_options() -> None:
    settings = Settings.from_options({})

    assert settings.profile_interval == timedelta(minutes=15)
    assert settings.repository_interval == timedelta(minutes=15)
    assert settings.history_years == 3
    assert settings.contribution_time_zone == ZoneInfo("America/Los_Angeles")
    assert settings.include_restricted is True
    assert settings.language_weighting == "commit_weighted"


def test_stored_options_override_the_defaults() -> None:
    settings = Settings.from_options(
        {
            CONF_PROFILE_INTERVAL: 30,
            CONF_REPOSITORY_INTERVAL: 60,
            CONF_HISTORY_YEARS: 5,
            CONF_CONTRIBUTION_TIME_ZONE: "Europe/Zurich",
            CONF_INCLUDE_RESTRICTED: False,
            CONF_LANGUAGE_WEIGHTING: "repo_count",
        }
    )

    assert settings.profile_interval == timedelta(minutes=30)
    assert settings.repository_interval == timedelta(hours=1)
    assert settings.history_years == 5
    assert settings.contribution_time_zone == ZoneInfo("Europe/Zurich")
    assert settings.include_restricted is False
    assert settings.language_weighting == "repo_count"


def test_unknown_time_zone_falls_back_to_the_default() -> None:
    settings = Settings.from_options({CONF_CONTRIBUTION_TIME_ZONE: "Mars/Base"})

    assert settings.contribution_time_zone == ZoneInfo("America/Los_Angeles")


def test_is_valid_time_zone() -> None:
    assert is_valid_time_zone("Europe/Zurich")
    assert not is_valid_time_zone("Mars/Base")
    assert not is_valid_time_zone("")
