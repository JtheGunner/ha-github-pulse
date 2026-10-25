"""Work-in-progress figures for pull requests, free of Home Assistant imports."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timedelta

STALE_AFTER = timedelta(days=14)


def average_hours_to_merge(
    pairs: Iterable[tuple[datetime, datetime | None]],
) -> float | None:
    """Return the mean hours from opening to merging.

    ``pairs`` holds ``(opened, merged)``; pull requests that were closed
    without merging have no merge time and are skipped. Returns ``None`` when
    nothing was merged.
    """
    durations = [
        (merged - opened).total_seconds() / 3600
        for opened, merged in pairs
        if merged is not None and merged >= opened
    ]
    if not durations:
        return None
    return sum(durations) / len(durations)


def stale_cutoff(now: datetime) -> str:
    """Return the date before which an untouched open pull request counts as stale."""
    return (now - STALE_AFTER).strftime("%Y-%m-%d")
