"""Consistency checks between the manifest, HACS metadata and constants."""

import json
import re
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


def test_manifest_version_matches_the_latest_changelog_release() -> None:
    manifest = json.loads((COMPONENT / "manifest.json").read_text(encoding="utf-8"))
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")

    latest = re.search(r"^## \[(\d+\.\d+\.\d+)\]", changelog, re.MULTILINE)

    assert latest is not None
    assert manifest["version"] == latest.group(1)
