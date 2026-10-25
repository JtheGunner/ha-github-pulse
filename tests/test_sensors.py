"""State and attribute snapshots of the profile sensors for a fixed fixture."""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from custom_components.github_pulse.const import (
    CONF_HISTORY_YEARS,
    CONF_INCLUDE_RESTRICTED,
    CONF_LANGUAGE_WEIGHTING,
    CONF_MODULES,
    CONF_OWNER,
    CONF_TOKEN_TYPE,
    DOMAIN,
)
from freezegun.api import FrozenDateTimeFactory
from homeassistant.const import CONF_ACCESS_TOKEN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from tests.fake_http import FakeResponse, FakeSession

NOW = datetime(2026, 10, 25, 12, tzinfo=UTC)
TODAY = date(2026, 10, 25)


def _totals(commits: int, prs: int = 0, restricted: int = 0) -> dict[str, int]:
    return {
        "totalCommitContributions": commits,
        "totalPullRequestContributions": prs,
        "totalIssueContributions": 0,
        "totalPullRequestReviewContributions": 0,
        "restrictedContributionsCount": restricted,
    }


def _calendar_response() -> FakeResponse:
    # A three-day streak ending today; Monday 2026-10-19 is the busiest weekday.
    days = [
        {"date": (TODAY - timedelta(days=offset)).isoformat(), "contributionCount": 1}
        for offset in range(3)
    ]
    days.append({"date": "2026-10-19", "contributionCount": 9})
    calendar = {"contributionCalendar": {"weeks": [{"contributionDays": days}]}}
    return FakeResponse(body={"data": {"user": {"contributionsCollection": calendar}}})


def _contribution_response(query: str) -> FakeResponse:
    if "lastMonth" in query:
        user = {
            "current": _totals(30, prs=4, restricted=6),
            "lastMonth": _totals(20),
            "lastYear": _totals(60),
        }
    else:
        aliases = re.findall(r"(m\d{6}): ", query)
        user = {a: _totals(100 if a == "m202603" else 10) for a in aliases}
    return FakeResponse(body={"data": {"user": user}})


def _language_response(query: str) -> FakeResponse:
    """PHP-heavy in 2026, Go-heavy in 2025."""

    def repo(commits: int, language: str) -> dict[str, Any]:
        return {
            "contributions": {"totalCount": commits},
            "repository": {
                "languages": {"edges": [{"size": 100, "node": {"name": language}}]}
            },
        }

    user = {}
    for alias in re.findall(r"(m\d{6}): ", query):
        year_repos = (
            [repo(30, "PHP"), repo(10, "Go")]
            if alias.startswith("m2026")
            else [repo(40, "Go")]
        )
        user[alias] = {"commitContributionsByRepository": year_repos}
    return FakeResponse(body={"data": {"user": user}})


class _Session(FakeSession):
    """Answer the integration's queries from a fixed fixture."""

    def request(self, method: str, url: str, **kwargs: Any) -> FakeResponse:
        query = (kwargs.get("json") or {}).get("query", "")
        if "contributionCalendar" in query:
            return _calendar_response()
        if "commitContributionsByRepository" in query:
            return _language_response(query)
        if "contributionsCollection" in query:
            return _contribution_response(query)
        return FakeResponse(status=404, body={})


@pytest.fixture(autouse=True)
def _freeze(freezer: FrozenDateTimeFactory) -> None:
    freezer.move_to(NOW)


async def _setup(
    hass: HomeAssistant,
    patch_session: Callable[[FakeSession], None],
    options: dict[str, Any] | None = None,
    session: FakeSession | None = None,
) -> MockConfigEntry:
    patch_session(session or _Session())
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="octocat",
        data={
            CONF_ACCESS_TOKEN: "token",
            CONF_OWNER: "octocat",
            CONF_TOKEN_TYPE: "classic",
            CONF_MODULES: ["profile"],
        },
        options=options or {CONF_HISTORY_YEARS: 2},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _state(hass: HomeAssistant, key: str) -> Any:
    registry = er.async_get(hass)
    entry = next(e for e in registry.entities.values() if e.unique_id.endswith(key))
    return hass.states.get(entry.entity_id)


async def test_default_sensors_report_the_fixture_values(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None]
) -> None:
    await _setup(hass, patch_session)

    contributions = _state(hass, "contributions_this_month")
    assert contributions.state == "40"
    assert contributions.attributes["visible"] == 34
    assert contributions.attributes["restricted"] == 6
    assert _state(hass, "commits_this_month").state == "30"
    assert _state(hass, "pull_requests_this_month").state == "4"
    assert _state(hass, "commits_vs_last_month").state == "50.0"
    assert _state(hass, "commits_vs_last_month").attributes["elapsed_days"] == 25
    assert _state(hass, "commits_vs_last_year").state == "-50.0"
    assert _state(hass, "busiest_month").state == "2026-03"
    assert _state(hass, "busiest_month").attributes["contributions"] == 100
    assert _state(hass, "current_streak").state == "3"
    assert _state(hass, "longest_streak").state == "3"


