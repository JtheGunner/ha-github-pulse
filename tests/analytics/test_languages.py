"""Tests for the language estimator."""

import pytest
from custom_components.github_pulse.analytics.languages import (
    EMPTY,
    OTHER,
    LanguageMonth,
    RepoActivity,
    combine,
    estimate_month,
    shares,
    shift,
)

PHP_HEAVY = RepoActivity(10, {"PHP": 750, "Shell": 250})
GO_ONLY = RepoActivity(30, {"Go": 4000})


def test_commits_are_split_by_byte_share() -> None:
    month = estimate_month([PHP_HEAVY, GO_ONLY])

    assert month.commit_scores == pytest.approx({"PHP": 7.5, "Shell": 2.5, "Go": 30})


def test_commit_weighted_shares_follow_the_commits() -> None:
    month = estimate_month([PHP_HEAVY, GO_ONLY])

    result = shares(month, by_commits=True)

    assert list(result) == ["Go", "PHP", "Shell"]
    assert result["Go"] == pytest.approx(0.75)
    assert sum(result.values()) == pytest.approx(1)


def test_repo_count_ignores_how_many_commits_a_repo_has() -> None:
    month = estimate_month([PHP_HEAVY, GO_ONLY])

    result = shares(month, by_commits=False)

    assert result["Go"] == pytest.approx(1 / 2)
    assert result["PHP"] == pytest.approx(0.375)


def test_repositories_without_commits_are_ignored() -> None:
    month = estimate_month([RepoActivity(0, {"Rust": 100}), GO_ONLY])

    assert set(month.commit_scores) == {"Go"}
    assert month.repositories == 1


def test_zero_byte_repositories_count_as_unclassified() -> None:
    month = estimate_month([RepoActivity(5, {}), RepoActivity(2, {"Go": 0}), GO_ONLY])

    assert month.unclassified_commits == 7
    assert month.commit_scores == {"Go": 30}


def test_a_repository_list_at_the_cap_is_flagged_as_truncated() -> None:
    repos = [RepoActivity(1, {"Go": 1})] * 100

    assert estimate_month(repos).truncated
    assert not estimate_month(repos[:99]).truncated


def test_hidden_private_repositories_do_not_appear_in_the_estimate() -> None:
    # GitHub reports contributions to unreadable repositories only as a count,
    # so the estimate is built from the visible repositories alone.
    month = estimate_month([GO_ONLY])

    assert shares(month, by_commits=True) == {"Go": 1.0}


def test_an_empty_period_has_no_shares() -> None:
    assert shares(estimate_month([]), by_commits=True) == {}
    assert shares(EMPTY, by_commits=False) == {}


def test_the_tail_is_merged_into_other() -> None:
    month = estimate_month([RepoActivity(10, {"A": 50, "B": 30, "C": 15, "D": 5})])

    result = shares(month, by_commits=True, top=2)

    assert list(result) == ["A", "B", OTHER]
    assert result[OTHER] == pytest.approx(0.2)


def test_top_larger_than_the_languages_adds_no_other_bucket() -> None:
    month = estimate_month([GO_ONLY])

    assert OTHER not in shares(month, by_commits=True, top=5)


def test_ties_are_ordered_by_name() -> None:
    month = estimate_month([RepoActivity(1, {"B": 1, "A": 1})])

    assert list(shares(month, by_commits=True)) == ["A", "B"]


def test_combine_adds_raw_scores_before_normalising() -> None:
    first = estimate_month([GO_ONLY])
    second = estimate_month([RepoActivity(10, {"PHP": 1})])

    both = combine([first, second])

    assert shares(both, by_commits=True)["Go"] == pytest.approx(0.75)
    assert both.repositories == 2


def test_combine_keeps_the_truncation_flag() -> None:
    capped = LanguageMonth({}, {}, 0, 100, truncated=True)

    assert combine([EMPTY, capped]).truncated
    assert combine([]) == EMPTY


def test_shift_reports_percentage_points_biggest_gain_first() -> None:
    result = shift({"Go": 0.6, "PHP": 0.4}, {"Go": 0.2, "PHP": 0.7, "Perl": 0.1})

    assert list(result) == ["Go", "Perl", "PHP"]
    assert result["Go"] == pytest.approx(40)
    assert result["PHP"] == pytest.approx(-30)
