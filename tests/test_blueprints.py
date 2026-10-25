"""The shipped blueprints must load and react to the integration's events."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.setup import async_setup_component
from homeassistant.util.yaml import load_yaml

SOURCE = Path(__file__).parents[1] / "blueprints" / "automation" / "github_pulse"
EVENTS = {
    "ci_failed.yaml": "github_pulse_workflow_failed",
    "review_requested.yaml": "github_pulse_review_requested",
}


@pytest.mark.parametrize("name", sorted(EVENTS))
def test_blueprint_listens_to_the_integration_event(name: str) -> None:
    raw = load_yaml(str(SOURCE / name))

    assert raw["blueprint"]["domain"] == "automation"
    assert "notify_actions" in raw["blueprint"]["input"]
    assert raw["triggers"][0]["event_type"] == EVENTS[name]


def _copy(source: Path, target: str) -> None:
    Path(target).mkdir(parents=True, exist_ok=True)
    shutil.copy(source, target)


async def _install(hass: HomeAssistant, name: str, inputs: dict) -> list[ServiceCall]:
    target = hass.config.path("blueprints/automation/github_pulse")
    await hass.async_add_executor_job(_copy, SOURCE / name, target)
    calls: list[ServiceCall] = []
    hass.services.async_register("test", "record", calls.append)
    assert await async_setup_component(
        hass,
        "automation",
        {
            "automation": {
                "use_blueprint": {
                    "path": f"github_pulse/{name}",
                    "input": {
                        **inputs,
                        "notify_actions": [
                            {
                                "action": "test.record",
                                "data": {"repo": "{{ repository }}"},
                            }
                        ],
                    },
                }
            }
        },
    )
    return calls


def _fire(hass: HomeAssistant, event_type: str, repository: str, **extra: str) -> None:
    hass.bus.async_fire(event_type, {"repository": repository, **extra})


async def test_ci_failed_runs_the_actions_with_the_event_data(
    hass: HomeAssistant,
) -> None:
    calls = await _install(hass, "ci_failed.yaml", {"repository": "octocat/hello"})

    _fire(hass, EVENTS["ci_failed.yaml"], "Octocat/Hello", branch="main")
    await hass.async_block_till_done()

    assert [c.data["repo"] for c in calls] == ["Octocat/Hello"]


async def test_ci_failed_ignores_other_repositories_and_branches(
    hass: HomeAssistant,
) -> None:
    calls = await _install(
        hass, "ci_failed.yaml", {"repository": "octocat/hello", "branch": "main"}
    )

    _fire(hass, EVENTS["ci_failed.yaml"], "octocat/other", branch="main")
    _fire(hass, EVENTS["ci_failed.yaml"], "octocat/hello", branch="dev")
    await hass.async_block_till_done()

    assert calls == []


async def test_review_requested_without_filter_matches_everything(
    hass: HomeAssistant,
) -> None:
    calls = await _install(hass, "review_requested.yaml", {})

    _fire(hass, EVENTS["review_requested.yaml"], "octocat/hello", number="7")
    await hass.async_block_till_done()

    assert len(calls) == 1
