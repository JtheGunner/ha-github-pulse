"""Fetch recent workflow runs of a repository."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from .analytics.actions import LONG_WINDOW, WorkflowRun
from .api import GitHubClient

MAX_PAGES = 3


def _time(value: str | None) -> datetime | None:
    return None if value is None else datetime.fromisoformat(value)


def parse_run(raw: dict[str, Any]) -> WorkflowRun:
    """Turn one run object of the REST response into a ``WorkflowRun``."""
    created = datetime.fromisoformat(raw["created_at"])
    return WorkflowRun(
        id=raw["id"],
        name=raw.get("name") or "",
        branch=raw.get("head_branch"),
        status=raw["status"],
        conclusion=raw.get("conclusion"),
        created_at=created,
        started_at=_time(raw.get("run_started_at")),
        updated_at=_time(raw.get("updated_at")) or created,
        url=raw.get("html_url"),
    )


async def fetch_runs(
    client: GitHubClient, full_name: str, now: datetime | None = None
) -> list[WorkflowRun]:
    """Fetch the runs created in the last 30 days, newest first."""
    since = (now or datetime.now(UTC)) - timedelta(days=LONG_WINDOW.days)
    response = await client.rest_get(
        f"/repos/{full_name}/actions/runs",
        {"per_page": "100", "created": f">={since:%Y-%m-%d}"},
    )
    runs = [parse_run(raw) for raw in response.data.get("workflow_runs", [])]
    pages = 1
    while (next_url := response.next_url) and pages < MAX_PAGES:
        response = await client.rest_get(next_url)
        runs.extend(parse_run(raw) for raw in response.data.get("workflow_runs", []))
        pages += 1
    return sorted(runs, key=lambda run: run.created_at, reverse=True)
