"""Track the remaining GitHub API budget per rate-limit resource."""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass

DEFAULT_THRESHOLD = 0.10
DEFAULT_RESOURCE = "core"


@dataclass(frozen=True, slots=True)
class ResourceBudget:
    """Snapshot of one rate-limit resource (``core``, ``graphql`` or ``search``)."""

    limit: int
    remaining: int
    reset_at: float

    @property
    def fraction_remaining(self) -> float:
        """Return the remaining share of the budget between 0 and 1."""
        if self.limit <= 0:
            return 0.0
        return self.remaining / self.limit


class RateBudget:
    """Keep the latest budget per resource from response headers.

    Coordinators ask :meth:`is_low` before polling and lengthen their interval
    while the budget is nearly spent.
    """

    def __init__(
        self,
        *,
        threshold: float = DEFAULT_THRESHOLD,
        clock: Callable[[], float] = time.time,
    ) -> None:
        """Create an empty budget with a "slow down" threshold (0..1)."""
        self._threshold = threshold
        self._clock = clock
        self._resources: dict[str, ResourceBudget] = {}

    def update_from_headers(self, headers: Mapping[str, str]) -> None:
        """Record the ``X-RateLimit-*`` headers of a response, if present."""
        lowered = {key.lower(): value for key, value in headers.items()}
        try:
            limit = int(lowered["x-ratelimit-limit"])
            remaining = int(lowered["x-ratelimit-remaining"])
            reset_at = float(lowered["x-ratelimit-reset"])
        except KeyError, ValueError:
            return
        resource = lowered.get("x-ratelimit-resource", DEFAULT_RESOURCE)
        self._resources[resource] = ResourceBudget(limit, remaining, reset_at)

    def get(self, resource: str = DEFAULT_RESOURCE) -> ResourceBudget | None:
        """Return the last known budget for a resource."""
        return self._resources.get(resource)

    def is_low(self, resource: str = DEFAULT_RESOURCE) -> bool:
        """Return whether the resource is at or below the slow-down threshold.

        A budget whose reset time has passed is treated as refilled.
        """
        budget = self._resources.get(resource)
        if budget is None or budget.reset_at <= self._clock():
            return False
        return budget.fraction_remaining <= self._threshold

    def seconds_until_reset(self, resource: str = DEFAULT_RESOURCE) -> float:
        """Return the seconds until the resource resets, or 0 when unknown."""
        budget = self._resources.get(resource)
        if budget is None:
            return 0.0
        return max(0.0, budget.reset_at - self._clock())
