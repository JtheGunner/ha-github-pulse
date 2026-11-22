"""State and attribute snapshots of the repository sensors."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import pytest
from custom_components.github_pulse.const import (
    CONF_ACTIONS,
    CONF_MODULES,
    CONF_OWNER,
    CONF_REPOSITORY,
    CONF_TOKEN_TYPE,
    DOMAIN,
    SUBENTRY_REPOSITORY,
)
from custom_components.github_pulse.sensor_repository import REPOSITORY_SENSORS
from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import ConfigSubentryData
from homeassistant.const import CONF_ACCESS_TOKEN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from tests.fake_http import FakeResponse, FakeSession
from tests.test_repository_fetch import RAW

NOW = datetime(2026, 10, 25, 12, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _freeze(freezer: FrozenDateTimeFactory) -> None:
    freezer.move_to(NOW)


class _Session(FakeSession):
    """Answer the batched repository query; the second repo is unreadable."""

    def request(self, method: str, url: str, **kwargs: Any) -> FakeResponse:
        if "/releases" in url:
            return FakeResponse(
                body=[{"assets": [{"download_count": 100}, {"download_count": 20}]}]
            )
        return FakeResponse(
            body={
                "data": {
                    "r0": RAW,
                    "r1": None,
                    "p0": {"issueCount": 6},
                    "i0": {"issueCount": 9},
                }
            }
        )


async def _setup(
    hass: HomeAssistant,
    patch_session: Callable[[FakeSession], None],
    *,
    names: tuple[str, ...] = ("Octocat/Hello-World", "octocat/hidden"),
) -> MockConfigEntry:
    patch_session(_Session())
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="octocat",
        data={
            CONF_ACCESS_TOKEN: "token",
            CONF_OWNER: "octocat",
            CONF_TOKEN_TYPE: "classic",
            CONF_MODULES: ["repositories"],
        },
        subentries_data=[
            ConfigSubentryData(
                data={CONF_REPOSITORY: name, CONF_ACTIONS: False},
                subentry_type=SUBENTRY_REPOSITORY,
                title=name,
                unique_id=name.lower(),
            )
            for name in names
        ],
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _state(hass: HomeAssistant, repo: str, key: str) -> Any:
    registry = er.async_get(hass)
    unique_id = next(
        e.unique_id
        for e in registry.entities.values()
        if e.unique_id.endswith(f"{repo.lower()}_{key}")
    )
    entity_id = registry.async_get_entity_id("sensor", DOMAIN, unique_id)
    return hass.states.get(entity_id)


async def test_default_sensors_report_the_fixture(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None]
) -> None:
    await _setup(hass, patch_session)
    repo = "Octocat/Hello-World"

    assert _state(hass, repo, "stars").state == "42"
    assert _state(hass, repo, "forks").state == "7"
    assert _state(hass, repo, "open_issues").state == "3"
    assert _state(hass, repo, "open_pull_requests").state == "2"
    release = _state(hass, repo, "latest_release")
    assert release.state == "v1.2.0"
    assert release.attributes["url"].endswith("/releases/tag/v1.2.0")
    assert release.attributes["prerelease"] is False
    assert _state(hass, repo, "ci_state").state == "failure"


async def test_activity_sensors_are_on_by_default_and_count_all_authors(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None]
) -> None:
    await _setup(hass, patch_session)
    repo = "Octocat/Hello-World"

    assert _state(hass, repo, "commits_this_month").state == "4"
    assert _state(hass, repo, "active_days_this_month").state == "3"
    assert _state(hass, repo, "pull_requests_this_month").state == "6"
    assert _state(hass, repo, "issues_this_month").state == "9"
    assert _state(hass, repo, "commits_vs_last_month").state == "100.0"
    last_year = _state(hass, repo, "commits_vs_last_year")
    assert last_year.state == "-50.0"
    assert last_year.attributes["commits"] == 4
    assert last_year.attributes["commits_in_comparison_span"] == 8
    assert last_year.attributes["elapsed_days"] == 25
    assert _state(hass, repo, "active_days_this_month").attributes["truncated"] is False


async def test_activity_sensors_are_unknown_without_a_default_branch(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None]
) -> None:
    class Empty(_Session):
        def request(self, method: str, url: str, **kwargs: Any) -> FakeResponse:
            if "/releases" in url:
                return super().request(method, url, **kwargs)
            return FakeResponse(
                body={"data": {"r0": {**RAW, "defaultBranchRef": None}, "r1": None}}
            )

    patch_session(Empty())
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="octocat",
        data={
            CONF_ACCESS_TOKEN: "token",
            CONF_OWNER: "octocat",
            CONF_TOKEN_TYPE: "classic",
            CONF_MODULES: ["repositories"],
        },
        subentries_data=[
            ConfigSubentryData(
                data={CONF_REPOSITORY: "Octocat/Hello-World", CONF_ACTIONS: False},
                subentry_type=SUBENTRY_REPOSITORY,
                title="Octocat/Hello-World",
                unique_id="octocat/hello-world",
            )
        ],
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    for key in (
        "commits_this_month",
        "active_days_this_month",
        "pull_requests_this_month",
        "issues_this_month",
        "commits_vs_last_month",
        "commits_vs_last_year",
    ):
        assert _state(hass, "Octocat/Hello-World", key).state == "unknown", key


async def test_optional_sensors_are_disabled_by_default(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None]
) -> None:
    await _setup(hass, patch_session, names=("Octocat/Hello-World",))
    registry = er.async_get(hass)

    for description in REPOSITORY_SENSORS:
        entry = next(
            e
            for e in registry.entities.values()
            if e.unique_id.endswith(f"hello-world_{description.key}")
        )
        expected = (
            None
            if description.entity_registry_enabled_default
            else er.RegistryEntryDisabler.INTEGRATION
        )
        assert entry.disabled_by is expected, description.key


async def test_each_repository_gets_its_own_device_and_subentry_link(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None]
) -> None:
    entry = await _setup(hass, patch_session)
    devices = dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)

    assert {d.name for d in devices} == {"Octocat/Hello-World", "octocat/hidden"}
    registry = er.async_get(hass)
    subentry_ids = {
        e.config_subentry_id
        for e in registry.entities.values()
        if e.config_entry_id == entry.entry_id
    }
    assert subentry_ids == set(entry.subentries)


async def test_an_unreadable_repository_is_unavailable_not_broken(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None]
) -> None:
    await _setup(hass, patch_session)

    assert _state(hass, "octocat/hidden", "stars").state == "unavailable"
    assert _state(hass, "Octocat/Hello-World", "stars").state == "42"


async def test_enabling_the_downloads_sensor_fetches_that_group(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None]
) -> None:
    entry = await _setup(hass, patch_session, names=("Octocat/Hello-World",))
    registry = er.async_get(hass)
    total = next(
        e for e in registry.entities.values() if e.unique_id.endswith("total_downloads")
    )
    days = next(
        e
        for e in registry.entities.values()
        if e.unique_id.endswith("days_since_last_commit")
    )
    registry.async_update_entity(total.entity_id, disabled_by=None)
    registry.async_update_entity(days.entity_id, disabled_by=None)
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get(total.entity_id).state == "120"
    assert hass.states.get(days.entity_id).state == "1"


TRAFFIC_VIEWS = {
    "count": 27,
    "uniques": 12,
    "views": [
        {"timestamp": "2026-10-14T00:00:00Z", "count": 8, "uniques": 6},
        {"timestamp": "2026-10-20T00:00:00Z", "count": 10, "uniques": 7},
        {"timestamp": "2026-10-22T00:00:00Z", "count": 9, "uniques": 7},
    ],
}
TRAFFIC_CLONES = {"count": 30, "uniques": 6, "clones": []}
TRAFFIC_REFERRERS = [
    {"referrer": "Google", "count": 20, "uniques": 9},
    {"referrer": "github.com", "count": 7, "uniques": 3},
]
TRAFFIC_PATHS = [
    {"path": "/Octocat/Hello-World", "title": "Hello", "count": 22, "uniques": 10}
]
TRAFFIC_KEYS = (
    "unique_visitors_14d",
    "views_14d",
    "unique_cloners_14d",
    "clones_14d",
    "peak_visitor_day",
    "top_referrer",
    "top_path",
    "visitor_trend",
    "clone_visitor_ratio",
)


class _TrafficSession(_Session):
    """Also answer the traffic endpoints, or refuse them, and record the paths."""

    def __init__(self, *, forbidden: bool = False) -> None:
        super().__init__()
        self.traffic_urls: list[str] = []
        self._forbidden = forbidden

    def request(self, method: str, url: str, **kwargs: Any) -> FakeResponse:
        if "/traffic/" not in url:
            return super().request(method, url, **kwargs)
        self.traffic_urls.append(url)
        if self._forbidden:
            return FakeResponse(
                status=403, body={"message": "Resource not accessible by integration"}
            )
        bodies = {
            "/traffic/views": TRAFFIC_VIEWS,
            "/traffic/clones": TRAFFIC_CLONES,
            "/traffic/popular/referrers": TRAFFIC_REFERRERS,
            "/traffic/popular/paths": TRAFFIC_PATHS,
        }
        return FakeResponse(body=next(b for p, b in bodies.items() if p in url))


async def _setup_traffic(
    hass: HomeAssistant,
    patch_session: Callable[[FakeSession], None],
    session: _TrafficSession,
    *,
    enable: tuple[str, ...],
) -> MockConfigEntry:
    patch_session(session)
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="octocat",
        data={
            CONF_ACCESS_TOKEN: "token",
            CONF_OWNER: "octocat",
            CONF_TOKEN_TYPE: "classic",
            CONF_MODULES: ["repositories"],
        },
        subentries_data=[
            ConfigSubentryData(
                data={CONF_REPOSITORY: "Octocat/Hello-World", CONF_ACTIONS: False},
                subentry_type=SUBENTRY_REPOSITORY,
                title="Octocat/Hello-World",
                unique_id="octocat/hello-world",
            )
        ],
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    if enable:
        registry = er.async_get(hass)
        for key in enable:
            entity = next(
                e
                for e in registry.entities.values()
                if e.unique_id.endswith(f"hello-world_{key}")
            )
            registry.async_update_entity(entity.entity_id, disabled_by=None)
        await hass.config_entries.async_reload(entry.entry_id)
        await hass.async_block_till_done()
    return entry


async def test_the_traffic_group_is_not_fetched_while_every_traffic_sensor_is_off(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None]
) -> None:
    session = _TrafficSession()

    await _setup_traffic(hass, patch_session, session, enable=())

    assert session.traffic_urls == []


async def test_enabling_traffic_sensors_reports_the_traffic(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None]
) -> None:
    session = _TrafficSession()
    await _setup_traffic(hass, patch_session, session, enable=TRAFFIC_KEYS)
    repo = "Octocat/Hello-World"

    assert _state(hass, repo, "unique_visitors_14d").state == "12"
    assert _state(hass, repo, "views_14d").state == "27"
    assert _state(hass, repo, "unique_cloners_14d").state == "6"
    assert _state(hass, repo, "clones_14d").state == "30"
    peak = _state(hass, repo, "peak_visitor_day")
    assert peak.state == "2026-10-22"
    assert peak.attributes["visitors"] == 7
    assert peak.attributes["views"] == 9
    referrer = _state(hass, repo, "top_referrer")
    assert referrer.state == "Google"
    assert referrer.attributes["referrers"][0] == {
        "name": "Google",
        "views": 20,
        "visitors": 9,
    }
    assert len(referrer.attributes["referrers"]) == 2
    path = _state(hass, repo, "top_path")
    assert path.state == "/Octocat/Hello-World"
    assert path.attributes["paths"][0]["visitors"] == 10
    trend = _state(hass, repo, "visitor_trend")
    assert trend.state == "100.0"
    assert trend.attributes["recent_daily_average"] == 2.0
    assert trend.attributes["previous_daily_average"] == 1.0
    assert _state(hass, repo, "clone_visitor_ratio").state == "0.5"


async def test_traffic_sensors_are_unavailable_without_push_access(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None]
) -> None:
    session = _TrafficSession(forbidden=True)
    await _setup_traffic(hass, patch_session, session, enable=TRAFFIC_KEYS)

    for key in TRAFFIC_KEYS:
        assert _state(hass, "Octocat/Hello-World", key).state == "unavailable", key
    assert _state(hass, "Octocat/Hello-World", "stars").state == "42"
