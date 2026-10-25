#!/usr/bin/env python3
"""Generate docs/permission-matrix.md by probing the GitHub API.

For every endpoint or query the integration relies on, the script records:

* the live result with the supplied token (HTTP status, accepted classic scopes),
* the live result without a token,
* the fine-grained PAT permission category, looked up in GitHub's published
  machine-readable permission data (``github/docs``).

Usage::

    GITHUB_TOKEN=... python3 scripts/generate_permission_matrix.py \
        --owner OWNER --repo REPO [--output docs/permission-matrix.md]

The token is read from the environment and never written to the output.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

API = "https://api.github.com"
FINE_GRAINED_DATA_URL = (
    "https://raw.githubusercontent.com/github/docs/main/"
    "src/github-apps/data/fpt-2022-11-28/fine-grained-pat.json"
)
USER_AGENT = "ha-github-pulse-permission-probe"
TIMEOUT = 30

GRAPHQL_CONTRIBUTIONS = (
    "query($login:String!){user(login:$login){contributionsCollection{"
    "totalCommitContributions restrictedContributionsCount}}}"
)


@dataclass(frozen=True, slots=True)
class Probe:
    """One data point the integration needs."""

    module: str
    name: str
    method: str
    template: str
    path: str
    graphql: str | None = None


@dataclass(frozen=True, slots=True)
class Result:
    """Outcome of a single request."""

    status: int
    accepted_scopes: str


def build_probes(owner: str, repo: str) -> list[Probe]:
    """Return every probe, with concrete paths for the sample repository."""
    r = f"/repos/{owner}/{repo}"
    rt = "/repos/{owner}/{repo}"
    return [
        Probe(
            "profile",
            "Contributions (GraphQL)",
            "POST",
            "/graphql",
            "/graphql",
            GRAPHQL_CONTRIBUTIONS,
        ),
        Probe("profile", "User profile", "GET", "/users/{username}", f"/users/{owner}"),
        Probe(
            "profile",
            "User events",
            "GET",
            "/users/{username}/events",
            f"/users/{owner}/events?per_page=1",
        ),
        Probe(
            "profile",
            "Search issues/PRs",
            "GET",
            "/search/issues",
            "/search/issues?q=is:pr+is:open&per_page=1",
        ),
        Probe("repository", "Repository", "GET", rt, r),
        Probe(
            "repository", "Commits", "GET", f"{rt}/commits", f"{r}/commits?per_page=1"
        ),
        Probe(
            "repository",
            "Releases",
            "GET",
            f"{rt}/releases",
            f"{r}/releases?per_page=1",
        ),
        Probe(
            "repository",
            "Traffic views",
            "GET",
            f"{rt}/traffic/views",
            f"{r}/traffic/views",
        ),
        Probe(
            "repository",
            "Dependabot alerts",
            "GET",
            f"{rt}/dependabot/alerts",
            f"{r}/dependabot/alerts?per_page=1",
        ),
        Probe(
            "actions",
            "Workflow runs",
            "GET",
            f"{rt}/actions/runs",
            f"{r}/actions/runs?per_page=1",
        ),
        Probe(
            "actions",
            "Billing usage (user)",
            "GET",
            "/users/{username}/settings/billing/usage",
            f"/users/{owner}/settings/billing/usage",
        ),
        Probe(
            "packages",
            "List packages (user)",
            "GET",
            "/user/packages",
            "/user/packages?package_type=container",
        ),
        Probe(
            "misc",
            "Notifications",
            "GET",
            "/notifications",
            "/notifications?per_page=1",
        ),
    ]


def request(probe: Probe, token: str | None) -> Result:
    """Perform the probe request and return status and accepted classic scopes."""
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": USER_AGENT,
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = None
    if probe.graphql:
        data = json.dumps(
            {"query": probe.graphql, "variables": {"login": probe.path.split("/")[-1]}}
        ).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(
        f"{API}{probe.path}", data=data, headers=headers, method=probe.method
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as response:
            status = response.status
            scopes = response.headers.get("X-Accepted-OAuth-Scopes", "")
    except urllib.error.HTTPError as err:
        status = err.code
        scopes = err.headers.get("X-Accepted-OAuth-Scopes", "")
    return Result(status, scopes.strip())


def load_fine_grained_index() -> dict[tuple[str, str], str]:
    """Map (verb, request path template) to the fine-grained permission category."""
    req = urllib.request.Request(
        FINE_GRAINED_DATA_URL, headers={"User-Agent": USER_AGENT}
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT) as response:
        data = json.load(response)
    return {
        (entry["verb"].upper(), entry["requestPath"]): category
        for category, entries in data.items()
        for entry in entries
    }


def fine_grained_permission(index: dict[tuple[str, str], str], probe: Probe) -> str:
    """Return the fine-grained permission category for a probe."""
    if probe.graphql:
        return "not documented (GraphQL)"
    return index.get((probe.method, probe.template), "not supported")


def render(rows: list[tuple[Probe, Result, Result, str]], owner: str, repo: str) -> str:
    """Render the markdown document."""
    lines = [
        "# Permission matrix",
        "",
        "Generated by `scripts/generate_permission_matrix.py`. Do not edit by hand.",
        "",
        f"Generated: {datetime.now(UTC):%Y-%m-%d} (sample repository `{owner}/{repo}`).",
        "",
        "| Module | Data point | Classic: result | Classic: accepted scopes "
        "| No token | Fine-grained permission category |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for probe, with_token, anonymous, fine_grained in rows:
        scopes = with_token.accepted_scopes or "-"
        lines.append(
            f"| {probe.module} | {probe.name} | {with_token.status} | `{scopes}` "
            f"| {anonymous.status} | {fine_grained} |"
        )
    lines += [
        "",
        "Notes:",
        "",
        "- *Classic: result* is the HTTP status for the token used to generate this file; "
        "403/404 can also mean the token's account lacks access to the sample repository.",
        "- *Accepted scopes* is the `X-Accepted-OAuth-Scopes` header; an empty value means "
        "GitHub reports no scope requirement for the endpoint.",
        "- *Fine-grained permission category* comes from GitHub's published permission "
        "data; `not supported` means the endpoint is absent from it, so a fine-grained "
        "PAT cannot call it.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    """Run all probes and write the matrix."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--owner", required=True)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--output", default="docs/permission-matrix.md")
    args = parser.parse_args()

    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        print("GITHUB_TOKEN is required", file=sys.stderr)
        return 2

    index = load_fine_grained_index()
    rows = [
        (
            probe,
            request(probe, token),
            request(probe, None),
            fine_grained_permission(index, probe),
        )
        for probe in build_probes(args.owner, args.repo)
    ]
    Path(args.output).write_text(render(rows, args.owner, args.repo), encoding="utf-8")
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
