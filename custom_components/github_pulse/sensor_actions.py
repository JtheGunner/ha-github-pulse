"""Descriptions of the per-repository Actions entities."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntityDescription
from homeassistant.components.binary_sensor.const import BinarySensorDeviceClass
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, UnitOfTime

from .analytics.actions import ActionsSummary

LAST_RESULTS = [
    "success",
    "failure",
    "cancelled",
    "skipped",
    "timed_out",
    "neutral",
    "action_required",
    "stale",
    "startup_failure",
]


@dataclass(frozen=True, kw_only=True)
class ActionsSensorDescription(SensorEntityDescription):
    """An Actions sensor reading a repository summary."""

    value_fn: Callable[[ActionsSummary], Any]


@dataclass(frozen=True, kw_only=True)
class ActionsBinarySensorDescription(BinarySensorEntityDescription):
    """An Actions binary sensor reading a repository summary."""

    value_fn: Callable[[ActionsSummary], bool]


ACTIONS_SENSORS: tuple[ActionsSensorDescription, ...] = (
    ActionsSensorDescription(
        key="actions_last_result",
        translation_key="actions_last_result",
        device_class=SensorDeviceClass.ENUM,
        options=LAST_RESULTS,
        value_fn=lambda summary: summary.last_result,
    ),
    ActionsSensorDescription(
        key="actions_runs_today",
        translation_key="actions_runs_today",
        entity_registry_enabled_default=False,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda summary: summary.runs_today,
    ),
    ActionsSensorDescription(
        key="actions_queued_runs",
        translation_key="actions_queued_runs",
        entity_registry_enabled_default=False,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda summary: summary.queued,
    ),
    ActionsSensorDescription(
        key="actions_failure_rate_7d",
        translation_key="actions_failure_rate_7d",
        entity_registry_enabled_default=False,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda summary: summary.failure_rate_7d,
    ),
    ActionsSensorDescription(
        key="actions_failure_rate_30d",
        translation_key="actions_failure_rate_30d",
        entity_registry_enabled_default=False,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda summary: summary.failure_rate_30d,
    ),
    ActionsSensorDescription(
        key="actions_average_duration",
        translation_key="actions_average_duration",
        entity_registry_enabled_default=False,
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        suggested_unit_of_measurement=UnitOfTime.MINUTES,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda summary: summary.average_duration_seconds,
    ),
)

ACTIONS_BINARY_SENSORS: tuple[ActionsBinarySensorDescription, ...] = (
    ActionsBinarySensorDescription(
        key="actions_running",
        translation_key="actions_running",
        device_class=BinarySensorDeviceClass.RUNNING,
        value_fn=lambda summary: summary.running,
    ),
)
