# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- Automation blueprints for failed workflow runs and review requests.
- Custom queries: add your own read-only GraphQL query as a sensor. Queries are validated (single `query`, cost cap, minimum interval), test-run before saving, and rendered with templates over `value_json`.
- Optional rhythm sensors: most active hour and night-owl score, labelled approximate.
- Optional work-in-progress sensors: average time to merge and stale pull requests.
- Year in review: service `github_pulse.year_in_review` and an optional text sensor.
- German translation.
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
