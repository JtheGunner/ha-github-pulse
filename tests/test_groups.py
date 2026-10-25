"""Tests for demand-based data groups."""

from custom_components.github_pulse.groups import GroupedEntity, active_groups

ENTITIES = [
    GroupedEntity("commits", "contributions"),
    GroupedEntity("streak", "calendar", enabled_default=False),
    GroupedEntity("weekday", "calendar", enabled_default=False),
    GroupedEntity("top_language", "languages"),
]


def _unregistered(_: str) -> bool | None:
    return None


def test_defaults_decide_for_unregistered_entities() -> None:
    assert active_groups(ENTITIES, _unregistered) == {"contributions", "languages"}


def test_an_enabled_registry_entry_activates_its_group() -> None:
    states = {"streak": True}

    assert active_groups(ENTITIES, states.get) == {
        "contributions",
        "calendar",
        "languages",
    }


def test_a_user_disabled_entity_deactivates_its_group() -> None:
    states = {"top_language": False}

    assert active_groups(ENTITIES, states.get) == {"contributions"}


def test_a_group_stays_active_while_any_entity_needs_it() -> None:
    states = {"streak": True, "weekday": False}

    assert "calendar" in active_groups(ENTITIES, states.get)


def test_no_entities_need_no_groups() -> None:
    assert active_groups([], _unregistered) == frozenset()
