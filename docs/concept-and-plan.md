# Concept & implementation plan — GitHub activity integration for Home Assistant

Name: **GitHub Pulse** (integration domain `github_pulse`). Repository: [`JtheGunner/ha-github-pulse`](https://github.com/JtheGunner/ha-github-pulse). Task tracker: YouTrack project `HGP`.

Status: concept, not yet implemented. Nothing in this document has been built.

---

## 1. Verdict

| Question | Answer |
| --- | --- |
| Is the idea feasible? | **Yes.** Every metric on the wish list can be obtained from the GitHub GraphQL/REST API with a PAT. Two items are only approximations (language usage over time, Packages downloads); both are flagged below. |
| Does it make sense for Home Assistant? | **Yes**, with one reframing: HA sensors hold *one* value. History questions ("how did my language use change?") need HA long-term statistics and service responses on top of sensors. |
| Fork or new project? | **New project.** Borrow patterns and, where useful, code from `ReikanYsora/github-insights` (MIT, with attribution). See [section 3](#3-fork-or-new-project). |
| Biggest risk | Token permissions: what a user *sees* depends on the token (private contributions, orgs, packages). The design makes this explicit instead of hiding it. |

---

## 2. Verified facts

Everything marked ✅ was tested against the live GitHub API with a classic token (`repo`, `read:org`, `workflow`, `gist`) in October 2026. Items marked ⚠️ are documented or inferred and **must be confirmed in Phase 0**.

| # | Fact | Consequence for the design |
| --- | --- | --- |
| 1 | ✅ `contributionsCollection(from,to)` returns commit / PR / review / issue / repository contribution totals and a per-day calendar. | Core of the profile module. |
| 2 | ✅ A single window may span **at most 1 year** (API validation error otherwise). | History is fetched in ≤1-year windows. |
| 3 | ✅ Many `contributionsCollection` aliases fit in **one** request; 12 monthly windows cost **1 point**. | A multi-year backfill is cheap. |
| 4 | ✅ Contributions to private repos the token cannot see appear only as `restrictedContributionsCount`. On the test account, most months showed 0 visible commits but hundreds of restricted contributions. | Expose visible and restricted counts separately; never silently mix them. Document how to make more contributions visible. |
| 5 | ✅ `commitContributionsByRepository` returns per-repo commit counts and each repo's `languages` (bytes) in one 1-point request. | Basis for the language estimate. |
| 6 | ✅ `rateLimit(dryRun: true)` returns a query's cost without executing it. | Custom queries can be cost-checked at configuration time. |
| 7 | ✅ REST requests answered with `304 Not Modified` (via `If-None-Match`) do **not** consume rate limit. | ETag caching makes REST polling effectively free. |
| 8 | ✅ `GET /users/{login}/events` returns up to 300 events (3 pages) with timestamps. | Enables "most active hour / night owl" without commit-level calls. |
| 9 | ✅ Search `is:pr is:open review-requested:@me` works (30 req/min, separate budget). | "Review requested" sensor and event. |
| 10 | ✅ `GET /user/packages` needs the classic `read:packages` scope; the billing endpoints need the `user` scope. | Packages and billing are optional, off by default. |
| 11 | ✅ Repo traffic (views/clones) works when the token has push access. | Optional repo sensor. |
| 12 | ✅ Fine-grained PATs: one resource owner only, no access to multiple organizations at once, **no Packages**, no Checks API (GitHub docs, `managing-your-personal-access-tokens`). | The token guidance must offer classic PATs for cross-org/profile use. |
| 13 | ⚠️ Which exact fine-grained permissions each module needs (e.g. traffic → Administration read?). | Phase 0 builds a probe-based permission matrix. |
| 14 | ⚠️ Whether the contribution calendar buckets days in UTC or the profile timezone. | Phase 0; default to UTC to match github.com. |
| 15 | ⚠️ Whether GraphQL `PackageVersion` exposes usable download statistics. | Packages stays experimental until proven. |
| 16 | ⚠️ HA reloads the entry when a disabled entity is enabled (needed for demand-based fetching, see 6.4). | Phase 0 test with the HA test harness. |
| 17 | ⚠️ HA recorder statistics API changed in late 2025 (`unit_class`, `mean_type`). | Code against the current API; pin the minimum HA version. |

Not fabricated: no number above comes from memory. The restricted-contribution observation is specific to the test account and is used only to justify the design.

---

## 3. Fork or new project?

Reference: [`ReikanYsora/github-insights`](https://github.com/ReikanYsora/github-insights) — MIT, created 2026-07-03, one release, 0 stars, 0 forks, ~40 KB of code excluding ~70 machine-style translation files.

| Aspect | Reference project | Our target | Fork helps? |
| --- | --- | --- | --- |
| Data layer | REST only, flat `RepositoryInsights` dataclass | GraphQL-first, several data domains, history store | No — rewritten |
| Scope | One repo per config entry | Account-wide + many repos + custom queries | No — different entry model (entry + subentries) |
| Entity model | 9 static sensors, one description tuple | Dozens of sensors across modules, demand-based fetching | Pattern only |
| Domain | `github_insights` | must differ | **A fork keeping the domain collides with the original if both are installed** |
| Community | None to inherit | — | No benefit |
| Upstream merges | — | Diverged from day one | Would be impossible |
| Code quality | Good: typed, `runtime_data`, reauth, options flow, tests | — | Worth learning from |

**Decision: new repository, new domain.** Reuse, with the MIT notice preserved for anything copied verbatim:

- the `Link`-header trick to count commits with one request,
- the typed error taxonomy (auth / not found / rate limit),
- the reauth and validation flow shape,
- the test layout (`conftest`, API tests, config-flow tests).

Add a credit line in the README. Optionally open an issue upstream to say a broader project exists; no obligation.

Counter-argument considered: a fork gives a quicker start. Rejected, because the start is not the bottleneck (the reusable part is under 300 lines) and a fork would inherit a data model we would delete.

---

## 4. My own ideas (independent of the original wish list)

What I would want from this integration, beyond statistics:

**Make it an automation tool, not only a dashboard**

1. **HA events + `event` entities** for `workflow_failed`, `release_published`, `review_requested`, `pr_merged`. This is what makes the integration genuinely "Home Assistant": a light turns red when CI fails, a speaker announces a review request.
2. **Build-light mode:** one sensor per repo with a clean state (`passing`, `failing`, `running`) for tri-colour lights.
4. **Blueprints** for CI failure and review requests, shipped in the repo.

**Better insight than a count**

5. **Like-for-like comparisons.** "+12 % vs. last month" is misleading on the 10th of a month. Default to month-to-date vs. the same number of days in the previous month; expose the full-month comparison as an attribute.
6. **Rhythm sensors:** most productive weekday (from the calendar), most active hour and "night owl score" (from the events API, labelled approximate).
7. **Work-in-progress sensors:** open PRs awaiting my review, my PRs awaiting review, average time to merge (last 50 PRs).
8. **Repo health:** latest default-branch CI state, days since last commit/release, stale PR count, Dependabot alert count (permission-gated), stars gained in the last 7 days.
9. **Year in review** as a service with a response (and a text sensor): top language, busiest month, longest streak, total contributions. Also a natural target for HA Assist ("how many commits this month?").

**Platform-native extras**

10. **Long-term statistics import** for monthly commits and language shares, so the standard `statistics-graph` card can draw history and trends without a custom card.
11. **Diagnostic sensors** for API budget (`rate_limit_remaining`, last successful refresh) — important when the user adds custom queries.
12. **Stretch:** webhook receiver for real-time events, organization mode, Sponsors, notifications count (classic token only), a contribution-heatmap card as a separate project.

---

## 5. Merging both idea sets — conflicts and resolutions

| # | Tension | Resolution |
| --- | --- | --- |
| 1 | **Repo-only users vs. account-wide stats.** A repo-only user must not be forced to grant profile access. | Modules are opt-in during setup; each module lists the permissions it needs; a probe verifies the token before the entry is created. |
| 2 | **"Many defaults out of the box" vs. entity flood and rate limit.** | Few entities enabled by default; the rest are `entity_registry_enabled_default=False`. Data groups are fetched only if an enabled entity needs them (see 6.4). |
| 3 | **"Language over time" (programming languages such as PHP, Bash, Go) vs. API reality.** GitHub has no per-commit language data. | Estimate: per period, `Σ repos (commits in repo × repo language byte share)`. Labelled `estimated` in an attribute and in the docs. Exact per-commit analysis is a possible later opt-in; it costs one API call per commit. |
| 4 | **Single-value sensors vs. history questions.** | Sensors hold the headline value; history goes to imported statistics (graphs) and a service response (raw data). |
| 5 | **Percent change vs. unfair partial periods; zero baseline.** | Like-for-like default; if the baseline is 0 the state is `unknown` (never ∞), the absolute values stay in attributes. |
| 6 | **Visible vs. restricted contributions** make month-to-month comparisons noisy (a token change flips counts). | Two sets of sensors/attributes: `visible` and `all (incl. restricted)`. Percent comparisons use the same set on both sides. |
| 7 | **Flexibility (custom queries) vs. safety and budget.** | Queries only, never mutations (parsed, not regexed); cost-checked with `dryRun`; cost-based minimum interval; shared rate-limit budget. |
| 8 | **Least-privilege PAT vs. cross-org/packages needs.** | Fine-grained PATs cannot do multi-org or Packages (fact 12). The permission matrix recommends fine-grained for repo-only setups and classic for profile/org/packages. Not hideable; documented prominently. |
| 9 | **Contribution commits ≠ repo commit count.** Contributions count default-branch commits authored by the user only. | Name the sensors accordingly ("Commits (contributions)" vs. repo "Commits on default branch") and explain in the docs. |
| 10 | **`commitContributionsByRepository` caps at 100 repos.** Heavy contributors would get truncated language shares. | Query per month (each window has far fewer than 100 repos); flag `truncated: true` if a window hits the cap. |
| 11 | **Large attributes** (calendars, language histories) bloat the recorder DB. | Mark big attributes with `_unrecorded_attributes`; deliver bulk data via service responses. |
| 12 | **Domain collision** if the new project reused `github_insights`. | New domain. |

No contradiction is unresolvable. The two genuine limitations (language history is an estimate; Packages is token-limited) are visible to the user instead of hidden.

---

## 6. Architecture

### 6.1 Entry model

```text
Config entry  = one token + one owner login (user or organization)
  data:    access_token, owner, token_type (detected), enabled modules
  options: update intervals, include-restricted switch, language weighting mode

  Subentries
    ├─ repository   (one per tracked repo; add/remove without re-entering the token)
    └─ custom_query (one per user-defined sensor)
```

Config subentries let repositories and custom queries be added and removed independently. A second token (e.g. a work account) is a second entry.

### 6.2 Modules

| Module | Scope | Typical token needs |
| --- | --- | --- |
| **Profile** | contributions, PRs, comparisons, history, languages, rhythm | classic: none for public, `repo`+`read:org` for private; fine-grained: Metadata read |
| **Repositories** | per-repo stats, releases, CI state | fine-grained: Metadata, Contents, Issues, Pull requests read |
| **Actions** | workflow runs and failure rates | fine-grained: Actions read |
| **Packages** (experimental) | package/version listing | classic `read:packages` only |
| **Custom queries** | user-defined GraphQL | whatever the query touches |

The exact matrix is generated in Phase 0 from probes, not guessed.

### 6.3 Layers

```text
┌──────────────────────────────────────────────────────────────┐
│ Entities (sensor / binary_sensor / event)  ←  Services       │  HA-specific
├──────────────────────────────────────────────────────────────┤
│ Coordinators (per module, own interval) + shared RateBudget  │  HA-specific
├──────────────────────────────────────────────────────────────┤
│ History store (HA Store: closed months, language data)       │  HA-specific
├──────────────────────────────────────────────────────────────┤
│ Analytics (pure functions: comparisons, streaks, languages)  │  NO HA imports
├──────────────────────────────────────────────────────────────┤
│ API client (GraphQL + REST, ETag cache, retry, error types)  │  NO HA imports
└──────────────────────────────────────────────────────────────┘
```

The two bottom layers have no Home Assistant imports, so they are tested with plain pytest and fixtures. All statistics logic lives there.

### 6.4 Key mechanisms

- **Rate budget.** One object per entry reads `rateLimit` / `X-RateLimit-*`. Below a threshold (default 10 % remaining) coordinators lengthen their interval. Exposed as a diagnostic sensor. Search API (30/min) is tracked separately.
- **ETag cache** for all REST GETs; 304s are free (fact 7).
- **Demand-based fetching.** Each entity description declares a `data_group`. At setup, a coordinator fetches only groups with at least one enabled entity. Enabling a disabled entity reloads the entry (verify, fact 16).
- **History store.** Closed months are immutable in practice, so they are cached in an HA `Store` and survive restarts. Because backdated commits and newly linked e-mail addresses can change old months, refresh the last 2 months daily and older months weekly. First run backfills up to N years (default 3, configurable in the options flow) using yearly windows with monthly aliases.
- **Intervals (defaults).** Profile current period 15 min; history daily; repos 15 min; Actions 5 min; Packages 1 h; events API 30 min.
- **Time handling.** Month boundaries computed in UTC to match github.com (verify, fact 14). The comparison functions take explicit period arguments so a timezone switch is a one-line change.
- **Error handling.** Auth errors → reauth flow; rate limit / 5xx → `UpdateFailed` with backoff and `Retry-After`; partial failures keep the last good data per group instead of failing the whole coordinator.

### 6.5 Custom queries

Layered, familiar to HA users:

1. **Custom query subentry.** Fields: name, GraphQL query (or REST path), variables, interval, **value template** (Jinja with `value_json`, like the REST integration), optional **attributes template**, unit, device class, state class.
2. **Variable helpers** so queries stay valid over time: `{{ start_of_month }}`, `{{ end_of_month }}`, `{{ start_of_year }}`, `{{ one_year_ago }}`, `{{ owner }}`.
3. **Validation in the flow:** parse with `graphql-core` and reject anything but `query`; run `rateLimit(dryRun: true)` to show the cost; refuse queries above a cost cap; derive the minimum allowed interval from cost; offer a test run that shows the raw result and the rendered state.
4. **Service `github_pulse.query`** with `SupportsResponse.ONLY` for scripts/automations and ad-hoc exploration; same validation, same budget.
5. **Preset library** (docs + a "start from preset" dropdown): the shipped examples demonstrate the engine.

Built-in sensors stay as code, not as presets: they need computed values (comparisons, streaks) that a template engine should not be forced to express. Custom queries are the escape hatch, not the foundation.

State limit reminder: an HA state is at most 255 characters; larger results belong in attributes, and attributes that are large get `_unrecorded_attributes`.

---

## 7. Default entity catalog

"Default" = enabled right after setup. Everything else is created disabled.

### Profile

| Sensor | Default | Notes |
| --- | --- | --- |
| Contributions this month (visible / all) | ✅ | Calendar total vs. visible types |
| Commits this month | ✅ | `totalCommitContributions` |
| Pull requests this month | ✅ | opened |
| Commits vs. last month (%) | ✅ | like-for-like; full-month in attribute |
| Commits vs. same month last year (%) | ✅ | like-for-like |
| Busiest month this year | ✅ | state `2026-03`, attributes count + name |
| Top language (this year) | ✅ | attributes: ranking, shares, `method: estimated` |
| Current / longest streak | ✅ | days (plain statistic, no reminder logic) |
| Contributions this week / year | – | |
| Language shift vs. last year | – | top gainer / loser in percentage points |
| Reviews this month, issues this month | – | |
| Active days this month | – | |
| Most productive weekday | – | |
| Most active hour, night-owl score | – | events API, approximate |
| Review requested (count), my open PRs | – | search API |
| Average time to merge | – | last 50 PRs |
| Followers, following, public repos, total stars | – | |
| Year-in-review text | – | |

### Repository (per subentry)

| Sensor | Default |
| --- | --- |
| Stars, forks, open issues, open PRs | ✅ |
| Latest release (tag, URL) | ✅ |
| Default-branch CI state | ✅ |
| Latest release downloads, total downloads | – |
| Commits on default branch | – |
| Days since last commit / release | – |
| Stars gained (7 d), watchers | – |
| Stale PRs, Dependabot alerts, traffic (views/clones) | – (permission-gated) |

### Actions (per repository or account-wide)

Last run result, running now (binary), runs today, failure rate 7 d / 30 d, average duration, queued runs. Billing minutes: optional, classic `user` scope, off by default.

### Events and services

Events: `workflow_failed`, `workflow_recovered`, `release_published`, `review_requested`, `pr_merged`.
Services: `query` (response), `refresh`, `get_history` (response: monthly series, language series), `year_in_review` (response).

### Statistics imported (external, opt-in)

Monthly commits/contributions and language share per month for the top languages plus "other".

---

## 8. Implementation plan

Conventions for every phase: code, identifiers, comments and docs in English; user-facing strings in `en` and `de`; every behaviour change ships with a test; run formatter, linter and the relevant tests before calling a task done.

### Phase 0 — Spikes and decisions (≈2 days)

Goal: replace every ⚠️ in section 2 with a verified fact.

| Task | Output |
| --- | --- |
| Probe every endpoint/query used with a classic token, a fine-grained token (own repos), and an unauthenticated call | `docs/permission-matrix.md`, generated by a script, not typed by hand |
| Confirm calendar timezone behaviour and the restricted-contribution rules | note in `docs/api-findings.md` |
| Test `PackageVersion` statistics availability | go/no-go for the Packages module |
| Spike in a throwaway HA test harness: enabling a disabled entity reloads the entry; subentry flow; `async_import_statistics` with the current signature; `SupportsResponse.ONLY` | go/no-go for demand-based fetching and statistics import |
| Decide name/domain, minimum HA version, license | recorded in [Open decisions](#12-open-decisions) |

Acceptance: no ⚠️ left, or each remaining one has a documented fallback.

### Phase 1 — Foundation (≈3–4 days)

1. Repo scaffold: `custom_components/<domain>/`, `hacs.json`, `manifest.json`, `pyproject.toml` (ruff, mypy), `LICENSE`, `README.md` skeleton, `.gitignore`.
2. CI: hassfest, HACS validation, ruff, mypy, pytest with `pytest-homeassistant-custom-component`.
3. API client: GraphQL + REST, ETag cache, retry/backoff, typed errors, `RateBudget`. Tests with recorded JSON fixtures.
4. Config flow: token → owner detection → module selection with per-module permission hints → probe → entry. Reauth and reconfigure. Diagnostics with token redaction.
5. Coordinator base class with partial-failure handling and demand-based group registry.

Acceptance: an entry can be created with a real token, module probe results are shown, a no-op coordinator refreshes and reports the rate budget.

### Phase 2 — Profile module, vertical slice (≈4–5 days)

1. Analytics: period math (month-to-date, like-for-like), comparison with zero baseline handling, busiest month, streaks, weekday pattern. **Test-first**, pure functions, edge cases: month boundaries, leap years, empty history, ties, restricted vs. visible.
2. Profile coordinator: current period, history backfill via yearly windows with monthly aliases, `Store` persistence, refresh policy for recent vs. old months.
3. Sensors from the default catalog.
4. Docs for the "visible vs. restricted" behaviour.

Acceptance: default Profile sensors appear and match github.com for a known account; restart does not refetch closed months; comparisons verified against hand-calculated fixtures.

### Phase 3 — Languages (≈3 days)

1. Language estimator (commits × byte share per repo per month), configurable weighting (`commit-weighted`, `repo-count`), "other" bucket, cap-hit flag.
2. Sensors: top language, language shift. Attributes marked estimated.
3. Statistics import (monthly commits, language shares) and `get_history` service. Guarded behind the Phase 0 go/no-go.
4. Dashboard example using `statistics-graph`.

Acceptance: stacked history graph of language shares for the backfilled period renders in a standard card.

### Phase 4 — Repository module (≈4 days)

1. Repo subentry flow (validate `owner/name`, duplicate check, per-repo permission check).
2. One batched GraphQL request for all tracked repos; REST + ETag for release assets and anything GraphQL lacks.
3. Default and optional repo sensors; device per repo.
4. Search-API sensors (review requested, my open PRs) with their own budget.

Acceptance: at least feature parity with the reference project's nine sensors, plus CI state; adding the tenth repo costs no additional GraphQL requests.

**Milestone — public beta 0.1.0** after Phase 4: README in house style, `CHANGELOG.md`, tagged release, installable through HACS custom repository.

### Phase 5 — Actions and automation layer (≈3 days)

1. Actions coordinator, run statistics, `running` binary sensors.
2. `event` entities and bus events with deduplication (store last seen run ID / release ID).
3. Blueprints: CI failed, review requested.

Acceptance: a deliberately failing workflow fires `workflow_failed` exactly once; a restart does not re-fire old events.

### Phase 6 — Custom queries (≈4 days)

1. Query engine: variable helpers, template rendering, `graphql-core` validation (query-only), `dryRun` cost check, cost-derived minimum interval.
2. Custom query subentry flow with test-run preview.
3. `query` service with response; shared budget; sandbox-like limits (timeout, result size).
4. Preset library and docs, including a "write your own query" guide.

Acceptance: a mutation is rejected; an over-budget query is rejected with the cost shown; a preset produces the same value as the equivalent built-in sensor.

### Phase 7 — Rhythm, polish, 1.0 (≈4–5 days)

1. Events-API rhythm sensors, work-in-progress sensors, year-in-review.
2. Packages module only if Phase 0 gave a go; otherwise documented as not supported.
3. `de` translation, icon/brand assets, documentation pass, `CONTRIBUTING.md`.
4. Hardening: large-account test (many repos, many orgs), rate-limit exhaustion test, token revoked mid-run, offline start.
5. Release 1.0, then consider submission to the default HACS list.

### Stretch backlog

Webhook receiver (real-time events), organization mode, Sponsors, notifications count (classic token), contribution-heatmap card, exact per-commit language analysis (opt-in).

---

### Task breakdown

Each phase is a YouTrack parent task (`HGP`); each row is a subtask. "Est." is ideal working hours. Every task has a test (or a written finding for spikes) in its definition of done.

| ID | Task | Depends on | Est. |
| --- | --- | --- | --- |
| **P0** | **Spikes and decisions** | | |
| P0-1 | Probe script and generated permission matrix (classic, fine-grained, unauthenticated) | – | 6 |
| P0-2 | Verify calendar timezone and restricted-contribution rules | – | 3 |
| P0-3 | Spike: Packages download statistics (go/no-go) | – | 2 |
| P0-4 | Spike in HA test harness: entity-enable reload, subentry flow, statistics import signature, response service | – | 6 |
| P0-5 | Spike: language-estimate accuracy against a sample of repos | – | 3 |
| P0-6 | Record findings and decide minimum HA version | P0-1..5 | 2 |
| **P1** | **Foundation** | P0 | |
| P1-1 | Repository scaffold (structure, manifest, `hacs.json`, `pyproject.toml`, LICENSE, README skeleton) | P0-6 | 3 |
| P1-2 | CI: hassfest, HACS validation, ruff, mypy, pytest | P1-1 | 3 |
| P1-3 | API client core: GraphQL + REST, typed errors | P1-1 | 6 |
| P1-4 | ETag cache, retry and backoff | P1-3 | 4 |
| P1-5 | `RateBudget` (primary, GraphQL, search) | P1-3 | 4 |
| P1-6 | Config flow: token, owner detection, module selection, permission probe | P1-3, P0-1 | 8 |
| P1-7 | Reauth, reconfigure, options flow (intervals, history depth, restricted switch) | P1-6 | 4 |
| P1-8 | Diagnostics with token redaction | P1-6 | 2 |
| P1-9 | Coordinator base class and data-group registry | P1-5 | 5 |
| **P2** | **Profile module** | P1 | |
| P2-1 | Analytics: period math, like-for-like comparison, zero baseline (test-first) | P1-1 | 6 |
| P2-2 | Analytics: busiest month, streaks, weekday pattern | P2-1 | 4 |
| P2-3 | History store and multi-year backfill with refresh policy | P1-9, P2-1 | 8 |
| P2-4 | Profile coordinator | P2-3 | 4 |
| P2-5 | Profile sensors (default catalog) | P2-2, P2-4 | 6 |
| P2-6 | Docs: visible vs. restricted contributions | P2-5 | 2 |
| **P3** | **Languages** | P2 | |
| P3-1 | Language estimator (commit-weighted and repo-count modes, "other" bucket, cap flag) | P2-3, P0-5 | 8 |
| P3-2 | Language sensors (top language, shift) | P3-1 | 4 |
| P3-3 | Statistics import adapter (monthly commits, language shares) | P3-1, P0-4 | 6 |
| P3-4 | Service `get_history` with response | P3-1 | 3 |
| P3-5 | Dashboard example with `statistics-graph` | P3-3 | 2 |
| **P4** | **Repository module and 0.1.0** | P1 | |
| P4-1 | Repository subentry flow | P1-6, P0-4 | 6 |
| P4-2 | Batched repository GraphQL plus REST/ETag for gaps | P4-1 | 8 |
| P4-3 | Repository sensors and devices | P4-2 | 6 |
| P4-4 | Search-API sensors (review requested, my open PRs) | P1-5 | 4 |
| P4-5 | Release 0.1.0: README in house style, CHANGELOG, tag, HACS install check | P2, P3, P4-1..4 | 4 |
| **P5** | **Actions and automation layer** | P4 | |
| P5-1 | Actions coordinator and sensors | P4-2 | 6 |
| P5-2 | `event` entities, bus events, deduplication store | P5-1, P4-4 | 6 |
| P5-3 | Blueprints: CI failed, review requested | P5-2 | 3 |
| **P6** | **Custom queries** | P1 | |
| P6-1 | Query engine: variable helpers and template rendering | P1-3 | 6 |
| P6-2 | Validation: query-only parse, `dryRun` cost, interval floor | P6-1, P1-5 | 6 |
| P6-3 | Custom query subentry flow with test-run preview | P6-2, P0-4 | 8 |
| P6-4 | Service `query` with response, size and timeout limits | P6-2 | 4 |
| P6-5 | Preset library and "write your own query" guide | P6-3 | 4 |
| **P7** | **Rhythm, polish, 1.0** | P4, P6 | |
| P7-1 | Rhythm sensors from the events API | P1-5 | 5 |
| P7-2 | Work-in-progress sensors (average time to merge, stale PRs) | P4-3 | 4 |
| P7-3 | Year in review (service and text sensor) | P3, P2 | 4 |
| P7-4 | Packages module (only if P0-3 is a go) | P0-3, P1-6 | 8 |
| P7-5 | German translation, brand assets | P4-5 | 4 |
| P7-6 | Hardening: large account, rate-limit exhaustion, revoked token, offline start | P5, P6 | 8 |
| P7-7 | CONTRIBUTING and documentation pass | P7-5 | 3 |
| P7-8 | Release 1.0 | all | 3 |

---

## 9. Testing and quality

| Layer | Approach |
| --- | --- |
| API client, analytics | Plain pytest, recorded fixtures (anonymised), property-style tests for period math |
| Config/subentry flows | `pytest-homeassistant-custom-component`, one test per error key |
| Coordinators | Fake client; cover partial failure, reauth, backoff |
| Entities | Snapshot of the state/attributes for a fixed fixture |
| Contract tests | A small script that re-runs the Phase 0 probes against live GitHub and diffs the permission matrix (manual, not in CI) |

Coverage target: ≥ 90 % for the two pure layers, ≥ 80 % overall. Tools: ruff, mypy, hassfest, HACS validation in CI.

Security: token only in the config entry; redacted in diagnostics and logs; custom queries are query-only; no secrets in fixtures; errors shown to users contain no tokens.

---

## 10. Effort estimate

Roughly 27–31 working days for a solo developer to reach 1.0, with a usable public beta after about 14–16 days. The estimate assumes no major surprises in Phase 0; a "no-go" on statistics import or Packages shortens the plan rather than lengthening it.

---

## 11. Risks

| Risk | Likelihood | Impact | Mitigation |
| --- | --- | --- | --- |
| Restricted contributions confuse users | High | Medium | Separate sensors, documentation, config-flow hint |
| HA statistics API changes again | Medium | Medium | Isolate behind one adapter; pin the minimum HA version; feature can be disabled |
| Language estimate misread as exact | Medium | Low | `estimated` attribute and docs; labelled in names where space allows |
| Custom queries exhaust the rate limit | Medium | Medium | `dryRun` cost, interval floor, shared budget, diagnostic sensor |
| Demand-based fetching does not behave as assumed | Low–Medium | Low | Fallback: fetch all groups, rely on cheap batching |
| GitHub API shape changes | Low | Medium | Pinned `X-GitHub-Api-Version`, contract script |
| Scope creep | High | High | The phase order is the scope control; stretch items stay in the backlog |

---

## 12. Decisions

| # | Decision | Status |
| --- | --- | --- |
| 1 | Name `GitHub Pulse`, domain `github_pulse`, repository `ha-github-pulse` | decided |
| 2 | License MIT | decided |
| 3 | Public repository from the start (README, LICENSE, CHANGELOG from first release, CONTRIBUTING) | decided |
| 4 | History backfill: 3 years by default, configurable in the options flow | decided |
| 5 | Streak reminder / "contributed today" is out of scope; plain streak statistics stay | decided |
| 6 | Token advice: classic PAT for profile/org use, fine-grained for repo-only setups | proposed, confirmed by the Phase 0 permission matrix |
| 7 | Minimum HA version | open, decided in task P0-6 |

---

## 13. Self-review of this plan

I re-checked the plan against the verified facts and against how Home Assistant works. Findings and what changed:

| Finding | Fix |
| --- | --- |
| Early draft let the new integration reuse the reference domain. | Two integrations with the same domain cannot coexist. New domain. |
| "% vs. last month" was planned as full-month vs. full-month, which is wrong for a month in progress. | Month-to-date, like-for-like by default. |
| Language history planned as a single sensor. | A sensor holds one value. Moved to statistics import + service response. |
| `commitContributionsByRepository` is capped at 100 repos. | Query per month, flag when the cap is hit. |
| Calendar/attribute payloads would bloat the recorder. | `_unrecorded_attributes`, service responses for bulk data. |
| "Closed months never change" is false (backdated commits, newly linked e-mail). | Refresh the last 2 months daily and older months weekly. |
| Custom queries originally relied on a regex to block mutations. | A regex is bypassable; parse with `graphql-core`. |
| Packages looked like a safe module. | Fine-grained PATs cannot access Packages and download stats are unproven. Marked experimental with a go/no-go. |
| Several design assumptions depend on HA internals I did not verify (entity-enable reload, statistics signature). | Listed as ⚠️ and made Phase 0 gates, each with a fallback. |
| Timezone of the contribution calendar unknown. | Phase 0 item; period functions take explicit boundaries. |

Remaining weaknesses I cannot remove from here:

- The permission matrix (fact 13) is unknown until probed with a fine-grained token. Until then, per-module permission hints in the plan are directional.
- Effort figures are estimates; Phase 0 results can move them.
- The restricted-contribution behaviour was observed on one account; other accounts (fewer orgs, SSO) may differ. The design copes with either case, but the documentation wording should be checked on a second account.
