"""Services of the integration."""

from __future__ import annotations

from typing import Any

import probatio
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
)
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .analytics.history import MonthKey
from .analytics.languages import shares
from .const import DOMAIN, WEIGHTING_COMMITS
from .models import GitHubPulseConfigEntry
from .profile_coordinator import GROUP_HISTORY, GROUP_LANGUAGES

SERVICE_GET_HISTORY = "get_history"
ATTR_CONFIG_ENTRY_ID = "config_entry_id"
ATTR_START = "start"
ATTR_END = "end"
ATTR_INCLUDE_LANGUAGES = "include_languages"
TOP_LANGUAGES = 10

GET_HISTORY_SCHEMA = probatio.Schema(
    {
        probatio.Optional(ATTR_CONFIG_ENTRY_ID): cv.string,
        probatio.Optional(ATTR_START): cv.string,
        probatio.Optional(ATTR_END): cv.string,
        probatio.Optional(ATTR_INCLUDE_LANGUAGES, default=True): cv.boolean,
    }
)


def async_setup_services(hass: HomeAssistant) -> None:
    """Register the services."""
    hass.services.async_register(
        DOMAIN,
        SERVICE_GET_HISTORY,
        _async_get_history,
        schema=GET_HISTORY_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )


def _entry(hass: HomeAssistant, entry_id: str | None) -> GitHubPulseConfigEntry:
    """Return the addressed entry, or the only loaded one."""
    entries = [
        entry
        for entry in hass.config_entries.async_loaded_entries(DOMAIN)
        if entry_id is None or entry.entry_id == entry_id
    ]
    if not entries:
        raise ServiceValidationError(
            translation_domain=DOMAIN, translation_key="no_entry"
        )
    if len(entries) > 1:
        raise ServiceValidationError(
            translation_domain=DOMAIN, translation_key="entry_required"
        )
    return entries[0]


def _month(value: str | None, field: str) -> MonthKey | None:
    if value is None:
        return None
    try:
        key = MonthKey.parse(value)
        if not 1 <= key.month <= 12:
            raise ValueError
    except ValueError as err:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="invalid_month",
            translation_placeholders={"field": field, "value": value},
        ) from err
    return key


def _in_range(key: MonthKey, start: MonthKey | None, end: MonthKey | None) -> bool:
    return (start is None or key >= start) and (end is None or key <= end)


async def _async_get_history(call: ServiceCall) -> ServiceResponse:
    """Return the monthly series, and the language series on request."""
    entry = _entry(call.hass, call.data.get(ATTR_CONFIG_ENTRY_ID))
    profile = entry.runtime_data.profile
    if profile is None:
        raise ServiceValidationError(
            translation_domain=DOMAIN, translation_key="profile_disabled"
        )
    start = _month(call.data.get(ATTR_START), ATTR_START)
    end = _month(call.data.get(ATTR_END), ATTR_END)
    if start is not None and end is not None and start > end:
        raise ServiceValidationError(
            translation_domain=DOMAIN, translation_key="range_reversed"
        )

    include_restricted = profile.settings.include_restricted
    response: dict[str, Any] = {
        "months": [
            {
                "month": key.label,
                "commits": stats.commits,
                "pull_requests": stats.pull_requests,
                "issues": stats.issues,
                "reviews": stats.reviews,
                "restricted": stats.restricted,
                "contributions": stats.total(include_restricted=include_restricted),
            }
            for key, stats in sorted(
                (profile.data or {}).get(GROUP_HISTORY, {}).items()
            )
            if _in_range(key, start, end)
        ]
    }
    if call.data[ATTR_INCLUDE_LANGUAGES]:
        by_commits = profile.settings.language_weighting == WEIGHTING_COMMITS
        response["languages"] = {
            "method": "estimated",
            "weighting": profile.settings.language_weighting,
            "months": [
                {
                    "month": key.label,
                    "shares": {
                        name: round(share * 100, 2)
                        for name, share in shares(
                            month, by_commits=by_commits, top=TOP_LANGUAGES
                        ).items()
                    },
                    "truncated": month.truncated,
                }
                for key, month in sorted(
                    (profile.data or {}).get(GROUP_LANGUAGES, {}).items()
                )
                if _in_range(key, start, end)
            ],
        }
    return response
