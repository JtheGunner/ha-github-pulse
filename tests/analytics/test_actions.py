"""Tests for the workflow-run summaries."""

from datetime import UTC, datetime, timedelta

import pytest
from custom_components.github_pulse.analytics.actions import (
    WorkflowRun,
    average_duration,
    failure_rate,
    summarize,
)

NOW = datetime(2026, 10, 25, 12, tzinfo=UTC)


def _run(
    run_id: int,
    *,
    age: timedelta = timedelta(hours=1),
    status: str = "completed",
    conclusion: str | None = "success",
    duration: timedelta = timedelta(minutes=2),
) -> WorkflowRun:
    created = NOW - age
    return WorkflowRun(
        id=run_id,
        name="CI",
        branch="main",
        status=status,
        conclusion=conclusion,
        created_at=created,
        started_at=created,
        updated_at=created + duration,
    )


def test_failure_rate_ignores_inconclusive_runs() -> None:
    runs = [
        _run(1, conclusion="failure"),
        _run(2, conclusion="success"),
        _run(3, conclusion="cancelled"),
        _run(4, conclusion="skipped"),
        _run(5, status="in_progress", conclusion=None),
    ]

    assert failure_rate(runs, NOW - timedelta(days=7)) == 50.0


def test_timeouts_and_startup_failures_count_as_failures() -> None:
    runs = [_run(1, conclusion="timed_out"), _run(2, conclusion="startup_failure")]

    assert failure_rate(runs, NOW - timedelta(days=7)) == 100.0


def test_failure_rate_is_none_without_conclusive_runs() -> None:
    assert failure_rate([], NOW - timedelta(days=7)) is None
    assert (
        failure_rate([_run(1, conclusion="cancelled")], NOW - timedelta(days=7)) is None
    )


def test_runs_outside_the_window_are_ignored() -> None:
    old = _run(1, age=timedelta(days=10), conclusion="failure")

    assert failure_rate([old], NOW - timedelta(days=7)) is None
    assert failure_rate([old], NOW - timedelta(days=30)) == 100.0


def test_average_duration_uses_completed_runs_only() -> None:
    runs = [
        _run(1, duration=timedelta(minutes=2)),
        _run(2, duration=timedelta(minutes=4)),
        _run(3, status="in_progress", conclusion=None),
    ]

    assert average_duration(runs, NOW - timedelta(days=7)) == 180.0
    assert average_duration([], NOW - timedelta(days=7)) is None


def test_summary_reports_state_queue_and_runs_today() -> None:
    runs = [
        _run(1, age=timedelta(minutes=5), status="in_progress", conclusion=None),
        _run(2, age=timedelta(minutes=10), status="queued", conclusion=None),
        _run(3, age=timedelta(hours=2), conclusion="failure"),
        _run(4, age=timedelta(days=2), conclusion="success"),
    ]

    summary = summarize(runs, NOW)

    assert summary.running is True
    assert summary.queued == 1
    assert summary.runs_today == 3
    assert summary.last_result == "failure"


def test_last_result_is_the_newest_completed_run() -> None:
    runs = [_run(1, age=timedelta(days=3), conclusion="failure"), _run(2)]

    assert summarize(runs, NOW).last_result == "success"


def test_an_empty_history_gives_neutral_values() -> None:
    summary = summarize([], NOW)

    assert summary.last_result is None
    assert summary.running is False
    assert summary.runs_today == 0
    assert summary.failure_rate_7d is None
    assert summary.average_duration_seconds is None


@pytest.mark.parametrize("status", ["queued", "waiting", "pending", "requested"])
def test_every_waiting_status_counts_as_queued(status: str) -> None:
    assert summarize([_run(1, status=status, conclusion=None)], NOW).queued == 1
