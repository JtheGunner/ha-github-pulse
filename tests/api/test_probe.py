"""Tests for token identification and module probing."""

from __future__ import annotations

import pytest
from custom_components.github_pulse.api import GitHubAuthError, GitHubClient
from custom_components.github_pulse.api.probe import (
    TokenType,
    detect_token_type,
    fetch_token_info,
    probe_module,
)

from tests.fake_http import FakeResponse, FakeSession


def _client(*responses: FakeResponse) -> GitHubClient:
    async def no_sleep(_: float) -> None:
        return None

    return GitHubClient(FakeSession(*responses), "t", sleep=no_sleep)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("token", "scopes", "expected"),
    [
        ("github_pat_abc", None, TokenType.FINE_GRAINED),
        ("ghp_abc", "repo, read:org", TokenType.CLASSIC),
        ("ghp_abc", "", TokenType.CLASSIC),
        ("something", None, TokenType.UNKNOWN),
    ],
)
def test_detect_token_type(token: str, scopes: str | None, expected: TokenType) -> None:
    assert detect_token_type(token, scopes) == expected


async def test_fetch_token_info_reads_login_and_scopes() -> None:
    client = _client(
        FakeResponse(200, {"login": "octocat"}, {"X-OAuth-Scopes": "repo, read:org"})
    )

    info = await fetch_token_info(client, "ghp_abc")

    assert info.login == "octocat"
    assert info.token_type is TokenType.CLASSIC
    assert info.scopes == {"repo", "read:org"}


async def test_fetch_token_info_for_a_fine_grained_token_has_no_scopes() -> None:
    client = _client(FakeResponse(200, {"login": "octocat"}))

    info = await fetch_token_info(client, "github_pat_abc")

    assert info.token_type is TokenType.FINE_GRAINED
    assert info.scopes == frozenset()


async def test_fetch_token_info_propagates_a_rejected_token() -> None:
    client = _client(FakeResponse(401, {"message": "Bad credentials"}))

    with pytest.raises(GitHubAuthError):
        await fetch_token_info(client, "ghp_abc")


@pytest.mark.parametrize("module", ["profile", "repositories"])
async def test_probe_module_succeeds_when_the_query_works(module: str) -> None:
    client = _client(FakeResponse(200, {"data": {"viewer": {}}}))

    assert await probe_module(client, module, "octocat") is True


@pytest.mark.parametrize(
    "error_type", ["INSUFFICIENT_SCOPES", "FORBIDDEN", "NOT_FOUND"]
)
async def test_probe_module_reports_missing_access_as_false(error_type: str) -> None:
    client = _client(
        FakeResponse(200, {"errors": [{"type": error_type, "message": "no"}]})
    )

    assert await probe_module(client, "profile", "octocat") is False


async def test_probe_module_propagates_authentication_errors() -> None:
    client = _client(FakeResponse(401, {"message": "Bad credentials"}))

    with pytest.raises(GitHubAuthError):
        await probe_module(client, "profile", "octocat")


async def test_probe_module_rejects_unknown_modules() -> None:
    with pytest.raises(ValueError, match="unknown module"):
        await probe_module(_client(), "packages", "octocat")
