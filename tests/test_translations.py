"""The German translation must mirror the English source."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

TRANSLATIONS = Path(__file__).parents[1] / "custom_components/github_pulse/translations"
PLACEHOLDER = re.compile(r"\{(\w+)\}")


def _leaves(value: Any, path: str = "") -> dict[str, str]:
    if isinstance(value, dict):
        found: dict[str, str] = {}
        for key, child in value.items():
            found |= _leaves(child, f"{path}.{key}" if path else key)
        return found
    return {path: value}


@pytest.fixture(scope="module")
def english() -> dict[str, str]:
    return _leaves(json.loads((TRANSLATIONS / "en.json").read_text()))


@pytest.fixture(scope="module")
def german() -> dict[str, str]:
    return _leaves(json.loads((TRANSLATIONS / "de.json").read_text()))


def test_german_has_exactly_the_english_keys(
    english: dict[str, str], german: dict[str, str]
) -> None:
    assert german.keys() == english.keys()


def test_german_keeps_every_placeholder(
    english: dict[str, str], german: dict[str, str]
) -> None:
    for path, text in english.items():
        assert set(PLACEHOLDER.findall(german[path])) == set(
            PLACEHOLDER.findall(text)
        ), path


def test_german_strings_are_not_left_in_english(
    english: dict[str, str], german: dict[str, str]
) -> None:
    same = {p for p, t in english.items() if german[p] == t and len(t.split()) > 3}

    assert same == set()
