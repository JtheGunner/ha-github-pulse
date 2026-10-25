"""Tests for the GitHub REST and GraphQL client."""

from __future__ import annotations

from typing import Any

import pytest
from custom_components.github_pulse.api import (
    GitHubAuthError,
    GitHubClient,
    GitHubError,
    GitHubForbiddenError,
    GitHubGraphQLError,
    GitHubNotFoundError,
    GitHubRateLimitError,
    GitHubTransportError,
    RateBudget,
)

from tests.fake_http import FakeResponse, FakeSession, transport_failure

RATE_HEADERS = {
    "X-RateLimit-Limit": "5000",
    "X-RateLimit-Remaining": "4999",
    "X-RateLimit-Reset": "99999999999",
    "X-RateLimit-Resource": "core",
}


class Sleeper:
    """Record requested sleeps instead of waiting."""

    def __init__(self) -> None:
        self.delays: list[float] = []

    async def __call__(self, delay: float) -> None:
        self.delays.append(delay)


def _client(
    *responses: FakeResponse, **kwargs: Any
) -> tuple[GitHubClient, FakeSession]:
    session = FakeSession(*responses)
    sleeper = kwargs.pop("sleep", Sleeper())
    return GitHubClient(session, "secret-token", sleep=sleeper, **kwargs), session  # type: ignore[arg-type]


async def test_rest_get_returns_data_and_updates_budget() -> None:
    budget = RateBudget()
    client, session = _client(
        FakeResponse(200, {"name": "repo"}, RATE_HEADERS), budget=budget
    )

    response = await client.rest_get("/repos/o/r", {"per_page": "1"})

    assert response.data == {"name": "repo"}
    assert not response.from_cache
    assert budget.get("core").remaining == 4999  # type: ignore[union-attr]
    request = session.requests[0]
    assert request.url == "https://api.github.com/repos/o/r"
    assert request.params == {"per_page": "1"}
    assert request.headers["Authorization"] == "Bearer secret-token"
    assert request.headers["X-GitHub-Api-Version"] == "2022-11-28"


async def test_etag_is_sent_and_304_returns_cached_body() -> None:
    client, session = _client(
        FakeResponse(200, {"stars": 3}, {"ETag": 'W/"abc"'}),
        FakeResponse(304, None, {"ETag": 'W/"abc"'}),
    )

    first = await client.rest_get("/repos/o/r")
    second = await client.rest_get("/repos/o/r")

    assert first.data == second.data == {"stars": 3}
    assert second.from_cache
    assert "If-None-Match" not in session.requests[0].headers
    assert session.requests[1].headers["If-None-Match"] == 'W/"abc"'


async def test_etag_cache_is_keyed_by_query_parameters() -> None:
    client, session = _client(
        FakeResponse(200, [1], {"ETag": "a"}),
        FakeResponse(200, [2], {"ETag": "b"}),
    )

    await client.rest_get("/x", {"page": "1"})
    await client.rest_get("/x", {"page": "2"})

    assert "If-None-Match" not in session.requests[1].headers


@pytest.mark.parametrize(
    ("response", "expected"),
    [
        (FakeResponse(401, {"message": "Bad credentials"}), GitHubAuthError),
        (FakeResponse(404, {"message": "Not Found"}), GitHubNotFoundError),
        (
            FakeResponse(403, {"message": "Resource not accessible"}),
            GitHubForbiddenError,
        ),
        (
            FakeResponse(
                403,
                {"message": "API rate limit exceeded"},
                {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "1234"},
            ),
            GitHubRateLimitError,
        ),
        (FakeResponse(422, {"message": "Validation Failed"}), GitHubError),
        (FakeResponse(500), GitHubError),
    ],
)
async def test_http_errors_are_typed(
    response: FakeResponse, expected: type[GitHubError]
) -> None:
    client, _ = _client(response)

    with pytest.raises(expected) as caught:
        await client.rest_get("/x")

    assert caught.value.status == response.status


async def test_rate_limit_error_carries_reset_time() -> None:
    client, _ = _client(
        FakeResponse(
            403,
            {"message": "API rate limit exceeded"},
            {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "1234"},
        )
    )

    with pytest.raises(GitHubRateLimitError) as caught:
        await client.rest_get("/x")

    assert caught.value.reset_at == 1234.0


async def test_server_errors_are_retried_with_backoff() -> None:
    sleeper = Sleeper()
    client, session = _client(
        FakeResponse(502),
        FakeResponse(503),
        FakeResponse(200, {"ok": True}),
        sleep=sleeper,
    )

    response = await client.rest_get("/x")

    assert response.data == {"ok": True}
    assert len(session.requests) == 3
    assert sleeper.delays == [0.5, 1.0]


async def test_retries_are_bounded() -> None:
    client, session = _client(*[FakeResponse(502, {"message": "bad gateway"})] * 4)

    with pytest.raises(GitHubError) as caught:
        await client.rest_get("/x")

    assert caught.value.status == 502
    assert len(session.requests) == 4


