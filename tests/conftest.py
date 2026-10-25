"""Shared fixtures."""

from collections.abc import Generator
from typing import Any
from unittest.mock import patch

import pytest

from tests.fake_http import FakeSession


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Let Home Assistant load the integration from ``custom_components``."""


@pytest.fixture
def patch_session() -> Generator[Any]:
    """Return a function that makes every client use a scripted session."""
    patchers: list[Any] = []

    def _patch(session: FakeSession) -> None:
        for target in (
            "custom_components.github_pulse.config_flow.async_get_clientsession",
            "custom_components.github_pulse.async_get_clientsession",
        ):
            patcher = patch(target, return_value=session)
            patcher.start()
            patchers.append(patcher)

    yield _patch
    for patcher in patchers:
        patcher.stop()