async def test_restricted_contributions_can_be_left_out(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None]
) -> None:
    await _setup(
        hass,
        patch_session,
        {CONF_HISTORY_YEARS: 1, CONF_INCLUDE_RESTRICTED: False},
    )

    state = _state(hass, "contributions_this_month")
    assert state.state == "34"
    assert state.attributes["includes_restricted"] is False


async def test_optional_sensors_are_disabled_by_default(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None]
) -> None:
    await _setup(hass, patch_session)
    registry = er.async_get(hass)

    for key in (
        "reviews_this_month",
        "issues_this_month",
        "active_days_this_month",
        "most_productive_weekday",
    ):
        entry = next(e for e in registry.entities.values() if e.unique_id.endswith(key))
        assert entry.disabled_by is er.RegistryEntryDisabler.INTEGRATION
        assert hass.states.get(entry.entity_id) is None


async def test_optional_calendar_sensor_reports_the_strongest_weekday(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None]
) -> None:
    entry = await _setup(hass, patch_session)
    registry = er.async_get(hass)
    sensor = next(
        e for e in registry.entities.values() if e.unique_id.endswith("weekday")
    )
    registry.async_update_entity(sensor.entity_id, disabled_by=None)
    active_days = next(
        e
        for e in registry.entities.values()
        if e.unique_id.endswith("active_days_this_month")
    )
    registry.async_update_entity(active_days.entity_id, disabled_by=None)
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get(sensor.entity_id).state == "monday"
    assert _state(hass, "active_days_this_month").state == "4"


async def test_a_group_without_enabled_sensors_is_not_fetched(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None]
) -> None:
    session = _Session()
    patch_session(session)
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="octocat",
        data={
            CONF_ACCESS_TOKEN: "token",
            CONF_OWNER: "octocat",
            CONF_TOKEN_TYPE: "classic",
            CONF_MODULES: ["profile"],
        },
        options={CONF_HISTORY_YEARS: 2},
    )
    entry.add_to_hass(hass)
    registry = er.async_get(hass)
    for key in (
        "current_streak",
        "longest_streak",
        "active_days_this_month",
        "most_productive_weekday",
    ):
        registry.async_get_or_create(
            "sensor",
            DOMAIN,
            f"{entry.entry_id}_{key}",
            config_entry=entry,
            disabled_by=er.RegistryEntryDisabler.USER,
        )

    assert await hass.config_entries.async_setup(entry.entry_id)

    sent = [r.json["query"] for r in session.requests if r.json]
    assert not any("contributionCalendar" in query for query in sent)
    assert _state(hass, "commits_this_month").state == "30"


class _NoCurrentSession(_Session):
    """Fail only the current-period group."""

    def request(self, method: str, url: str, **kwargs: Any) -> FakeResponse:
        query = (kwargs.get("json") or {}).get("query", "")
        if "lastMonth" in query:
            return FakeResponse(status=404, body={"message": "Not Found"})
        return super().request(method, url, **kwargs)


async def test_history_sensors_survive_a_failed_current_group(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None]
) -> None:
    await _setup(hass, patch_session, session=_NoCurrentSession())

    assert _state(hass, "busiest_month").state == "2026-03"
    assert _state(hass, "current_streak").state == "3"
    assert _state(hass, "commits_this_month").state == "unavailable"


async def test_top_language_is_marked_as_an_estimate(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None]
) -> None:
    await _setup(hass, patch_session)

    state = _state(hass, "top_language")
    assert state.state == "PHP"
    assert state.attributes["method"] == "estimated"
    assert state.attributes["ranking"] == {"PHP": 75.0, "Go": 25.0}
    assert state.attributes["weighting"] == "commit_weighted"
    assert state.attributes["truncated"] is False


async def test_repo_count_weighting_changes_the_ranking(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None]
) -> None:
    await _setup(
        hass,
        patch_session,
        {CONF_HISTORY_YEARS: 2, CONF_LANGUAGE_WEIGHTING: "repo_count"},
    )

    assert _state(hass, "top_language").attributes["ranking"] == {
        "Go": 50.0,
        "PHP": 50.0,
    }


async def test_language_shift_reports_the_top_gainer(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None]
) -> None:
    entry = await _setup(hass, patch_session)
    registry = er.async_get(hass)
    sensor = next(
        e for e in registry.entities.values() if e.unique_id.endswith("language_shift")
    )
    registry.async_update_entity(sensor.entity_id, disabled_by=None)
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get(sensor.entity_id)
    assert state.state == "PHP"
    assert state.attributes["gainer_points"] == 75.0
    assert state.attributes["loser"] == "Go"
    assert state.attributes["loser_points"] == -75.0
    assert state.attributes["compared_with"] == 2025
