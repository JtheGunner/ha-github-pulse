"""Tests for the rhythm analytics, the events fetch and the rhythm sensors."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

from custom_components.github_pulse.analytics.rhythm import MIN_EVENTS, rhythm
from custom_components.github_pulse.api import GitHubClient
from custom_components.github_pulse.const import (
    CONF_HISTORY_YEARS,
    CONF_MODULES,
    CONF_OWNER,
    CONF_TOKEN_TYPE,
    DOMAIN,
)
from custom_components.github_pulse.profile_coordinator import GROUP_RHYTHM
from custom_components.github_pulse.rhythm_fetch import fetch_event_times
from homeassistant.const import CONF_ACCESS_TOKEN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from tests.fake_http import FakeResponse, FakeSession

ZURICH = ZoneInfo("Europe/Zurich")


def _at(hour: int, day: int = 10) -> datetime:
    return datetime(2026, 10, day, hour, 30, tzinfo=UTC)


def test_hours_are_counted_in_the_given_time_zone() -> None:
    times = [_at(7)] * 12  # 07:30 UTC is 09:30 in Zurich (summer time)

    assert rhythm(times, UTC).most_active_hour == 7
    assert rhythm(times, ZURICH).most_active_hour == 9


def test_the_night_owl_share_uses_local_night_hours() -> None:
    times = [_at(21)] * 6 + [_at(12)] * 6  # 21:30 UTC is 23:30 in Zurich

    assert rhythm(times, UTC).night_owl_share == 0
    assert rhythm(times, ZURICH).night_owl_share == 0.5


def test_a_local_date_change_is_handled() -> None:
    times = [datetime(2026, 10, 10, 22, 30, tzinfo=UTC)] * MIN_EVENTS

    assert rhythm(times, ZURICH).most_active_hour == 0


def test_sparse_data_gives_no_rhythm() -> None:
    result = rhythm([_at(10)] * (MIN_EVENTS - 1), UTC)

    assert result.events == MIN_EVENTS - 1
    assert result.most_active_hour is None
    assert result.night_owl_share is None


def test_no_events_at_all() -> None:
    assert rhythm([], UTC).events == 0


def test_the_earliest_hour_wins_a_tie() -> None:
    times = [_at(15)] * 6 + [_at(9)] * 6

    assert rhythm(times, UTC).most_active_hour == 9


def test_the_night_window_runs_from_22_to_5() -> None:
    hours = [22, 23, 0, 4, 5, 12, 13, 14, 15, 16]
    times = [_at(h) for h in hours]

    assert rhythm(times, UTC).night_owl_share == 0.4


async def test_event_times_are_read_from_up_to_three_pages() -> None:
    client = AsyncMock(spec=GitHubClient)
    client.rest_get_pages.return_value = [
        {"created_at": "2026-10-10T08:15:00Z"},
        {"type": "PushEvent"},
        {"created_at": "2026-10-10T09:45:00Z"},
    ]

    times = await fetch_event_times(client, "octocat")

    assert times == [_at(8).replace(minute=15), _at(9).replace(minute=45)]
    client.rest_get_pages.assert_awaited_once_with(
        "/users/octocat/events", {"per_page": "100"}, max_pages=3
    )


class _EventsSession(FakeSession):
    def request(self, method: str, url: str, **kwargs: Any) -> FakeResponse:
        if url.endswith("/users/octocat/events"):
            events = [{"created_at": "2026-10-10T23:30:00Z"}] * 12
            return FakeResponse(body=events)
        return super().request(method, url, **kwargs)


async def test_the_sensors_report_the_rhythm_when_enabled(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None]
) -> None:
    await hass.config.async_set_time_zone("UTC")
    patch_session(_EventsSession())
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="octocat",
        data={
            CONF_ACCESS_TOKEN: "token",
            CONF_OWNER: "octocat",
            CONF_TOKEN_TYPE: "classic",
            CONF_MODULES: ["profile"],
        },
        options={CONF_HISTORY_YEARS: 1},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    assert GROUP_RHYTHM not in entry.runtime_data.profile.active_groups

    registry = er.async_get(hass)
    for key in ("most_active_hour", "night_owl_score"):
        sensor = next(
            e for e in registry.entities.values() if e.unique_id.endswith(key)
        )
        registry.async_update_entity(sensor.entity_id, disabled_by=None)
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    states = {
        e.unique_id.split("_", 1)[1]: hass.states.get(e.entity_id)
        for e in registry.entities.values()
        if e.unique_id.endswith(("most_active_hour", "night_owl_score"))
    }
    assert states["most_active_hour"].state == "23"
    assert states["night_owl_score"].state == "100.0"
    assert states["night_owl_score"].attributes["approximate"] is True
    assert states["night_owl_score"].attributes["events_analysed"] == 12
