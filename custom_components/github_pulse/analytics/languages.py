"""Estimate programming-language usage from commits and repository languages.

GitHub has no per-commit language data. The estimate distributes each
repository's commits over its languages in proportion to their byte share.
Both weightings are kept so changing the option needs no refetch. Pure and
free of Home Assistant imports.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

COMMIT_CAP = 100
OTHER = "Other"


@dataclass(frozen=True, slots=True)
class RepoActivity:
    """One repository's commits in a period and its language bytes."""

    commits: int
    languages: Mapping[str, int]


@dataclass(frozen=True, slots=True)
class LanguageMonth:
    """Raw language scores of a period, ready to be combined and normalised."""

    commit_scores: Mapping[str, float]
    repo_scores: Mapping[str, float]
    unclassified_commits: int
    repositories: int
    truncated: bool


EMPTY = LanguageMonth({}, {}, 0, 0, truncated=False)


def estimate_month(
    repos: Sequence[RepoActivity], cap: int = COMMIT_CAP
) -> LanguageMonth:
    """Estimate one period.

    Repositories without commits are ignored. Repositories without language
    bytes (empty, or languages the token cannot read) add their commits to
    ``unclassified_commits``. ``truncated`` is set when the list reached the
    API cap, so repositories beyond it are missing.
    """
    commit_scores: dict[str, float] = defaultdict(float)
    repo_scores: dict[str, float] = defaultdict(float)
    unclassified = 0
    counted = 0
    for repo in repos:
        if repo.commits <= 0:
            continue
        counted += 1
        total_bytes = sum(size for size in repo.languages.values() if size > 0)
        if total_bytes == 0:
            unclassified += repo.commits
            continue
        for name, size in repo.languages.items():
            if size <= 0:
                continue
            share = size / total_bytes
            commit_scores[name] += repo.commits * share
            repo_scores[name] += share
    return LanguageMonth(
        dict(commit_scores),
        dict(repo_scores),
        unclassified,
        counted,
        truncated=len(repos) >= cap,
    )


def combine(months: Iterable[LanguageMonth]) -> LanguageMonth:
    """Add up raw scores of several periods."""
    commit_scores: dict[str, float] = defaultdict(float)
    repo_scores: dict[str, float] = defaultdict(float)
    unclassified = repositories = 0
    truncated = False
    for month in months:
        for name, score in month.commit_scores.items():
            commit_scores[name] += score
        for name, score in month.repo_scores.items():
            repo_scores[name] += score
        unclassified += month.unclassified_commits
        repositories += month.repositories
        truncated = truncated or month.truncated
    return LanguageMonth(
        dict(commit_scores),
        dict(repo_scores),
        unclassified,
        repositories,
        truncated=truncated,
    )


def shares(
    month: LanguageMonth, *, by_commits: bool, top: int | None = None
) -> dict[str, float]:
    """Return language shares as fractions summing to 1, largest first.

    With ``top`` set, languages beyond the first ``top`` are merged into
    ``"Other"``. An empty period returns an empty dict.
    """
    scores = month.commit_scores if by_commits else month.repo_scores
    total = sum(scores.values())
    if total == 0:
        return {}
    ranked = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    result = {name: score / total for name, score in ranked}
    if top is None or len(result) <= top:
        return result
    kept = dict(list(result.items())[:top])
    kept[OTHER] = sum(list(result.values())[top:])
    return kept


def shift(
    current: Mapping[str, float], previous: Mapping[str, float]
) -> dict[str, float]:
    """Return each language's change in percentage points, biggest gain first."""
    names = current.keys() | previous.keys()
    changes = {
        name: (current.get(name, 0.0) - previous.get(name, 0.0)) * 100 for name in names
    }
    return dict(sorted(changes.items(), key=lambda item: (-item[1], item[0])))
