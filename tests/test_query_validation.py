"""Tests for validating custom GraphQL queries."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from custom_components.github_pulse.api import GraphQLResult
from custom_components.github_pulse.api.query_validation import (
    QueryCost,
    QueryTooExpensiveError,
    QueryValidationError,
    dry_run_query,
    ensure_affordable,
    estimate_cost,
    minimum_interval,
    parse_query,
)

QUERY = (
    "query Repos($owner: String!) "
    "{ user(login: $owner) { repositories { totalCount } } }"
)


@pytest.mark.parametrize(
    "text",
    [
        'mutation { addStar(input: {starrableId: "x"}) { clientMutationId } }',
        "subscription { x }",
        "# query\nmutation Rename { x }",
        "  \n\t mutation\n{x}",
        "query A { a } mutation B { b }",
        "fragment F on User { login }",
        "",
    ],
)
def test_rejects_anything_but_a_single_query(text: str) -> None:
    with pytest.raises(QueryValidationError):
        parse_query(text)


def test_rejects_syntax_errors_with_the_reason() -> None:
    with pytest.raises(QueryValidationError, match="not valid GraphQL"):
        parse_query("query { viewer { ")


def test_a_word_query_inside_a_string_does_not_make_a_mutation_a_query() -> None:
    with pytest.raises(QueryValidationError, match="mutation"):
        parse_query('mutation { m(note: "query { a }") { id } }')


def test_accepts_shorthand_and_named_queries() -> None:
    assert parse_query("{ viewer { login } }").declared_variables == frozenset()
    assert parse_query(QUERY).declared_variables == {"owner"}


def test_dry_run_query_adds_the_cost_field_and_keeps_the_rest() -> None:
    text = dry_run_query(parse_query(QUERY))

    assert "pulseCost: rateLimit(dryRun: true)" in text
    assert "user(login: $owner)" in text
    assert "$owner: String!" in text
    parse_query(text)


def test_dry_run_query_names_an_anonymous_query() -> None:
    parse_query(dry_run_query(parse_query("{ viewer { login } }")))


class StubClient:
    def __init__(self, data: dict[str, Any]) -> None:
        self._data = data
        self.queries: list[str] = []

    async def graphql(self, query: str, variables: Any = None) -> GraphQLResult:
        self.queries.append(query)
        return GraphQLResult(self._data, [])


async def test_estimate_cost_reads_the_dry_run() -> None:
    client = StubClient({"pulseCost": {"cost": 3, "nodeCount": 120}})

    cost = await estimate_cost(client, parse_query(QUERY), {"owner": "octocat"})

    assert cost == QueryCost(3, 120)
    assert "dryRun: true" in client.queries[0]


async def test_estimate_cost_rejects_a_response_without_cost() -> None:
    with pytest.raises(QueryValidationError, match="did not report"):
        await estimate_cost(StubClient({}), parse_query(QUERY), {})


def test_an_over_budget_query_is_rejected_with_its_cost() -> None:
    with pytest.raises(QueryTooExpensiveError, match="costs 120 points") as raised:
        ensure_affordable(QueryCost(120, 5000))

    assert raised.value.cost == 120


def test_a_query_at_the_limit_is_accepted() -> None:
    ensure_affordable(QueryCost(50, 100))


@pytest.mark.parametrize(
    ("cost", "expected"),
    [
        (1, timedelta(minutes=5)),
        (40, timedelta(minutes=5)),
        (50, timedelta(seconds=360)),
        (0, timedelta(minutes=5)),
    ],
)
def test_minimum_interval_grows_with_cost(cost: int, expected: timedelta) -> None:
    assert minimum_interval(QueryCost(cost, 0)) == expected
