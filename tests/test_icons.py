"""Every entity the integration describes carries an icon."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

PACKAGE = Path(__file__).parents[1] / "custom_components/github_pulse"
STATE_ICON_KEYS = {
    ("sensor", "ci_state"),
    ("sensor", "actions_last_result"),
    ("binary_sensor", "actions_running"),
}


def _load(name: str) -> dict[str, Any]:
    return json.loads((PACKAGE / name).read_text())["entity"]


@pytest.fixture(scope="module")
def icons() -> dict[str, Any]:
    return _load("icons.json")


@pytest.fixture(scope="module")
def entities() -> dict[str, Any]:
    return _load("translations/en.json")


def _icon_strings(definition: dict[str, Any]) -> list[str]:
    return [definition["default"], *definition.get("state", {}).values()]


def test_every_translated_entity_has_an_icon(
    icons: dict[str, Any], entities: dict[str, Any]
) -> None:
    for platform, keys in entities.items():
        assert set(keys) <= set(icons.get(platform, {})), platform


def test_icons_describe_no_unknown_entity(
    icons: dict[str, Any], entities: dict[str, Any]
) -> None:
    for platform, keys in icons.items():
        assert set(keys) <= set(entities.get(platform, {})), platform


def test_every_icon_is_a_material_design_icon(icons: dict[str, Any]) -> None:
    for keys in icons.values():
        for definition in keys.values():
            assert all(icon.startswith("mdi:") for icon in _icon_strings(definition))


def test_no_entity_falls_back_to_the_default_eye(icons: dict[str, Any]) -> None:
    eyes = {
        key
        for keys in icons.values()
        for key, definition in keys.items()
        if "mdi:eye" in _icon_strings(definition)
    }
    assert eyes == set()


def test_state_icons_cover_every_option(
    icons: dict[str, Any], entities: dict[str, Any]
) -> None:
    for platform, key in STATE_ICON_KEYS:
        states = icons[platform][key]["state"]
        if platform == "binary_sensor":
            assert set(states) == {"on", "off"}
        else:
            assert set(states) == set(entities[platform][key]["state"])
