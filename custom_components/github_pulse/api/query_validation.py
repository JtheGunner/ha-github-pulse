"""Validation of user-written GraphQL queries, free of Home Assistant imports.

Custom queries run on a schedule with the user's token, so they are held to
three rules: only read operations, a known cost, and a polling interval that
keeps that cost inside a small share of the hourly rate budget.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Protocol

from graphql import (
    DocumentNode,
    FieldNode,
    GraphQLError,
    NameNode,
    OperationDefinitionNode,
    OperationType,
    SelectionSetNode,
    parse,
    print_ast,
)

from .client import GraphQLResult

COST_ALIAS = "pulseCost"
MAX_COST = 50
HOURLY_BUDGET_SHARE = 500
SECONDS_PER_HOUR = 3600
MIN_INTERVAL = timedelta(minutes=5)


class QueryValidationError(Exception):
    """The query cannot be used as a custom query."""


class QueryTooExpensiveError(QueryValidationError):
    """The query costs more rate-limit points than a custom query may use."""

    def __init__(self, cost: int, limit: int) -> None:
        """Keep the cost so the message can show it."""
        super().__init__(f"the query costs {cost} points, the limit is {limit}")
        self.cost = cost
        self.limit = limit


class GraphQLRunner(Protocol):
    """The part of the API client validation needs."""

    async def graphql(
        self, query: str, variables: Mapping[str, Any] | None = None
    ) -> GraphQLResult:
        """Run a GraphQL query."""
        ...


@dataclass(frozen=True, slots=True)
class ParsedQuery:
    """A syntactically valid, read-only query."""

    document: DocumentNode
    operation: OperationDefinitionNode
    declared_variables: frozenset[str]


@dataclass(frozen=True, slots=True)
class QueryCost:
    """What GitHub reports for a dry run of the query."""

    cost: int
    node_count: int


def parse_query(text: str) -> ParsedQuery:
    """Parse ``text`` and accept exactly one ``query`` operation.

    Mutations and subscriptions are rejected whatever the formatting, because
    the decision is made on the parsed syntax tree, not on the text.
    """
    try:
        document = parse(text)
    except GraphQLError as err:
        msg = f"the query is not valid GraphQL: {err.message}"
        raise QueryValidationError(msg) from err
    operations = [
        d for d in document.definitions if isinstance(d, OperationDefinitionNode)
    ]
    if not operations:
        msg = "the query contains no operation"
        raise QueryValidationError(msg)
    if len(operations) > 1:
        msg = "the query must contain exactly one operation"
        raise QueryValidationError(msg)
    operation = operations[0]
    if operation.operation is not OperationType.QUERY:
        msg = f"only queries are allowed, not a {operation.operation.value}"
        raise QueryValidationError(msg)
    declared = frozenset(
        v.variable.name.value for v in operation.variable_definitions or ()
    )
    return ParsedQuery(document, operation, declared)


def dry_run_query(parsed: ParsedQuery) -> str:
    """Return the query with a ``rateLimit(dryRun: true)`` field added.

    With ``dryRun`` GitHub reports the cost without evaluating the query.
    """
    cost_field = parse(
        f"{{ {COST_ALIAS}: rateLimit(dryRun: true) {{ cost nodeCount }} }}"
    ).definitions[0]
    assert isinstance(cost_field, OperationDefinitionNode)  # noqa: S101
    added = cost_field.selection_set.selections[0]
    assert isinstance(added, FieldNode)  # noqa: S101
    selections = (*parsed.operation.selection_set.selections, added)
    operation = OperationDefinitionNode(
        operation=OperationType.QUERY,
        name=parsed.operation.name or NameNode(value="PulseCost"),
        variable_definitions=parsed.operation.variable_definitions,
        directives=parsed.operation.directives,
        selection_set=SelectionSetNode(selections=selections),
    )
    others = tuple(d for d in parsed.document.definitions if d is not parsed.operation)
    return print_ast(DocumentNode(definitions=(*others, operation)))


async def estimate_cost(
    client: GraphQLRunner,
    parsed: ParsedQuery,
    variables: Mapping[str, Any],
) -> QueryCost:
    """Ask GitHub what the query costs without running it."""
    result = await client.graphql(dry_run_query(parsed), variables)
    info = result.data.get(COST_ALIAS)
    if not isinstance(info, dict) or not isinstance(info.get("cost"), int):
        msg = "GitHub did not report a cost for the query"
        raise QueryValidationError(msg)
    return QueryCost(info["cost"], int(info.get("nodeCount") or 0))


def ensure_affordable(cost: QueryCost, limit: int = MAX_COST) -> None:
    """Reject a query costing more than ``limit`` points per run."""
    if cost.cost > limit:
        raise QueryTooExpensiveError(cost.cost, limit)


def minimum_interval(cost: QueryCost) -> timedelta:
    """Return the shortest polling interval that keeps the query affordable.

    A query may use at most ``HOURLY_BUDGET_SHARE`` points per hour, and never
    polls faster than ``MIN_INTERVAL``.
    """
    seconds = math.ceil(max(cost.cost, 1) * SECONDS_PER_HOUR / HOURLY_BUDGET_SHARE)
    return max(MIN_INTERVAL, timedelta(seconds=seconds))
