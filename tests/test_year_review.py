"""Tests for the year in review: analytics, service and sensor."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, date, datetime
from typing import Any

import pytest
from custom_components.github_pulse.analytics.history import MonthKey, MonthStats
from custom_components.github_pulse.analytics.languages import LanguageMonth
from custom_components.github_pulse.analytics.year_review import (
    summary,
    year_in_review,
)
from custom_components.github_pulse.const import (
    CONF_HISTORY_YEARS,
    CONF_MODULES,
    CONF_OWNER,
    CONF_TOKEN_TYPE,
    DOMAIN,
)
from freezegun.api import FrozenDateTimeFactory
from homeassistant.const import CONF_ACCESS_TOKEN
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from tests.fake_http import FakeSession


def _stats(commits: int = 0, prs: int = 0) -> MonthStats:
    return MonthStats(commits, prs, 0, 0, 0)


def _language(name: str, score: float) -> LanguageMonth:
    return LanguageMonth({name: score}, {name: 1}, 0, 1, truncated=False)


def _review(year: int = 2025, **overrides: Any) -> Any:
    months = {
        MonthKey(2025, 2): _stats(commits=5),
        MonthKey(2025, 3): _stats(commits=30, prs=4),
        MonthKey(2025, 4): _stats(commits=10),
        MonthKey(2024, 12): _stats(commits=99),
    }
    languages = {
        MonthKey(2025, 3): _language("TypeScript", 30),
        MonthKey(2025, 4): _language("Python", 10),
    }
    daily = {date(2025, 3, d): 1 for d in range(1, 8)} | {date(2025, 6, 1): 1}
    args: dict[str, Any] = {
        "months": months,
        "languages": languages,
        "daily": daily,
        "include_restricted": False,
        "by_commits": True,
    } | overrides
    return year_in_review(year, **args)


def test_a_normal_year() -> None:
    review = _review()

    assert review.contributions == 49
    assert review.commits == 45
    assert review.pull_requests == 4
    assert review.active_months == 3
    assert review.busiest_month.month == 3
    assert review.top_language == "TypeScript"
    assert review.longest_streak == 7
    assert summary(review) == (
        "2025: 49 contributions, busiest in March, mostly TypeScript, "
        "longest streak 7 days"
    )


def test_other_years_are_not_mixed_in() -> None:
    assert _review(year=2024).contributions == 99


def test_a_year_with_little_data() -> None:
    review = _review(
        months={MonthKey(2025, 1): _stats(commits=1)}, languages={}, daily={}
    )

    assert review.contributions == 1
    assert review.top_language is None
    assert review.longest_streak is None
    assert summary(review) == "2025: 1 contributions, busiest in January"


def test_an_empty_year() -> None:
    review = _review(year=2019)

    assert review.contributions == 0
    assert review.busiest_month is None
    assert summary(review) == "2019: no contributions recorded"


@pytest.fixture(autouse=True)
def _freeze(freezer: FrozenDateTimeFactory) -> None:
    freezer.move_to(datetime(2026, 10, 25, 12, tzinfo=UTC))


async def _setup(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None]
) -> MockConfigEntry:
    patch_session(FakeSession())
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
    return entry


async def _call(hass: HomeAssistant, **data: Any) -> dict[str, Any]:
    return await hass.services.async_call(  # type: ignore[no-any-return]
        DOMAIN, "year_in_review", data, blocking=True, return_response=True
    )


async def test_the_service_defaults_to_the_current_year(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None]
) -> None:
    await _setup(hass, patch_session)

    response = await _call(hass)

    assert response["year"] == 2026
    assert response["contributions"] == 200  # ten months of 20
    assert response["language_method"] == "estimated"
    assert "contributions" in response["summary"]


async def test_the_service_summarises_a_partly_covered_year(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None]
) -> None:
    await _setup(hass, patch_session)

    response = await _call(hass, year=2025)

    assert response["contributions"] == 60  # October to December only


async def test_the_service_reports_a_year_without_data(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None]
) -> None:
    await _setup(hass, patch_session)

    response = await _call(hass, year=2010)

    assert response["contributions"] == 0
    assert response["summary"] == "2010: no contributions recorded"
    assert response["busiest_month"] is None


async def test_the_service_needs_the_profile_module(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None]
) -> None:
    patch_session(FakeSession())
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="octocat",
        data={
            CONF_ACCESS_TOKEN: "token",
            CONF_OWNER: "octocat",
            CONF_TOKEN_TYPE: "classic",
            CONF_MODULES: ["repositories"],
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)

    with pytest.raises(ServiceValidationError):
        await _call(hass)


async def test_enabling_the_sensor_fetches_what_it_needs(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None]
) -> None:
    entry = await _setup(hass, patch_session)
    registry = er.async_get(hass)
    sensor = next(
        e for e in registry.entities.values() if e.unique_id.endswith("year_in_review")
    )
    assert sensor.disabled

    registry.async_update_entity(sensor.entity_id, disabled_by=None)
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get(sensor.entity_id)
    assert state is not None
    assert state.state.startswith("2026: 200 contributions")
    assert state.attributes["language_method"] == "estimated"
    assert {
        "history",
        "languages",
        "calendar",
    } <= entry.runtime_data.profile.active_groups
