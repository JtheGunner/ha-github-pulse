"""Import the monthly history as external long-term statistics (opt-in).

Statistics are keyed by ``(statistic_id, start)``, so importing the same
months again overwrites them and is idempotent.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, time
from zoneinfo import ZoneInfo

from homeassistant.components.recorder.models import (
    StatisticData,
    StatisticMeanType,
    StatisticMetaData,
)
from homeassistant.components.recorder.statistics import async_add_external_statistics
from homeassistant.core import HomeAssistant

from .analytics.history import MonthKey, MonthStats
from .analytics.languages import LanguageMonth, shares
from .const import DOMAIN

LANGUAGE_TOP = 8
_SYMBOLS = {"+": "plus", "#": "sharp"}


@dataclass(frozen=True, slots=True)
class StatisticSeries:
    """One statistic with its metadata and monthly points."""

    metadata: StatisticMetaData
    points: list[StatisticData]


def slug(name: str) -> str:
    """Return a statistic-id safe version of a name ("C++" becomes "cplusplus")."""
    for symbol, word in _SYMBOLS.items():
        name = name.replace(symbol, word)
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def _start(key: MonthKey, zone: ZoneInfo) -> datetime:
    return datetime.combine(
        datetime(key.year, key.month, 1).date(), time.min, tzinfo=zone
    ).astimezone(UTC)


def _metadata(
    login: str, suffix: str, name: str, unit: str | None
) -> StatisticMetaData:
    return StatisticMetaData(
        mean_type=StatisticMeanType.NONE,
        has_sum=False,
        name=name,
        source=DOMAIN,
        statistic_id=f"{DOMAIN}:{slug(login)}_{suffix}",
        unit_class=None,
        unit_of_measurement=unit,
    )


def build_series(
    login: str,
    history: Mapping[MonthKey, MonthStats],
    languages: Mapping[MonthKey, LanguageMonth],
    *,
    zone: ZoneInfo,
    include_restricted: bool,
    by_commits: bool,
) -> list[StatisticSeries]:
    """Build the series: commits, contributions and per-language shares."""
    series = [
        StatisticSeries(
            _metadata(login, "commits", f"GitHub {login} commits", None),
            [
                StatisticData(start=_start(key, zone), state=float(stats.commits))
                for key, stats in sorted(history.items())
            ],
        ),
        StatisticSeries(
            _metadata(login, "contributions", f"GitHub {login} contributions", None),
            [
                StatisticData(
                    start=_start(key, zone),
                    state=float(stats.total(include_restricted=include_restricted)),
                )
                for key, stats in sorted(history.items())
            ],
        ),
    ]
    series.extend(_language_series(login, languages, zone, by_commits=by_commits))
    return series


def _language_series(
    login: str,
    languages: Mapping[MonthKey, LanguageMonth],
    zone: ZoneInfo,
    *,
    by_commits: bool,
) -> list[StatisticSeries]:
    monthly = {
        key: shares(month, by_commits=by_commits) for key, month in languages.items()
    }
    totals: dict[str, float] = {}
    for month_shares in monthly.values():
        for name, share in month_shares.items():
            totals[name] = totals.get(name, 0.0) + share
    top = [
        name
        for name, _ in sorted(totals.items(), key=lambda item: (-item[1], item[0]))
        if name != "Other"
    ][:LANGUAGE_TOP]
    result = []
    for name in top:
        points = [
            StatisticData(
                start=_start(key, zone), state=round(s.get(name, 0.0) * 100, 2)
            )
            for key, s in sorted(monthly.items())
            if s
        ]
        result.append(
            StatisticSeries(
                _metadata(
                    login,
                    f"language_{slug(name)}",
                    f"GitHub {login} {name} share (estimated)",
                    "%",
                ),
                points,
            )
        )
    other = [
        StatisticData(
            start=_start(key, zone),
            state=round(sum(v for n, v in s.items() if n not in top) * 100, 2),
        )
        for key, s in sorted(monthly.items())
        if s
    ]
    if top:
        result.append(
            StatisticSeries(
                _metadata(
                    login,
                    "language_other",
                    f"GitHub {login} other languages (estimated)",
                    "%",
                ),
                other,
            )
        )
    return result


def import_series(hass: HomeAssistant, series: list[StatisticSeries]) -> None:
    """Write the series to the recorder."""
    for item in series:
        if item.points:
            async_add_external_statistics(hass, item.metadata, item.points)