async def test_transport_errors_are_retried_then_raised() -> None:
    client, session = _client(*[transport_failure()] * 4)

    with pytest.raises(GitHubTransportError):
        await client.rest_get("/x")

    assert len(session.requests) == 4


async def test_transport_error_recovers_on_retry() -> None:
    client, _ = _client(transport_failure(), FakeResponse(200, {"ok": 1}))

    assert (await client.rest_get("/x")).data == {"ok": 1}


async def test_secondary_limit_waits_for_retry_after() -> None:
    sleeper = Sleeper()
    client, _ = _client(
        FakeResponse(403, {"message": "secondary rate limit"}, {"Retry-After": "7"}),
        FakeResponse(200, {"ok": True}),
        sleep=sleeper,
    )

    assert (await client.rest_get("/x")).data == {"ok": True}
    assert sleeper.delays == [7.0]


async def test_retry_after_beyond_the_cap_raises_rate_limit_error() -> None:
    sleeper = Sleeper()
    client, session = _client(
        FakeResponse(403, {"message": "secondary rate limit"}, {"Retry-After": "3600"}),
        sleep=sleeper,
    )

    with pytest.raises(GitHubRateLimitError):
        await client.rest_get("/x")

    assert sleeper.delays == []
    assert len(session.requests) == 1


async def test_pagination_follows_next_links() -> None:
    client, session = _client(
        FakeResponse(
            200,
            [1, 2],
            {
                "Link": '<https://api.github.com/x?page=2>; rel="next", '
                '<https://api.github.com/x?page=3>; rel="last"'
            },
        ),
        FakeResponse(
            200, [3, 4], {"Link": '<https://api.github.com/x?page=3>; rel="next"'}
        ),
        FakeResponse(200, [5]),
    )

    items = await client.rest_get_pages("/x", {"per_page": "2"})

    assert items == [1, 2, 3, 4, 5]
    assert session.requests[1].url == "https://api.github.com/x?page=2"


async def test_pagination_respects_max_pages() -> None:
    link = {"Link": '<https://api.github.com/x?page=2>; rel="next"'}
    client, session = _client(
        FakeResponse(200, [1], link), FakeResponse(200, [2], link)
    )

    assert await client.rest_get_pages("/x", max_pages=2) == [1, 2]
    assert len(session.requests) == 2


async def test_last_page_is_parsed_from_link_header() -> None:
    client, _ = _client(
        FakeResponse(
            200,
            [1],
            {
                "Link": '<https://api.github.com/x?per_page=1&page=2>; rel="next", '
                '<https://api.github.com/x?per_page=1&page=148>; rel="last"'
            },
        )
    )

    response = await client.rest_get("/x")

    assert response.last_page == 148


async def test_response_without_link_header_has_no_pages() -> None:
    client, _ = _client(FakeResponse(200, [1]))

    response = await client.rest_get("/x")

    assert response.last_page is None
    assert response.next_url is None


async def test_graphql_returns_data() -> None:
    client, session = _client(FakeResponse(200, {"data": {"viewer": {"login": "me"}}}))

    result = await client.graphql("query($a:Int){x}", {"a": 1})

    assert result.data == {"viewer": {"login": "me"}}
    assert result.errors == []
    request = session.requests[0]
    assert request.method == "POST"
    assert request.url == "https://api.github.com/graphql"
    assert request.json == {"query": "query($a:Int){x}", "variables": {"a": 1}}


async def test_graphql_partial_data_keeps_errors() -> None:
    client, _ = _client(
        FakeResponse(
            200,
            {"data": {"a": 1}, "errors": [{"type": "FORBIDDEN", "message": "no"}]},
        )
    )

    result = await client.graphql("query{a}")

    assert result.data == {"a": 1}
    assert result.errors[0]["type"] == "FORBIDDEN"


@pytest.mark.parametrize(
    ("error_type", "expected"),
    [
        ("RATE_LIMITED", GitHubRateLimitError),
        ("NOT_FOUND", GitHubNotFoundError),
        ("INSUFFICIENT_SCOPES", GitHubForbiddenError),
        ("VALIDATION", GitHubGraphQLError),
    ],
)
async def test_graphql_errors_without_data_are_typed(
    error_type: str, expected: type[GitHubError]
) -> None:
    client, _ = _client(
        FakeResponse(200, {"errors": [{"type": error_type, "message": "boom"}]})
    )

    with pytest.raises(expected, match="boom"):
        await client.graphql("query{a}")


async def test_graphql_without_data_or_errors_raises() -> None:
    client, _ = _client(FakeResponse(200, {}))

    with pytest.raises(GitHubError, match="no data"):
        await client.graphql("query{a}")


async def test_token_never_appears_in_error_messages() -> None:
    client, _ = _client(FakeResponse(401, {"message": "Bad credentials"}))

    with pytest.raises(GitHubAuthError) as caught:
        await client.rest_get("/x")

    assert "secret-token" not in str(caught.value)
