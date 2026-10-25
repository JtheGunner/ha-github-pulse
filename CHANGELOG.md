# Changelog

All notable changes to this project are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses [Semantic Versioning](https://semver.org/).

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
