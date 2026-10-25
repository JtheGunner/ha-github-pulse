"""Demand-based data groups.

Every entity declares the data group it reads. A coordinator only fetches the
groups that at least one *enabled* entity needs, so disabled-by-default
sensors cost no API calls.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class GroupedEntity:
    """The parts of an entity description that decide whether a group is needed."""

    key: str
    group: str
    enabled_default: bool = True


def active_groups(
    entities: Iterable[GroupedEntity],
    registered_enabled: Callable[[str], bool | None],
) -> frozenset[str]:
    """Return the groups needed by at least one enabled entity.

    ``registered_enabled(key)`` answers ``True``/``False`` when the entity is
    already in the registry (the user's choice wins) and ``None`` when it is
    not registered yet, in which case its default decides.
    """
    needed: set[str] = set()
    for entity in entities:
        enabled = registered_enabled(entity.key)
        if enabled is None:
            enabled = entity.enabled_default
        if enabled:
            needed.add(entity.group)
    return frozenset(needed)
