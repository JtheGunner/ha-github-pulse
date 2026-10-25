"""Tests for the rate budget."""

from custom_components.github_pulse.api import RateBudget


def _headers(
    remaining: int, *, limit: int = 5000, reset: int = 2000, resource: str = "core"
) -> dict[str, str]:
    return {
        "X-RateLimit-Limit": str(limit),
        "X-RateLimit-Remaining": str(remaining),
        "X-RateLimit-Reset": str(reset),
        "X-RateLimit-Resource": resource,
    }


def test_headers_are_recorded_per_resource() -> None:
    budget = RateBudget(clock=lambda: 1000.0)

    budget.update_from_headers(_headers(4000))
    budget.update_from_headers(_headers(25, limit=30, resource="search"))

    assert budget.get("core").remaining == 4000  # type: ignore[union-attr]
    assert budget.get("search").limit == 30  # type: ignore[union-attr]
    assert budget.get("graphql") is None


def test_header_names_are_case_insensitive() -> None:
    budget = RateBudget(clock=lambda: 1000.0)

    budget.update_from_headers({k.lower(): v for k, v in _headers(10).items()})

    assert budget.get().remaining == 10  # type: ignore[union-attr]


def test_missing_resource_header_defaults_to_core() -> None:
    budget = RateBudget(clock=lambda: 1000.0)
    headers = _headers(10)
    del headers["X-RateLimit-Resource"]

    budget.update_from_headers(headers)

    assert budget.get("core") is not None


def test_incomplete_or_invalid_headers_are_ignored() -> None:
    budget = RateBudget(clock=lambda: 1000.0)

    budget.update_from_headers({"X-RateLimit-Remaining": "5"})
    budget.update_from_headers({**_headers(5), "X-RateLimit-Limit": "many"})

    assert budget.get() is None


def test_is_low_at_and_below_the_threshold() -> None:
    budget = RateBudget(threshold=0.10, clock=lambda: 1000.0)

    budget.update_from_headers(_headers(501))
    assert not budget.is_low()

    budget.update_from_headers(_headers(500))
    assert budget.is_low()


def test_is_low_is_false_for_unknown_resource() -> None:
    assert not RateBudget().is_low("graphql")


def test_budget_counts_as_refilled_after_reset() -> None:
    now = [1000.0]
    budget = RateBudget(clock=lambda: now[0])
    budget.update_from_headers(_headers(0, reset=1500))
    assert budget.is_low()

    now[0] = 1500.0

    assert not budget.is_low()


def test_seconds_until_reset() -> None:
    now = [1000.0]
    budget = RateBudget(clock=lambda: now[0])
    assert budget.seconds_until_reset() == 0.0

    budget.update_from_headers(_headers(10, reset=1090))
    assert budget.seconds_until_reset() == 90.0

    now[0] = 2000.0
    assert budget.seconds_until_reset() == 0.0


def test_zero_limit_has_no_remaining_fraction() -> None:
    budget = RateBudget(clock=lambda: 1000.0)
    budget.update_from_headers(_headers(0, limit=0))

    assert budget.get().fraction_remaining == 0.0  # type: ignore[union-attr]
