"""Daily rhythm from event timestamps, free of Home Assistant imports.

GitHub's events feed holds at most 300 recent events, so everything computed
here is an approximation of when someone works, not a measurement.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, tzinfo

MIN_EVENTS = 10
NIGHT_HOURS = frozenset({22, 23, 0, 1, 2, 3, 4})


@dataclass(frozen=True, slots=True)
class Rhythm:
    """When the recent events happened, in the viewer's time zone."""

    events: int
    most_active_hour: int | None
    night_owl_share: float | None


def rhythm(times: Iterable[datetime], zone: tzinfo) -> Rhythm:
    """Return the most active hour and the share of events between 22:00 and 05:00.

    Timestamps must be time-zone aware. With fewer than ``MIN_EVENTS`` events
    both values are ``None``: a handful of events says nothing about a rhythm.
    The earliest hour wins a tie.
    """
    hours = [moment.astimezone(zone).hour for moment in times]
    if len(hours) < MIN_EVENTS:
        return Rhythm(len(hours), None, None)
    counts = [hours.count(hour) for hour in range(24)]
    busiest = counts.index(max(counts))
    night = sum(1 for hour in hours if hour in NIGHT_HOURS)
    return Rhythm(len(hours), busiest, night / len(hours))
