# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- Adding repositories now offers a list of the most recently pushed repositories the token can read, with multi-select so several can be added at once. Typing a name still works, also when the list cannot be loaded.

### Changed

- New integration icon: a git branch-and-merge graph with a pulse ring.

### Fixed

- Adding a custom query no longer makes the account's other entities disappear. The query sensor used the account device, which Home Assistant then moved into the query's subentry. Query sensors now have no device, and an affected account device is moved back on startup. New query entities are named without the "GitHub <login>" prefix; existing entity IDs are unchanged.

## [1.0.2] - 2026-10-26

### Changed

- The longest-streak sensor is now named "Longest streak (last year)", because it covers the one-year window GitHub allows per request. Existing entity IDs are unchanged.

## [1.0.1] - 2026-10-26

### Changed

- The setup form now states that a single token serves all modules and recommends a classic token with `repo` and `read:org`.
- A classic token without the `repo` scope now gets a notice during setup that private data stays invisible, instead of passing silently.

## [1.0.0] - 2026-10-25

### Added

- Workflow run tracking per repository: last result, runs today, queued runs, failure rate over 7 and 30 days, average duration and a running indicator.
- Event entities and event-bus events for failed and recovered workflows, published releases, review requests and merged pull requests, with deduplication across restarts.
- Automation blueprints for failed workflow runs and review requests.
- Custom queries: add your own read-only GraphQL query as a sensor. Queries are validated (single `query`, cost cap, minimum interval), test-run before saving, and rendered with templates over `value_json`.
- Optional rhythm sensors: most active hour and night-owl score, labelled approximate.
- Optional work-in-progress sensors: average time to merge and stale pull requests.
- Year in review: service `github_pulse.year_in_review` and an optional text sensor.
- German translation.
- `CONTRIBUTING.md` and a documentation pass.
- Preset queries as starting points for custom queries.
- Service `github_pulse.query` to run a read-only GraphQL query and get the result as a response.

## [0.1.0] - 2026-10-25

First release.

### Added

- Config flow with token type detection, per-module permission checks, reauthentication, reconfiguration, options and diagnostics.
- Profile module: contributions, commits and pull requests this month, change versus the same span of last month and last year, busiest month, streaks, strongest weekday, optional review and issue counts.
- Monthly history store with a configurable multi-year backfill (default three years).
- Estimated language statistics (top language, shift versus last year) with commit-weighted and repository-count weighting.
- Repositories module: repositories as config subentries, one batched GraphQL request for all of them, one device each with stars, forks, issues, pull requests, latest release, CI state and optional extras.
- Search-based sensors for pull requests awaiting your review and your own open pull requests.
- Opt-in import of the monthly history into long-term statistics.
- Service `github_pulse.get_history` with a response.
