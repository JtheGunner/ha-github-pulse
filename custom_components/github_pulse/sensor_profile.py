"""Descriptions of the account-wide profile sensors."""

from __future__ import annotations

from calendar import day_name
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, UnitOfTime

from .analytics.history import MonthKey, MonthStats
from .analytics.languages import LanguageMonth, combine, shares, shift
from .analytics.patterns import busiest_month, streaks, weekday_pattern
from .analytics.periods import percent_change
from .const import WEIGHTING_COMMITS
from .profile_coordinator import (
    GROUP_CALENDAR,
    GROUP_CURRENT,
    GROUP_HISTORY,
    GROUP_LANGUAGES,
    GROUP_SEARCH,
    CurrentPeriods,
)
from .search_fetch import SearchCounts
from .settings import Settings

type Attributes = Mapping[str, Any]


@dataclass(frozen=True, kw_only=True)
class ProfileView:
    """What a sensor may read: coordinator data and the user's options."""

    data: Mapping[str, Any]
    settings: Settings
    today: date

    @property
    def current(self) -> CurrentPeriods:
        """Return the current-period group."""
        return self.data[GROUP_CURRENT]  # type: ignore[no-any-return]

    @property
    def history(self) -> Mapping[MonthKey, MonthStats]:
        """Return the monthly history group."""
        return self.data[GROUP_HISTORY]  # type: ignore[no-any-return]

    @property
    def languages(self) -> Mapping[MonthKey, LanguageMonth]:
        """Return the monthly language estimate group."""
        return self.data[GROUP_LANGUAGES]  # type: ignore[no-any-return]

    @property
    def search(self) -> SearchCounts:
        """Return the search-API counts group."""
        return self.data[GROUP_SEARCH]  # type: ignore[no-any-return]

    @property
    def daily(self) -> Mapping[date, int]:
        """Return the contribution calendar group."""
        return self.data[GROUP_CALENDAR]  # type: ignore[no-any-return]


@dataclass(frozen=True, kw_only=True)
class ProfileSensorDescription(SensorEntityDescription):
    """A profile sensor with the data group and the readers for state and attributes."""

    group: str
    value_fn: Callable[[ProfileView], Any]
    attributes_fn: Callable[[ProfileView], Attributes] | None = None


def _this_month_total(view: ProfileView) -> int:
    return view.current.this_month.total(
        include_restricted=view.settings.include_restricted
    )


def _contribution_attributes(view: ProfileView) -> Attributes:
    month = view.current.this_month
    return {
        "visible": month.visible_total,
        "restricted": month.restricted,
        "includes_restricted": view.settings.include_restricted,
    }


def _change(view: ProfileView, *, year: bool) -> float | None:
    current = view.current
    baseline = current.previous_year if year else current.previous_month
    change = percent_change(current.this_month.commits, baseline.commits)
    return None if change is None else round(change, 1)


def _change_attributes(view: ProfileView, *, year: bool) -> Attributes:
    current = view.current
    baseline = current.previous_year if year else current.previous_month
    return {
        "commits": current.this_month.commits,
        "commits_in_comparison_span": baseline.commits,
        "elapsed_days": current.today.day,
    }


def _monthly_totals(view: ProfileView) -> dict[tuple[int, int], int]:
    include = view.settings.include_restricted
    return {
        (key.year, key.month): stats.total(include_restricted=include)
        for key, stats in view.history.items()
    }


def _busiest(view: ProfileView) -> str | None:
    best = busiest_month(_monthly_totals(view), view.today.year)
    return None if best is None else MonthKey(view.today.year, best.month).label


def _busiest_attributes(view: ProfileView) -> Attributes:
    best = busiest_month(_monthly_totals(view), view.today.year)
    return {} if best is None else {"contributions": best.count}


def _year_language(view: ProfileView, year: int) -> LanguageMonth:
    return combine(month for key, month in view.languages.items() if key.year == year)


def _year_shares(view: ProfileView, year: int) -> dict[str, float]:
    return shares(
        _year_language(view, year),
        by_commits=view.settings.language_weighting == WEIGHTING_COMMITS,
    )


def _top_language(view: ProfileView) -> str | None:
    ranking = _year_shares(view, view.today.year)
    return next(iter(ranking), None)


def _percent(ranking: Mapping[str, float], limit: int = 10) -> dict[str, float]:
    return {
        name: round(value * 100, 1) for name, value in list(ranking.items())[:limit]
    }


def _top_language_attributes(view: ProfileView) -> Attributes:
    year = _year_language(view, view.today.year)
    return {
        "method": "estimated",
        "weighting": view.settings.language_weighting,
        "year": view.today.year,
        "ranking": _percent(_year_shares(view, view.today.year)),
        "unclassified_commits": year.unclassified_commits,
        "truncated": year.truncated,
    }


def _language_changes(view: ProfileView) -> dict[str, float]:
    year = view.today.year
    previous = _year_shares(view, year - 1)
    current = _year_shares(view, year)
    if not previous or not current:
        return {}
    return shift(current, previous)


