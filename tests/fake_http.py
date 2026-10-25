"""A scripted stand-in for ``aiohttp.ClientSession`` used by the API tests."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from aiohttp import ClientError


@dataclass
class FakeResponse:
    """One scripted response."""

    status: int = 200
    body: Any = None
    headers: dict[str, str] = field(default_factory=dict)
    error: Exception | None = None

    async def read(self) -> bytes:
        if self.body is None:
            return b""
        return json.dumps(self.body).encode()

    async def __aenter__(self) -> FakeResponse:
        if self.error:
            raise self.error
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        return None


@dataclass
class RecordedRequest:
    method: str
    url: str
    headers: dict[str, str]
    params: dict[str, str] | None
    json: Any


class FakeSession:
    """Return scripted responses in order and record every request."""

    def __init__(self, *responses: FakeResponse) -> None:
        self._responses = list(responses)
        self.requests: list[RecordedRequest] = []

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str],
        params: dict[str, str] | None = None,
        json: Any = None,
    ) -> FakeResponse:
        self.requests.append(RecordedRequest(method, url, dict(headers), params, json))
        if not self._responses and isinstance(json, dict) and "query" in json:
            return _contribution_response(json["query"])
        return self._responses.pop(0)


def transport_failure() -> FakeResponse:
    """Return a scripted response that fails like a dropped connection."""
    return FakeResponse(error=ClientError("connection reset"))


CONTRIBUTION_TOTALS = {
    "totalCommitContributions": 10,
    "totalPullRequestContributions": 2,
    "totalIssueContributions": 1,
    "totalPullRequestReviewContributions": 3,
    "restrictedContributionsCount": 4,
}


def _contribution_response(query: str) -> FakeResponse:
    """Answer a contribution query once the script is exhausted."""
    if "commitContributionsByRepository" in query:
        aliases = re.findall(r"(\w+): contributionsCollection", query)
        user = {a: {"commitContributionsByRepository": []} for a in aliases}
        return FakeResponse(body={"data": {"user": user}})
    if "contributionCalendar" in query:
        calendar = {"contributionCalendar": {"weeks": []}}
        return FakeResponse(
            body={"data": {"user": {"contributionsCollection": calendar}}}
        )
    aliases = re.findall(r"(\w+): contributionsCollection", query)
    user = dict.fromkeys(aliases, CONTRIBUTION_TOTALS)
    return FakeResponse(body={"data": {"user": user}})
