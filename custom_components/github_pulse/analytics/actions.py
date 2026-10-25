"""Summaries of GitHub Actions workflow runs.

Pure and free of Home Assistant imports.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

FAILED = frozenset({"failure", "timed_out", "startup_failure"})
# Outcomes that say nothing about whether the code works.
INCONCLUSIVE = frozenset(
    {"cancelled", "skipped", "neutral", "stale", "action_required"}
)
ACTIVE = frozenset({"in_progress"})
WAITING = frozenset({"queued", "waiting", "pending", "requested"})

SHORT_WINDOW = timedelta(days=7)
LONG_WINDOW = timedelta(days=30)


@dataclass(frozen=True, slots=True)
class WorkflowRun:
    """One workflow run."""

    id: int
    name: str
    branch: str | None
    status: str
    conclusion: str | None
    created_at: datetime
    started_at: datetime | None
    updated_at: datetime
    url: str | None = None


@dataclass(frozen=True, slots=True)
class ActionsSummary:
    """What the Actions sensors report for one repository."""

    last_result: str | None
    running: bool
    queued: int
    runs_today: int
    failure_rate_7d: float | None
    failure_rate_30d: float | None
    average_duration_seconds: float | None


def failure_rate(runs: Sequence[WorkflowRun], since: datetime) -> float | None:
    """Return the failed share (percent) of conclusive completed runs since a time.

    ``None`` when no conclusive run falls into the window.
    """
    conclusive = [
        run
        for run in runs
        if run.created_at >= since
        and run.status == "completed"
        and run.conclusion is not None
        and run.conclusion not in INCONCLUSIVE
    ]
    if not conclusive:
        return None
    failed = sum(1 for run in conclusive if run.conclusion in FAILED)
    return round(failed / len(conclusive) * 100, 1)


def average_duration(runs: Sequence[WorkflowRun], since: datetime) -> float | None:
    """Return the mean duration in seconds of completed runs since a time."""
    durations = [
        (run.updated_at - run.started_at).total_seconds()
        for run in runs
        if run.created_at >= since
        and run.status == "completed"
        and run.started_at is not None
        and run.updated_at >= run.started_at
    ]
    if not durations:
        return None
    return round(sum(durations) / len(durations), 1)


def latest_completed(runs: Sequence[WorkflowRun]) -> WorkflowRun | None:
    """Return the newest completed run."""
    completed = [run for run in runs if run.status == "completed"]
    return max(completed, key=lambda run: run.created_at, default=None)


def summarize(runs: Sequence[WorkflowRun], now: datetime) -> ActionsSummary:
    """Summarise a repository's recent runs."""
    last = latest_completed(runs)
    return ActionsSummary(
        last_result=None if last is None else last.conclusion,
        running=any(run.status in ACTIVE for run in runs),
        queued=sum(1 for run in runs if run.status in WAITING),
        runs_today=sum(1 for run in runs if run.created_at.date() == now.date()),
        failure_rate_7d=failure_rate(runs, now - SHORT_WINDOW),
        failure_rate_30d=failure_rate(runs, now - LONG_WINDOW),
        average_duration_seconds=average_duration(runs, now - SHORT_WINDOW),
    )