def _top_gainer(view: ProfileView) -> str | None:
    changes = _language_changes(view)
    return next(iter(changes), None)


def _language_shift_attributes(view: ProfileView) -> Attributes:
    changes = _language_changes(view)
    if not changes:
        return {"method": "estimated"}
    loser, loser_change = list(changes.items())[-1]
    gainer, gainer_change = next(iter(changes.items()))
    return {
        "method": "estimated",
        "compared_with": view.today.year - 1,
        "gainer_points": round(gainer_change, 1),
        "loser": loser,
        "loser_points": round(loser_change, 1),
        "changes_in_points": {n: round(v, 1) for n, v in list(changes.items())[:10]},
        "gainer": gainer,
    }


def _active_days_this_month(view: ProfileView) -> int:
    today = view.today
    return sum(
        1
        for day, count in view.daily.items()
        if count > 0 and (day.year, day.month) == (today.year, today.month)
    )


def _most_productive_weekday(view: ProfileView) -> str | None:
    pattern = weekday_pattern(view.daily)
    return None if pattern is None else day_name[pattern.most_productive].lower()


PROFILE_SENSORS: tuple[ProfileSensorDescription, ...] = (
    ProfileSensorDescription(
        key="contributions_this_month",
        translation_key="contributions_this_month",
        group=GROUP_CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_this_month_total,
        attributes_fn=_contribution_attributes,
    ),
    ProfileSensorDescription(
        key="commits_this_month",
        translation_key="commits_this_month",
        group=GROUP_CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda view: view.current.this_month.commits,
    ),
    ProfileSensorDescription(
        key="pull_requests_this_month",
        translation_key="pull_requests_this_month",
        group=GROUP_CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda view: view.current.this_month.pull_requests,
    ),
    ProfileSensorDescription(
        key="commits_vs_last_month",
        translation_key="commits_vs_last_month",
        group=GROUP_CURRENT,
        native_unit_of_measurement=PERCENTAGE,
        suggested_display_precision=1,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda view: _change(view, year=False),
        attributes_fn=lambda view: _change_attributes(view, year=False),
    ),
    ProfileSensorDescription(
        key="commits_vs_last_year",
        translation_key="commits_vs_last_year",
        group=GROUP_CURRENT,
        native_unit_of_measurement=PERCENTAGE,
        suggested_display_precision=1,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda view: _change(view, year=True),
        attributes_fn=lambda view: _change_attributes(view, year=True),
    ),
    ProfileSensorDescription(
        key="busiest_month",
        translation_key="busiest_month",
        group=GROUP_HISTORY,
        value_fn=_busiest,
        attributes_fn=_busiest_attributes,
    ),
    ProfileSensorDescription(
        key="current_streak",
        translation_key="current_streak",
        group=GROUP_CALENDAR,
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.DAYS,
        value_fn=lambda view: streaks(view.daily, view.today).current,
    ),
    ProfileSensorDescription(
        key="longest_streak",
        translation_key="longest_streak",
        group=GROUP_CALENDAR,
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.DAYS,
        value_fn=lambda view: streaks(view.daily, view.today).longest,
    ),
    ProfileSensorDescription(
        key="top_language",
        translation_key="top_language",
        group=GROUP_LANGUAGES,
        value_fn=_top_language,
        attributes_fn=_top_language_attributes,
    ),
    ProfileSensorDescription(
        key="reviews_this_month",
        translation_key="reviews_this_month",
        group=GROUP_CURRENT,
        entity_registry_enabled_default=False,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda view: view.current.this_month.reviews,
    ),
    ProfileSensorDescription(
        key="issues_this_month",
        translation_key="issues_this_month",
        group=GROUP_CURRENT,
        entity_registry_enabled_default=False,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda view: view.current.this_month.issues,
    ),
    ProfileSensorDescription(
        key="active_days_this_month",
        translation_key="active_days_this_month",
        group=GROUP_CALENDAR,
        entity_registry_enabled_default=False,
        native_unit_of_measurement=UnitOfTime.DAYS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_active_days_this_month,
    ),
    ProfileSensorDescription(
        key="most_productive_weekday",
        translation_key="most_productive_weekday",
        group=GROUP_CALENDAR,
        entity_registry_enabled_default=False,
        device_class=SensorDeviceClass.ENUM,
        options=[name.lower() for name in day_name],
        value_fn=_most_productive_weekday,
    ),
    ProfileSensorDescription(
        key="language_shift",
        translation_key="language_shift",
        group=GROUP_LANGUAGES,
        entity_registry_enabled_default=False,
        value_fn=_top_gainer,
        attributes_fn=_language_shift_attributes,
    ),
    ProfileSensorDescription(
        key="review_requests",
        translation_key="review_requests",
        group=GROUP_SEARCH,
        entity_registry_enabled_default=False,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda view: view.search.review_requested,
    ),
    ProfileSensorDescription(
        key="authored_open_pull_requests",
        translation_key="authored_open_pull_requests",
        group=GROUP_SEARCH,
        entity_registry_enabled_default=False,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda view: view.search.authored_open,
    ),
)
