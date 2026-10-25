"""Tests for event detection and deduplication."""

from datetime import UTC, datetime

from custom_components.github_pulse.analytics.actions import WorkflowRun
from custom_components.github_pulse.analytics.events import (
    PR_MERGED,
    RELEASE_PUBLISHED,
    REVIEW_REQUESTED,
    WORKFLOW_FAILED,
    WORKFLOW_RECOVERED,
    PullRequestRef,
    merged_events,
    release_events,
    review_request_events,
    workflow_events,
)

T = datetime(2026, 10, 25, tzinfo=UTC)


def _run(run_id: int, conclusion: str | None, status: str = "completed") -> WorkflowRun:
    return WorkflowRun(
        id=run_id,
        name="CI",
        branch="main",
        status=status,
        conclusion=conclusion,
        created_at=T,
        started_at=T,
        updated_at=T,
        url=f"https://example.test/{run_id}",
    )


def _pr(pr_id: int) -> PullRequestRef:
    return PullRequestRef(
        pr_id, "o/r", pr_id, f"PR {pr_id}", f"https://example.test/{pr_id}"
    )


def test_the_first_run_only_initialises_the_state() -> None:
    events, state = workflow_events(
        "o/r", [_run(2, "failure"), _run(1, "success")], None
    )

    assert events == []
    assert (state.last_run_id, state.last_outcome) == (2, "failure")


def test_a_new_failing_run_fires_exactly_once() -> None:
    _, state = workflow_events("o/r", [_run(1, "success")], None)
    runs = [_run(2, "failure"), _run(1, "success")]

    events, state = workflow_events("o/r", runs, state)
    again, _ = workflow_events("o/r", runs, state)

    assert [e.type for e in events] == [WORKFLOW_FAILED]
    assert events[0].data["run_id"] == 2
    assert again == []


def test_a_success_after_a_failure_is_a_recovery() -> None:
    _, state = workflow_events("o/r", [_run(1, "failure")], None)

    events, state = workflow_events(
        "o/r", [_run(2, "success"), _run(1, "failure")], state
    )

    assert [e.type for e in events] == [WORKFLOW_RECOVERED]
    assert state.last_outcome == "success"


def test_a_success_after_a_success_is_silent() -> None:
    _, state = workflow_events("o/r", [_run(1, "success")], None)

    events, _ = workflow_events("o/r", [_run(2, "success"), _run(1, "success")], state)

    assert events == []


def test_cancelled_and_unfinished_runs_do_not_count() -> None:
    _, state = workflow_events("o/r", [_run(1, "success")], None)
    runs = [
        _run(4, None, status="in_progress"),
        _run(3, "cancelled"),
        _run(2, "skipped"),
        _run(1, "success"),
    ]

    events, new = workflow_events("o/r", runs, state)

    assert events == []
    assert new.last_run_id == 3


def test_several_new_runs_are_processed_in_order() -> None:
    _, state = workflow_events("o/r", [_run(1, "success")], None)
    runs = [
        _run(4, "success"),
        _run(3, "failure"),
        _run(2, "failure"),
        _run(1, "success"),
    ]

    events, _ = workflow_events("o/r", runs, state)

    assert [e.type for e in events] == [
        WORKFLOW_FAILED,
        WORKFLOW_FAILED,
        WORKFLOW_RECOVERED,
    ]


def test_a_run_that_was_running_is_announced_once_it_completes() -> None:
    _, state = workflow_events("o/r", [_run(1, "success")], None)
    pending = [_run(2, None, status="in_progress"), _run(1, "success")]
    _, state = workflow_events("o/r", pending, state)

    events, _ = workflow_events("o/r", [_run(2, "failure"), _run(1, "success")], state)

    assert [e.type for e in events] == [WORKFLOW_FAILED]


def test_a_new_release_tag_fires_once() -> None:
    first, tag = release_events("o/r", "v1", {}, None, initialised=False)
    new, tag = release_events("o/r", "v2", {"url": "u"}, tag, initialised=True)
    same, _ = release_events("o/r", "v2", {}, tag, initialised=True)

    assert first == []
    assert [e.type for e in new] == [RELEASE_PUBLISHED]
    assert new[0].data == {"repository": "o/r", "tag": "v2", "url": "u"}
    assert same == []


def test_a_repository_without_releases_stays_silent() -> None:
    assert release_events("o/r", None, {}, None, initialised=True) == ([], None)


def test_review_requests_fire_for_new_pull_requests_only() -> None:
    _, ids = review_request_events([_pr(1)], None)

    events, ids = review_request_events([_pr(1), _pr(2)], ids)

    assert [e.type for e in events] == [REVIEW_REQUESTED]
    assert events[0].data["number"] == 2
    assert ids == [1, 2]


def test_a_withdrawn_and_renewed_review_request_fires_again() -> None:
    _, ids = review_request_events([_pr(1)], None)
    _, ids = review_request_events([], ids)

    events, _ = review_request_events([_pr(1)], ids)

    assert len(events) == 1


def test_merges_fire_once_and_remember_recent_ids() -> None:
    _, seen = merged_events([_pr(1)], None)

    events, seen = merged_events([_pr(2), _pr(1)], seen)
    again, _ = merged_events([_pr(2), _pr(1)], seen)

    assert [e.type for e in events] == [PR_MERGED]
    assert again == []
    assert seen == [2, 1]
