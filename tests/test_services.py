"""Tests for the get_history service."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import pytest
from custom_components.github_pulse.const import (
    CONF_HISTORY_YEARS,
    CONF_MODULES,
    CONF_OWNER,
    CONF_TOKEN_TYPE,
    DOMAIN,
)
from custom_components.github_pulse.services import async_setup_services
from freezegun.api import FrozenDateTimeFactory
from homeassistant.const import CONF_ACCESS_TOKEN
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from tests.fake_http import FakeSession


@pytest.fixture(autouse=True)
def _freeze(freezer: FrozenDateTimeFactory) -> None:
    freezer.move_to(datetime(2026, 10, 25, 12, tzinfo=UTC))


async def _setup(
    hass: HomeAssistant,
    patch_session: Callable[[FakeSession], None],
    modules: list[str] | None = None,
) -> MockConfigEntry:
    patch_session(FakeSession())
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="octocat",
        data={
            CONF_ACCESS_TOKEN: "token",
            CONF_OWNER: "octocat",
            CONF_TOKEN_TYPE: "classic",
            CONF_MODULES: modules or ["profile"],
        },
        options={CONF_HISTORY_YEARS: 1},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    return entry


async def _call(hass: HomeAssistant, **data: Any) -> dict[str, Any]:
    return await hass.services.async_call(  # type: ignore[no-any-return]
        DOMAIN, "get_history", data, blocking=True, return_response=True
    )


async def test_returns_months_and_languages(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None]
) -> None:
    await _setup(hass, patch_session)

    response = await _call(hass)

    assert len(response["months"]) == 13
    assert response["months"][-1] == {
        "month": "2026-10",
        "commits": 10,
        "pull_requests": 2,
        "issues": 1,
        "reviews": 3,
        "restricted": 4,
        "contributions": 20,
    }
    assert response["languages"]["method"] == "estimated"


async def test_the_range_limits_both_series(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None]
) -> None:
    await _setup(hass, patch_session)

    response = await _call(hass, start="2026-03", end="2026-05")

    assert [m["month"] for m in response["months"]] == ["2026-03", "2026-04", "2026-05"]
    assert all(m["month"] <= "2026-05" for m in response["languages"]["months"])


async def test_languages_can_be_left_out(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None]
) -> None:
    await _setup(hass, patch_session)

    assert "languages" not in await _call(hass, include_languages=False)


@pytest.mark.parametrize("value", ["2026", "2026-13", "March", "2026-00"])
async def test_a_malformed_month_is_rejected(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None], value: str
) -> None:
    await _setup(hass, patch_session)

    with pytest.raises(ServiceValidationError):
        await _call(hass, start=value)


async def test_a_reversed_range_is_rejected(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None]
) -> None:
    await _setup(hass, patch_session)

    with pytest.raises(ServiceValidationError):
        await _call(hass, start="2026-05", end="2026-03")


async def test_a_range_without_data_returns_empty_series(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None]
) -> None:
    await _setup(hass, patch_session)

    response = await _call(hass, start="1999-01", end="1999-12")

    assert response["months"] == []
    assert response["languages"]["months"] == []


async def test_an_unknown_entry_is_rejected(
    hass: HomeAssistant, patch_session: Callable[[FakeSession], None]
) -> None:
    await _setup(hass, patch_session)

    with pytest.raises(ServiceValidationError):
        await _call(hass, config_entry_id="nope")


async def test_without_a_loaded_entry_the_service_fails(hass: HomeAssistant) -> None:
    async_setup_services(hass)

    with pytest.raises(ServiceValidationError):
        await _call(hass)
