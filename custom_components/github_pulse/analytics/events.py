"""Detect new events by comparing fresh data with what was seen before.

Pure and free of Home Assistant imports. Every detector takes the previous
state (``None`` on the very first run) and returns the new events plus the
state to store. On the first run the state is only initialised, so history
never fires as news.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from .actions import FAILED, INCONCLUSIVE, WorkflowRun

WORKFLOW_FAILED = "workflow_failed"
WORKFLOW_RECOVERED = "workflow_recovered"
RELEASE_PUBLISHED = "release_published"
REVIEW_REQUESTED = "review_requested"
PR_MERGED = "pr_merged"

MAX_SEEN = 100


@dataclass(frozen=True, slots=True)
class DetectedEvent:
    """An event to announce."""

    type: str
    repository: str | None
    data: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class PullRequestRef:
    """A pull request found through the search API."""

    id: int
    repository: str
    number: int
    title: str
    url: str


@dataclass(frozen=True, slots=True)
class WorkflowState:
    """Watermark of processed runs and the last conclusive outcome."""

    last_run_id: int
    last_outcome: str | None  # "failure", "success" or None


def workflow_events(
    repository: str, runs: Sequence[WorkflowRun], state: WorkflowState | None
) -> tuple[list[DetectedEvent], WorkflowState]:
    """Return failure and recovery events for completed runs newer than the state."""
    completed = sorted(
        (run for run in runs if run.status == "completed"), key=lambda run: run.id
    )
    if state is None:
        outcome = None
        for run in completed:
            if run.conclusion in FAILED:
                outcome = "failure"
            elif run.conclusion == "success":
                outcome = "success"
        return [], WorkflowState(max((r.id for r in completed), default=0), outcome)

    events: list[DetectedEvent] = []
    outcome = state.last_outcome
    last_id = state.last_run_id
    for run in completed:
        if run.id <= state.last_run_id:
            continue
        last_id = max(last_id, run.id)
        if run.conclusion in INCONCLUSIVE or run.conclusion is None:
            continue
        payload = {
            "repository": repository,
            "workflow": run.name,
            "run_id": run.id,
            "branch": run.branch,
            "conclusion": run.conclusion,
            "url": run.url,
        }
        if run.conclusion in FAILED:
            events.append(DetectedEvent(WORKFLOW_FAILED, repository, payload))
            outcome = "failure"
        elif run.conclusion == "success":
            if outcome == "failure":
                events.append(DetectedEvent(WORKFLOW_RECOVERED, repository, payload))
            outcome = "success"
    return events, WorkflowState(last_id, outcome)


def release_events(
    repository: str,
    tag: str | None,
    details: Mapping[str, Any],
    seen_tag: str | None,
    *,
    initialised: bool,
) -> tuple[list[DetectedEvent], str | None]:
    """Return a release event when the latest tag differs from the one seen."""
    if tag is None:
        return [], seen_tag
    if not initialised or seen_tag == tag:
        return [], tag
    payload = {"repository": repository, "tag": tag, **details}
    return [DetectedEvent(RELEASE_PUBLISHED, repository, payload)], tag


def _payload(pr: PullRequestRef) -> dict[str, Any]:
    return {
        "repository": pr.repository,
        "number": pr.number,
        "title": pr.title,
        "url": pr.url,
    }


def review_request_events(
    pulls: Sequence[PullRequestRef], seen: Sequence[int] | None
) -> tuple[list[DetectedEvent], list[int]]:
    """Return an event for each pull request newly awaiting review.

    The state is the *current* set, so a request that is withdrawn and made
    again fires again.
    """
    current = [pr.id for pr in pulls]
    if seen is None:
        return [], current
    known = set(seen)
    events = [
        DetectedEvent(REVIEW_REQUESTED, pr.repository, _payload(pr))
        for pr in pulls
        if pr.id not in known
    ]
    return events, current


def merged_events(
    merged: Sequence[PullRequestRef], seen: Sequence[int] | None
) -> tuple[list[DetectedEvent], list[int]]:
    """Return an event for each own pull request merged since the last check."""
    ids = [pr.id for pr in merged]
    if seen is None:
        return [], ids[:MAX_SEEN]
    known = set(seen)
    events = [
        DetectedEvent(PR_MERGED, pr.repository, _payload(pr))
        for pr in merged
        if pr.id not in known
    ]
    return events, (ids + [i for i in seen if i not in set(ids)])[:MAX_SEEN]
