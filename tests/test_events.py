"""Tests for the event dispatcher and the event entities."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from custom_components.github_pulse.actions_coordinator import GROUP_RUNS
from custom_components.github_pulse.analytics.actions import WorkflowRun
from custom_components.github_pulse.events import EventDispatcher
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import async_capture_events

from tests.fake_http import FakeSession
from tests.test_actions import _setup as _setup_actions

T = datetime(2026, 10, 25, tzinfo=UTC)


def _run(run_id: int, conclusion: str) -> WorkflowRun:
    return WorkflowRun(run_id, "CI", "main", "completed", conclusion, T, T, T)


def _data(*runs: WorkflowRun) -> dict[str, object]:
    return {GROUP_RUNS: {"o/r": list(runs)}}


async def test_a_failing_run_fires_one_bus_event(hass: HomeAssistant) -> None:
    events = async_capture_events(hass, "github_pulse_workflow_failed")
    dispatcher = EventDispatcher(hass, "entry")
    await dispatcher.async_load()
    dispatcher.handle_runs(_data(_run(1, "success")))

    dispatcher.handle_runs(_data(_run(2, "failure"), _run(1, "success")))
    dispatcher.handle_runs(_data(_run(2, "failure"), _run(1, "success")))
    await hass.async_block_till_done()

    assert len(events) == 1
    assert events[0].data["repository"] == "o/r"
    assert events[0].data["run_id"] == 2


async def test_a_restart_does_not_refire_old_events(hass: HomeAssistant) -> None:
    first = EventDispatcher(hass, "entry")
    await first.async_load()
    first.handle_runs(_data(_run(1, "success")))
    first.handle_runs(_data(_run(2, "failure"), _run(1, "success")))
    await hass.async_block_till_done()

    events = async_capture_events(hass, "github_pulse_workflow_failed")
    second = EventDispatcher(hass, "entry")
    await second.async_load()
    second.handle_runs(_data(_run(2, "failure"), _run(1, "success")))
    await hass.async_block_till_done()

    assert events == []


async def test_a_failure_during_downtime_fires_after_the_restart(
    hass: HomeAssistant,
) -> None:
    first = EventDispatcher(hass, "entry")
    await first.async_load()
    first.handle_runs(_data(_run(1, "success")))
    await hass.async_block_till_done()

    events = async_capture_events(hass, "github_pulse_workflow_failed")
    second = EventDispatcher(hass, "entry")
    await second.async_load()
    second.handle_runs(_data(_run(2, "failure"), _run(1, "success")))

    assert len(events) == 1


async def test_listeners_receive_events_until_removed(hass: HomeAssistant) -> None:
    dispatcher = EventDispatcher(hass, "entry")
    await dispatcher.async_load()
    seen: list[str] = []
    remove = dispatcher.async_add_listener(lambda event: seen.append(event.type))
    dispatcher.handle_runs(_data(_run(1, "success")))

    dispatcher.handle_runs(_data(_run(2, "failure"), _run(1, "success")))
    remove()
    dispatcher.handle_runs(_data(_run(3, "failure"), _run(2, "failure")))

    assert seen == ["workflow_failed"]


async def test_an_unreadable_runs_entry_is_skipped(hass: HomeAssistant) -> None:
    dispatcher = EventDispatcher(hass, "entry")
    await dispatcher.async_load()

    dispatcher.handle_runs({GROUP_RUNS: {"o/hidden": None}})
    dispatcher.handle_runs({})
    dispatcher.handle_search({})


async def test_event_entities_trigger_for_their_repository(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None]
) -> None:
    entry = await _setup_actions(hass, patch_session)
    registry = er.async_get(hass)
    entity = next(
        e
        for e in registry.entities.values()
        if e.unique_id.endswith("o/with-actions_events")
    )
    other = next(
        e
        for e in registry.entities.values()
        if e.unique_id.endswith("o/without_events")
    )
    dispatcher = entry.runtime_data.events

    dispatcher.handle_runs({GROUP_RUNS: {"o/with-actions": [_run(99999, "failure")]}})
    await hass.async_block_till_done()

    state = hass.states.get(entity.entity_id)
    assert state.attributes["event_type"] == "workflow_failed"
    assert state.attributes["run_id"] == 99999
    assert hass.states.get(other.entity_id).attributes["event_type"] is None


async def test_a_repository_without_actions_only_offers_release_events(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None]
) -> None:
    await _setup_actions(hass, patch_session)
    registry = er.async_get(hass)
    entity = next(
        e
        for e in registry.entities.values()
        if e.unique_id.endswith("o/without_events")
    )

    state = hass.states.get(entity.entity_id)

    assert state.attributes["event_types"] == ["release_published"]
