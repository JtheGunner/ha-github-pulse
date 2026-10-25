"""Typed view of the options a user can change."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .const import (
    CONF_CONTRIBUTION_TIME_ZONE,
    CONF_HISTORY_YEARS,
    CONF_INCLUDE_RESTRICTED,
    CONF_LANGUAGE_WEIGHTING,
    CONF_PROFILE_INTERVAL,
    CONF_REPOSITORY_INTERVAL,
    DEFAULT_CONTRIBUTION_TIME_ZONE,
    DEFAULT_HISTORY_YEARS,
    DEFAULT_INCLUDE_RESTRICTED,
    DEFAULT_PROFILE_INTERVAL,
    DEFAULT_REPOSITORY_INTERVAL,
    WEIGHTING_COMMITS,
)


@dataclass(frozen=True, slots=True)
class Settings:
    """Options of a config entry with defaults applied."""

    profile_interval: timedelta
    repository_interval: timedelta
    history_years: int
    contribution_time_zone: ZoneInfo
    include_restricted: bool
    language_weighting: str

    @classmethod
    def from_options(cls, options: Mapping[str, Any]) -> Settings:
        """Build settings from stored options; missing or invalid values fall back."""
        return cls(
            profile_interval=timedelta(
                minutes=options.get(CONF_PROFILE_INTERVAL, DEFAULT_PROFILE_INTERVAL)
            ),
            repository_interval=timedelta(
                minutes=options.get(
                    CONF_REPOSITORY_INTERVAL, DEFAULT_REPOSITORY_INTERVAL
                )
            ),
            history_years=int(options.get(CONF_HISTORY_YEARS, DEFAULT_HISTORY_YEARS)),
            contribution_time_zone=_zone(
                options.get(CONF_CONTRIBUTION_TIME_ZONE, DEFAULT_CONTRIBUTION_TIME_ZONE)
            ),
            include_restricted=bool(
                options.get(CONF_INCLUDE_RESTRICTED, DEFAULT_INCLUDE_RESTRICTED)
            ),
            language_weighting=str(
                options.get(CONF_LANGUAGE_WEIGHTING, WEIGHTING_COMMITS)
            ),
        )


def is_valid_time_zone(name: str) -> bool:
    """Return whether the name is a known IANA time zone."""
    try:
        ZoneInfo(name)
    except ZoneInfoNotFoundError, ValueError, OSError:
        return False
    return True


def _zone(name: str) -> ZoneInfo:
    """Return the zone, falling back to the default for an unknown name."""
    if is_valid_time_zone(name):
        return ZoneInfo(name)
    return ZoneInfo(DEFAULT_CONTRIBUTION_TIME_ZONE)
