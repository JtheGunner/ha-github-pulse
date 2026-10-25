"""Tests for the opt-in statistics import."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest
from custom_components.github_pulse.analytics.history import MonthKey, MonthStats
from custom_components.github_pulse.analytics.languages import (
    RepoActivity,
    estimate_month,
)
from custom_components.github_pulse.const import (
    CONF_HISTORY_YEARS,
    CONF_IMPORT_STATISTICS,
    CONF_MODULES,
    CONF_OWNER,
    CONF_TOKEN_TYPE,
    DOMAIN,
)
from custom_components.github_pulse.statistics_import import (
    build_series,
    import_series,
    slug,
)
from freezegun.api import FrozenDateTimeFactory
from homeassistant.components.recorder import Recorder
from homeassistant.components.recorder.statistics import (
    get_last_statistics,
    list_statistic_ids,
)
from homeassistant.const import CONF_ACCESS_TOKEN
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.components.recorder.common import (
    async_wait_recording_done,
)

from tests.fake_http import FakeSession

ZONE = ZoneInfo("America/Los_Angeles")
HISTORY = {
    MonthKey(2026, 2): MonthStats(5, 1, 0, 0, 2),
    MonthKey(2026, 3): MonthStats(9, 2, 1, 1, 0),
}
LANGUAGES = {
    MonthKey(2026, 2): estimate_month([RepoActivity(10, {"C++": 1})]),
    MonthKey(2026, 3): estimate_month([RepoActivity(10, {"C++": 1, "Go": 1})]),
}


def _series(*, restricted: bool = True) -> dict[str, list[float]]:
    result = build_series(
        "Octo-Cat",
        HISTORY,
        LANGUAGES,
        zone=ZONE,
        include_restricted=restricted,
        by_commits=True,
    )
    return {s.metadata["statistic_id"]: [p["state"] for p in s.points] for s in result}


def test_slug_makes_language_names_id_safe() -> None:
    assert slug("C++") == "cplusplus"
    assert slug("C#") == "csharp"
    assert slug("Jupyter Notebook") == "jupyter_notebook"


def test_series_cover_commits_contributions_and_language_shares() -> None:
    series = _series()

    assert series["github_pulse:octo_cat_commits"] == [5.0, 9.0]
    assert series["github_pulse:octo_cat_contributions"] == [8.0, 13.0]
    assert series["github_pulse:octo_cat_language_cplusplus"] == [100.0, 50.0]
    assert series["github_pulse:octo_cat_language_go"] == [0.0, 50.0]
    assert series["github_pulse:octo_cat_language_other"] == [0.0, 0.0]


def test_restricted_contributions_can_be_left_out_of_the_total() -> None:
    assert _series(restricted=False)["github_pulse:octo_cat_contributions"] == [
        6.0,
        13.0,
    ]


def test_month_starts_fall_on_the_contribution_zone_midnight() -> None:
    series = build_series(
        "o", HISTORY, {}, zone=ZONE, include_restricted=True, by_commits=True
    )

    starts = [p["start"] for p in series[0].points]
    assert starts == [
        datetime(2026, 2, 1, 8, tzinfo=UTC),
        datetime(2026, 3, 1, 8, tzinfo=UTC),
    ]


def test_without_language_data_only_the_contribution_series_exist() -> None:
    series = build_series(
        "o", HISTORY, {}, zone=ZONE, include_restricted=True, by_commits=True
    )

    assert [s.metadata["statistic_id"] for s in series] == [
        "github_pulse:o_commits",
        "github_pulse:o_contributions",
    ]


async def _setup(
    hass: HomeAssistant,
    patch_session: Callable[[FakeSession], None],
    *,
    enabled: bool,
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
        options={CONF_HISTORY_YEARS: 1, CONF_IMPORT_STATISTICS: enabled},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    await async_wait_recording_done(hass)
    return entry


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(
    recorder_mock: Recorder, enable_custom_integrations: None
) -> None:
    """Start the recorder before Home Assistant, which its fixtures require."""


@pytest.fixture(autouse=True)
def _freeze(freezer: FrozenDateTimeFactory) -> None:
    freezer.move_to(datetime(2026, 10, 25, 12, tzinfo=UTC))


async def test_statistics_are_imported_when_enabled_and_reimport_is_idempotent(
    recorder_mock: Recorder,
    hass: HomeAssistant,
    patch_session: Callable[[FakeSession], None],
) -> None:
    entry = await _setup(hass, patch_session, enabled=True)

    ids = await recorder_mock.async_add_executor_job(
        list_statistic_ids, hass, None, None
    )
    commits = [i for i in ids if i["statistic_id"] == "github_pulse:octocat_commits"]
    assert commits

    await entry.runtime_data.profile.async_refresh()
    await async_wait_recording_done(hass)
    last = await recorder_mock.async_add_executor_job(
        get_last_statistics, hass, 100, "github_pulse:octocat_commits", True, {"state"}
    )
    assert len(last["github_pulse:octocat_commits"]) == 13


async def test_nothing_is_imported_by_default(
    recorder_mock: Recorder,
    hass: HomeAssistant,
    patch_session: Callable[[FakeSession], None],
) -> None:
    await _setup(hass, patch_session, enabled=False)

    ids = await recorder_mock.async_add_executor_job(
        list_statistic_ids, hass, None, None
    )
    assert not [i for i in ids if i["statistic_id"].startswith("github_pulse:")]


async def test_a_missing_recorder_is_skipped_with_a_warning(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    hass.config.components.remove("recorder")

    import_series(
        hass,
        build_series(
            "o", HISTORY, {}, zone=ZONE, include_restricted=True, by_commits=True
        ),
    )

    assert "recorder is not loaded" in caplog.text
