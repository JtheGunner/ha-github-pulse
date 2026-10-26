"""Descriptions of the per-repository sensors."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfTime
from homeassistant.util import dt as dt_util

from .analytics.periods import percent_change
from .repository_coordinator import GROUP_DOWNLOADS, GROUP_OVERVIEW
from .repository_fetch import RepositoryActivity, RepositorySnapshot

CI_STATES = ["success", "failure", "pending", "error", "expected"]

type Attributes = Mapping[str, Any]


@dataclass(frozen=True, kw_only=True)
class RepositoryView:
    """What a repository sensor may read."""

    snapshot: RepositorySnapshot
    total_downloads: int | None
    now: datetime


@dataclass(frozen=True, kw_only=True)
class RepositorySensorDescription(SensorEntityDescription):
    """A repository sensor with its data group and readers."""

    group: str = GROUP_OVERVIEW
    value_fn: Callable[[RepositoryView], Any]
    attributes_fn: Callable[[RepositoryView], Attributes] | None = None


def _days_since(moment: datetime | None, now: datetime) -> int | None:
    return None if moment is None else max((now - moment).days, 0)


def _release_attributes(view: RepositoryView) -> Attributes:
    release = view.snapshot.latest_release
    if release is None:
        return {}
    return {
        "name": release.name,
        "url": release.url,
        "published_at": release.published_at,
        "prerelease": release.prerelease,
    }


def _ci_state(view: RepositoryView) -> str | None:
    state = view.snapshot.ci_state
    return None if state is None else state.lower()


def _release_downloads(view: RepositoryView) -> int | None:
    release = view.snapshot.latest_release
    return None if release is None else release.downloads


def _commits_this_month(view: RepositoryView) -> int | None:
    activity = view.snapshot.activity
    return None if activity is None else activity.commits_this_month


def _active_days(view: RepositoryView) -> int | None:
    activity = view.snapshot.activity
    return None if activity is None else activity.active_days


def _active_days_attributes(view: RepositoryView) -> Attributes:
    activity = view.snapshot.activity
    return {} if activity is None else {"truncated": activity.truncated}


def _baseline(activity: RepositoryActivity, *, year: bool) -> int:
    return activity.commits_previous_year if year else activity.commits_previous_month


def _change(view: RepositoryView, *, year: bool) -> float | None:
    activity = view.snapshot.activity
    if activity is None:
        return None
    change = percent_change(activity.commits_this_month, _baseline(activity, year=year))
    return None if change is None else round(change, 1)


def _change_attributes(view: RepositoryView, *, year: bool) -> Attributes:
    activity = view.snapshot.activity
    if activity is None:
        return {}
    return {
        "commits": activity.commits_this_month,
        "commits_in_comparison_span": _baseline(activity, year=year),
        "elapsed_days": activity.elapsed_days,
    }


REPOSITORY_SENSORS: tuple[RepositorySensorDescription, ...] = (
    RepositorySensorDescription(
        key="stars",
        translation_key="stars",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda view: view.snapshot.stars,
    ),
    RepositorySensorDescription(
        key="forks",
        translation_key="forks",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda view: view.snapshot.forks,
    ),
    RepositorySensorDescription(
        key="open_issues",
        translation_key="open_issues",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda view: view.snapshot.open_issues,
    ),
    RepositorySensorDescription(
        key="open_pull_requests",
        translation_key="open_pull_requests",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda view: view.snapshot.open_pull_requests,
    ),
    RepositorySensorDescription(
        key="commits_this_month",
        translation_key="commits_this_month",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_commits_this_month,
    ),
    RepositorySensorDescription(
        key="active_days_this_month",
        translation_key="active_days_this_month",
        native_unit_of_measurement=UnitOfTime.DAYS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_active_days,
        attributes_fn=_active_days_attributes,
    ),
    RepositorySensorDescription(
        key="commits_vs_last_month",
        translation_key="commits_vs_last_month",
        native_unit_of_measurement=PERCENTAGE,
        suggested_display_precision=1,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda view: _change(view, year=False),
        attributes_fn=lambda view: _change_attributes(view, year=False),
    ),
    RepositorySensorDescription(
        key="commits_vs_last_year",
        translation_key="commits_vs_last_year",
        native_unit_of_measurement=PERCENTAGE,
        suggested_display_precision=1,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda view: _change(view, year=True),
        attributes_fn=lambda view: _change_attributes(view, year=True),
    ),
    RepositorySensorDescription(
        key="latest_release",
        translation_key="latest_release",
        value_fn=lambda view: (
            None
            if view.snapshot.latest_release is None
            else view.snapshot.latest_release.tag
        ),
        attributes_fn=_release_attributes,
    ),
    RepositorySensorDescription(
        key="ci_state",
        translation_key="ci_state",
        device_class=SensorDeviceClass.ENUM,
        options=CI_STATES,
        value_fn=_ci_state,
    ),
    RepositorySensorDescription(
        key="watchers",
        translation_key="watchers",
        entity_registry_enabled_default=False,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda view: view.snapshot.watchers,
    ),
    RepositorySensorDescription(
        key="latest_release_downloads",
        translation_key="latest_release_downloads",
        entity_registry_enabled_default=False,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_release_downloads,
    ),
    RepositorySensorDescription(
        key="total_downloads",
        translation_key="total_downloads",
        group=GROUP_DOWNLOADS,
        entity_registry_enabled_default=False,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda view: view.total_downloads,
    ),
    RepositorySensorDescription(
        key="days_since_last_commit",
        translation_key="days_since_last_commit",
        entity_registry_enabled_default=False,
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.DAYS,
        value_fn=lambda view: _days_since(view.snapshot.last_commit_at, view.now),
    ),
    RepositorySensorDescription(
        key="days_since_last_release",
        translation_key="days_since_last_release",
        entity_registry_enabled_default=False,
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.DAYS,
        value_fn=lambda view: _days_since(
            None
            if view.snapshot.latest_release is None
            else view.snapshot.latest_release.published_at,
            view.now,
        ),
    ),
    RepositorySensorDescription(
        key="last_push",
        translation_key="last_push",
        entity_registry_enabled_default=False,
        entity_category=EntityCategory.DIAGNOSTIC,
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda view: view.snapshot.pushed_at,
    ),
)


def now() -> datetime:
    """Return the current time; one place to patch."""
    return dt_util.utcnow()
