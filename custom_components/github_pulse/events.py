"""Fire Home Assistant events for new activity, without ever repeating one."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.storage import Store

from .actions_coordinator import GROUP_RUNS
from .analytics.events import (
    DetectedEvent,
    WorkflowState,
    merged_events,
    release_events,
    review_request_events,
    workflow_events,
)
from .const import DOMAIN, LOGGER
from .profile_coordinator import GROUP_SEARCH
from .repository_coordinator import GROUP_OVERVIEW

STORAGE_VERSION = 1

type EventListener = Callable[[DetectedEvent], None]


class EventDispatcher:
    """Compare coordinator data with the persisted state and announce changes.

    Each announced event goes onto the Home Assistant bus as
    ``github_pulse_<type>`` and to the listening event entities. The state is
    saved after every change, so a restart never repeats an announcement.
    """

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        """Create the dispatcher for one config entry."""
        self._hass = hass
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.events.{entry_id}"
        )
        self._state: dict[str, Any] = {}
        self._saved = ""
        self._listeners: list[EventListener] = []

    async def async_load(self) -> None:
        """Load the persisted state; an unreadable file starts a fresh one."""
        try:
            loaded = await self._store.async_load()
        except KeyError, TypeError, ValueError:
            LOGGER.warning("Discarding unreadable event state")
            loaded = None
        self._state = loaded if isinstance(loaded, dict) else {}
        self._saved = json.dumps(self._state, sort_keys=True)

    @callback
    def async_add_listener(self, listener: EventListener) -> CALLBACK_TYPE:
        """Register an entity callback; return the function that removes it."""
        self._listeners.append(listener)
        return lambda: self._listeners.remove(listener)

    @callback
    def _announce(self, events: list[DetectedEvent]) -> None:
        for event in events:
            self._hass.bus.async_fire(f"{DOMAIN}_{event.type}", dict(event.data))
            for listener in list(self._listeners):
                listener(event)

    def _save(self) -> None:
        """Persist the state when it changed, so a restart cannot repeat events."""
        snapshot = json.dumps(self._state, sort_keys=True)
        if snapshot == self._saved:
            return
        self._saved = snapshot
        self._hass.async_create_task(
            self._store.async_save(json.loads(snapshot)), name="github_pulse_events"
        )

    @callback
    def handle_runs(self, data: dict[str, Any]) -> None:
        """Process workflow runs: failures and recoveries."""
        repositories = (data or {}).get(GROUP_RUNS, {})
        states: dict[str, Any] = self._state.setdefault("workflows", {})
        found: list[DetectedEvent] = []
        for full_name, runs in repositories.items():
            if runs is None:
                continue
            raw = states.get(full_name)
            previous = None if raw is None else WorkflowState(**raw)
            events, new = workflow_events(full_name, runs, previous)
            found += events
            states[full_name] = {
                "last_run_id": new.last_run_id,
                "last_outcome": new.last_outcome,
            }
        self._save()
        self._announce(found)

    @callback
    def handle_repositories(self, data: dict[str, Any]) -> None:
        """Process the latest release of every tracked repository."""
        snapshots = (data or {}).get(GROUP_OVERVIEW, {})
        tags: dict[str, str] = self._state.setdefault("releases", {})
        found: list[DetectedEvent] = []
        for full_name, snapshot in snapshots.items():
            if snapshot is None:
                continue
            release = snapshot.latest_release
            events, tag = release_events(
                full_name,
                None if release is None else release.tag,
                {}
                if release is None
                else {
                    "name": release.name,
                    "url": release.url,
                    "prerelease": release.prerelease,
                },
                tags.get(full_name),
                initialised=full_name in tags,
            )
            found += events
            if tag is not None:
                tags[full_name] = tag
        self._save()
        self._announce(found)

    @callback
    def handle_search(self, data: dict[str, Any]) -> None:
        """Process pull requests awaiting review and own merged ones."""
        counts = (data or {}).get(GROUP_SEARCH)
        if counts is None:
            return
        review_events, review_ids = review_request_events(
            counts.review_pulls, self._state.get("review_ids")
        )
        merge_events, merged_ids = merged_events(
            counts.merged_pulls, self._state.get("merged_ids")
        )
        self._state["review_ids"] = review_ids
        self._state["merged_ids"] = merged_ids
        self._save()
        self._announce(review_events + merge_events)
