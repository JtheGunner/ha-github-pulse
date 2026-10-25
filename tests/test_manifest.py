"""Consistency checks between the manifest, HACS metadata and constants."""

import json
from pathlib import Path

from custom_components.github_pulse.const import DOMAIN

ROOT = Path(__file__).parent.parent
COMPONENT = ROOT / "custom_components" / DOMAIN


def test_manifest_domain_matches_constant() -> None:
    manifest = json.loads((COMPONENT / "manifest.json").read_text(encoding="utf-8"))

    assert manifest["domain"] == DOMAIN
    assert COMPONENT.name == DOMAIN


def test_hacs_minimum_version_is_declared() -> None:
    hacs = json.loads((ROOT / "hacs.json").read_text(encoding="utf-8"))

    assert hacs["homeassistant"] == "2026.9.0"
