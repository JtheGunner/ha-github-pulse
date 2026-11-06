"""Typed view of the options a user can change."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import timedelta
from typing import Any
from zoneinfo import ZoneInfo

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError
from homeassistant.util import dt as dt_util

from .const import (
    CONF_CONTRIBUTION_TIME_ZONE,
    CONF_HISTORY_YEARS,
    CONF_IMPORT_STATISTICS,
    CONF_INCLUDE_RESTRICTED,
    CONF_LANGUAGE_WEIGHTING,
    CONF_PROFILE_INTERVAL,
    CONF_REPOSITORY_INTERVAL,
    DEFAULT_CONTRIBUTION_TIME_ZONE,
    DEFAULT_HISTORY_YEARS,
    DEFAULT_IMPORT_STATISTICS,
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
    import_statistics: bool

    @classmethod
    async def async_from_options(
        cls, hass: HomeAssistant, options: Mapping[str, Any]
    ) -> Settings:
        """Build settings from stored options; missing or invalid values fall back.

        The time zone is resolved through Home Assistant so that reading the
        tz database never blocks the event loop.
        """
        zone = await _async_zone(
            hass,
            options.get(CONF_CONTRIBUTION_TIME_ZONE, DEFAULT_CONTRIBUTION_TIME_ZONE),
        )
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
            contribution_time_zone=zone,
            include_restricted=bool(
                options.get(CONF_INCLUDE_RESTRICTED, DEFAULT_INCLUDE_RESTRICTED)
            ),
            language_weighting=str(
                options.get(CONF_LANGUAGE_WEIGHTING, WEIGHTING_COMMITS)
            ),
            import_statistics=bool(
                options.get(CONF_IMPORT_STATISTICS, DEFAULT_IMPORT_STATISTICS)
            ),
        )


async def async_resolve_time_zone(hass: HomeAssistant, name: str) -> ZoneInfo | None:
    """Return the IANA time zone, or None for an unknown name."""
    try:
        zone = await dt_util.async_get_time_zone(name)
    except ValueError, OSError:
        return None
    return zone if isinstance(zone, ZoneInfo) else None


async def _async_zone(hass: HomeAssistant, name: str) -> ZoneInfo:
    """Return the zone, falling back to the default for an unknown name.

    Raises ConfigEntryError when not even the default zone can be loaded,
    which means the tz database of the host is unusable.
    """
    for candidate in (name, DEFAULT_CONTRIBUTION_TIME_ZONE):
        if zone := await async_resolve_time_zone(hass, candidate):
            return zone
    raise ConfigEntryError(
        f"Time zone database is unavailable (tried {DEFAULT_CONTRIBUTION_TIME_ZONE})"
    )
