"""Asynchronous GitHub REST and GraphQL client.

The client has no Home Assistant imports so it can be tested in isolation. It
caches REST responses by ETag (a ``304 Not Modified`` costs no rate limit),
retries transient failures with a bounded backoff and keeps a shared
:class:`RateBudget` up to date.
"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from http import HTTPStatus
from typing import Any

from aiohttp import ClientError, ClientSession

from ..const import API_BASE_URL, API_VERSION, GRAPHQL_URL, REQUEST_TIMEOUT, USER_AGENT
from .errors import (
    GitHubAuthError,
    GitHubError,
    GitHubForbiddenError,
    GitHubGraphQLError,
    GitHubNotFoundError,
    GitHubRateLimitError,
    GitHubTransportError,
)
from .rate_budget import RateBudget

MAX_RETRIES = 3
MAX_RETRY_AFTER = 60.0
MAX_BACKOFF = 8.0
RETRY_STATUSES = frozenset(
    {HTTPStatus.BAD_GATEWAY, HTTPStatus.SERVICE_UNAVAILABLE, HTTPStatus.GATEWAY_TIMEOUT}
)

_LINK_LAST_PAGE = re.compile(r'[?&]page=(\d+)[^>]*>;\s*rel="last"')
_LINK_NEXT = re.compile(r'<([^>]+)>;\s*rel="next"')

type Sleep = Callable[[float], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class RestResponse:
    """Parsed REST response."""

    data: Any
    headers: Mapping[str, str]
    from_cache: bool = False

    @property
    def next_url(self) -> str | None:
        """Return the URL of the next page, if the response is paginated."""
        match = _LINK_NEXT.search(self.headers.get("Link", ""))
        return match.group(1) if match else None

    @property
    def last_page(self) -> int | None:
        """Return the number of the last page, if the response is paginated."""
        match = _LINK_LAST_PAGE.search(self.headers.get("Link", ""))
        return int(match.group(1)) if match else None


@dataclass(frozen=True, slots=True)
class GraphQLResult:
    """GraphQL data plus any non-fatal errors that came with it."""

    data: dict[str, Any]
    errors: list[dict[str, Any]]


@dataclass(frozen=True, slots=True)
class _RawResponse:
    status: int
    headers: Mapping[str, str]
    body: Any


class GitHubClient:
    """Thin asynchronous wrapper around the GitHub REST and GraphQL APIs."""

    def __init__(
        self,
        session: ClientSession,
        token: str,
        *,
        budget: RateBudget | None = None,
        sleep: Sleep = asyncio.sleep,
        max_retries: int = MAX_RETRIES,
    ) -> None:
        """Create a client around a shared session and an access token."""
        self._session = session
        self._headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": API_VERSION,
            "User-Agent": USER_AGENT,
        }
        self.budget = budget or RateBudget()
        self._sleep = sleep
        self._max_retries = max_retries
        self._etag_cache: dict[str, tuple[str, Any, Mapping[str, str]]] = {}

    async def rest_get(
        self, path: str, params: Mapping[str, str] | None = None
    ) -> RestResponse:
        """GET a REST path (or absolute URL) and return the parsed response."""
        url = path if path.startswith("http") else f"{API_BASE_URL}{path}"
        cache_key = _cache_key(url, params)
        headers = dict(self._headers)
        cached = self._etag_cache.get(cache_key)
        if cached:
            headers["If-None-Match"] = cached[0]

        raw = await self._request("GET", url, headers=headers, params=params)
        if raw.status == HTTPStatus.NOT_MODIFIED and cached:
            return RestResponse(cached[1], cached[2], from_cache=True)
        if etag := raw.headers.get("ETag"):
            self._etag_cache[cache_key] = (etag, raw.body, raw.headers)
        return RestResponse(raw.body, raw.headers)

    async def rest_get_pages(
        self,
        path: str,
        params: Mapping[str, str] | None = None,
        *,
        max_pages: int = 10,
    ) -> list[Any]:
        """GET a paginated list endpoint and return the concatenated items."""
        items: list[Any] = []
        response = await self.rest_get(path, params)
        items.extend(response.data)
        pages = 1
        while (next_url := response.next_url) and pages < max_pages:
            response = await self.rest_get(next_url)
            items.extend(response.data)
            pages += 1
        return items

    async def graphql(
        self, query: str, variables: Mapping[str, Any] | None = None
    ) -> GraphQLResult:
        """Run a GraphQL query.

        Raises a typed error when the response carries no data. When data and
        errors arrive together (for example a field the token cannot see), the
        errors are returned next to the data.
        """
        headers = {**self._headers, "Content-Type": "application/json"}
        payload = {"query": query, "variables": dict(variables or {})}
        raw = await self._request(
            "POST", GRAPHQL_URL, headers=headers, json_body=payload
        )
        body = raw.body if isinstance(raw.body, dict) else {}
        errors: list[dict[str, Any]] = body.get("errors") or []
        data = body.get("data")
        if errors and not data:
            raise _graphql_error(errors)
        if not isinstance(data, dict):
            raise GitHubError("GraphQL response contained no data", status=raw.status)
        return GraphQLResult(data, errors)

    async def _request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str],
        params: Mapping[str, str] | None = None,
        json_body: Any = None,
    ) -> _RawResponse:
        """Send a request, retrying transient failures, and map errors."""
        for attempt in range(self._max_retries + 1):
            last_attempt = attempt == self._max_retries
            try:
                raw = await self._send(method, url, headers, params, json_body)
            except GitHubTransportError:
                if last_attempt:
                    raise
                await self._sleep(_backoff(attempt))
                continue

            self.budget.update_from_headers(raw.headers)
            if raw.status in RETRY_STATUSES and not last_attempt:
                await self._sleep(_backoff(attempt))
                continue
            delay = _retry_after(raw)
            if delay is not None and delay <= MAX_RETRY_AFTER and not last_attempt:
                await self._sleep(delay)
                continue
            _raise_for_status(raw)
            return raw
        raise GitHubTransportError("Retries exhausted")  # pragma: no cover

    async def _send(
        self,
        method: str,
        url: str,
        headers: Mapping[str, str],
        params: Mapping[str, str] | None,
        json_body: Any,
    ) -> _RawResponse:
        """Perform one HTTP exchange and read the body."""
        try:
            async with (
                asyncio.timeout(REQUEST_TIMEOUT),
                self._session.request(
                    method, url, headers=headers, params=params, json=json_body
                ) as response,
            ):
                content = await response.read()
                return _RawResponse(
                    response.status, response.headers, _parse_body(content)
                )
        except (ClientError, TimeoutError) as err:
            raise GitHubTransportError(
                f"Error communicating with GitHub: {err}"
            ) from err


def _cache_key(url: str, params: Mapping[str, str] | None) -> str:
    """Return a stable cache key for a URL and its query parameters."""
    if not params:
        return url
    return f"{url}?{'&'.join(f'{k}={params[k]}' for k in sorted(params))}"


def _parse_body(content: bytes) -> Any:
    """Parse a JSON body; an empty or non-JSON body becomes ``None``."""
    if not content:
        return None
    try:
        return json.loads(content)
    except ValueError:
        return None


def _backoff(attempt: int) -> float:
    """Return the exponential backoff delay for a zero-based attempt number."""
    return min(0.5 * (2.0**attempt), MAX_BACKOFF)


def _retry_after(raw: _RawResponse) -> float | None:
    """Return the ``Retry-After`` delay of a secondary-limit response, if any."""
    if raw.status not in (HTTPStatus.FORBIDDEN, HTTPStatus.TOO_MANY_REQUESTS):
        return None
    try:
        return float(raw.headers.get("Retry-After", ""))
    except ValueError:
        return None


def _message(raw: _RawResponse) -> str:
    """Return the error message GitHub sent, or a generic one."""
    if isinstance(raw.body, dict) and isinstance(raw.body.get("message"), str):
        return str(raw.body["message"])
    return f"Unexpected status {raw.status} from GitHub"


def _raise_for_status(raw: _RawResponse) -> None:
    """Translate an HTTP status into a typed exception."""
    status = raw.status
    if status in (HTTPStatus.OK, HTTPStatus.NOT_MODIFIED):
        return
    message = _message(raw)
    if status == HTTPStatus.UNAUTHORIZED:
        raise GitHubAuthError(message, status=status)
    if status in (HTTPStatus.FORBIDDEN, HTTPStatus.TOO_MANY_REQUESTS):
        if raw.headers.get("X-RateLimit-Remaining") == "0" or (
            "rate limit" in message.lower()
        ):
            reset = raw.headers.get("X-RateLimit-Reset", "")
            raise GitHubRateLimitError(
                message,
                status=status,
                reset_at=float(reset) if reset.isdigit() else None,
            )
        raise GitHubForbiddenError(message, status=status)
    if status == HTTPStatus.NOT_FOUND:
        raise GitHubNotFoundError(message, status=status)
    raise GitHubError(message, status=status)


def _graphql_error(errors: list[dict[str, Any]]) -> GitHubError:
    """Map GraphQL error objects to the most specific typed exception."""
    kinds = {str(error.get("type", "")).upper() for error in errors}
    message = "; ".join(str(error.get("message", "")) for error in errors)
    if "RATE_LIMITED" in kinds:
        return GitHubRateLimitError(message)
    if "NOT_FOUND" in kinds:
        return GitHubNotFoundError(message)
    if "INSUFFICIENT_SCOPES" in kinds or "FORBIDDEN" in kinds:
        return GitHubForbiddenError(message)
    return GitHubGraphQLError(message, errors=errors)
