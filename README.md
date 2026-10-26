<div align="center">

# 📈 GitHub Pulse

**Your GitHub activity, inside Home Assistant.**

<code>GitHub API</code> &nbsp;→&nbsp; <code>sensors, events & history</code> &nbsp;→&nbsp; <code>dashboards & automations</code>

[![License](https://img.shields.io/badge/license-MIT-22c55e?style=flat-square)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.14-3776ab?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![Home Assistant](https://img.shields.io/badge/home%20assistant-2026.9%2B-0ea5e9?style=flat-square&logo=homeassistant&logoColor=white)](https://www.home-assistant.io/)
[![HACS](https://img.shields.io/badge/HACS-custom-8b5cf6?style=flat-square)](https://hacs.xyz/)
[![Status](https://img.shields.io/badge/status-stable-22c55e?style=flat-square)](CHANGELOG.md)

</div>

---

## 🎯 What it is

GitHub Pulse turns your GitHub account into Home Assistant entities. It looks at the whole account, not only a single repository:

- 📊 commits and pull requests this month, compared with last month and last year
- 🗓️ your busiest month, contribution streaks and weekday rhythm
- 🧑‍💻 the programming languages you use most, and how that changed over time (an estimate, see below)
- 📦 per-repository stats, releases, CI state and workflow runs
- 🔔 events for failed workflows, new releases and review requests
- 🔧 your own GraphQL queries as sensors

You choose which parts to enable. That also decides which access token permissions you need.

---

## 📥 Installation

1. In HACS, open the menu → **Custom repositories**, add `https://github.com/JtheGunner/ha-github-pulse` as an **Integration**.
2. Install **GitHub Pulse** and restart Home Assistant.
3. Go to **Settings → Devices & services → Add integration → GitHub Pulse**.
4. Paste a personal access token and choose the modules you want.
5. Use **Add repository** to pick one or more repositories from a list of those your token can read, or type `owner/name`.

Requires Home Assistant 2026.9 or newer.

---

## 🔑 Access token

You need **one** token. It serves every module you enable. A classic token with `repo` and `read:org` covers everything; the table shows the minimum per module.

| Module | Classic token | Fine-grained token |
| --- | --- | --- |
| 👤 Profile | no scope for public activity; `repo` + `read:org` adds private repositories | Metadata read, one owner only |
| 📁 Repositories | `repo` for private repositories | Metadata, Contents, Issues, Pull requests (read); Actions read if you track workflow runs |

The setup checks the token against every module you select and tells you what is missing. The full endpoint list is in the [permission matrix](docs/permission-matrix.md).

> [!IMPORTANT]
> Fine-grained tokens belong to a single owner and cannot read Packages. Use a classic token if you need more.

---

## 🧩 What you get

| | Part | Entities |
| --- | --- | --- |
| 👤 | Profile | Contributions, commits and pull requests this month; change versus last month and last year (like for like); busiest month; current and longest streak; top language and language shift (estimated) |
| 📁 | Repositories | One device per repository: stars, forks, open issues and pull requests, latest release, CI state of the default branch; commits and active days this month and the change versus last month and last year (like for like); pull requests and issues created this month; all counting every author |
| ⚙️ | Workflow runs | Per repository, if you turn on **Track workflow runs**: last result, runs today, queued runs, failure rate over 7 and 30 days, average duration, and a binary sensor while a workflow runs |
| 🔔 | Events | Event entities per repository (workflow failed or recovered, release published) and for your account (review requested, pull request merged), also fired on the event bus |
| 🧪 | Custom queries | Your own read-only GraphQL query as a sensor, added under **Add custom query**. Rendered with templates over `value_json`. Presets included; see the [guide](docs/custom-queries.md) |
| ➕ | Optional sensors | Reviews, issues, active days, strongest weekday, watchers, release downloads, days since last commit or release, pull requests awaiting your review, most active hour and night-owl score (approximate, from GitHub's last 300 events), average time to merge (last 50 merged pull requests), stale pull requests (open, untouched for 14 days), year in review (one-line summary with the details as attributes) |

Everything marked optional is created disabled. GitHub Pulse only fetches data that an enabled entity needs, so unused sensors cost no API calls.

### 🛎️ Services

| Service | Purpose |
| --- | --- |
| `github_pulse.get_history` | Returns the monthly series and language shares as a response, for scripts and templates |
| `github_pulse.year_in_review` | Returns contributions, busiest month, top language (estimated) and longest streak of a year, with a one-line summary |
| `github_pulse.query` | Runs a read-only GraphQL query and returns its `data`, `errors` and `cost`. Same validation and rate budget as custom query sensors; 30 s timeout, 200 kB result limit |

### 📣 Events

Each event is also fired on the Home Assistant event bus, so any automation can react to it.

| Event type | Fired when | Data |
| --- | --- | --- |
| `github_pulse_workflow_failed` | A workflow run of a tracked repository fails | `repository`, `workflow`, `branch`, `run_id`, `conclusion`, `url` |
| `github_pulse_workflow_recovered` | The first run succeeds after a failure | same as above |
| `github_pulse_release_published` | A tracked repository publishes a release | `repository`, `tag`, `name`, `url`, `prerelease` |
| `github_pulse_review_requested` | Someone asks you to review a pull request | `repository`, `number`, `title`, `url` |
| `github_pulse_pr_merged` | One of your pull requests is merged | `repository`, `number`, `title`, `url` |

History is never announced: on a fresh install the current state is only remembered.

### 🔧 Options

History depth (1 to 10 years, default 3), refresh intervals, contribution time zone, whether to include restricted contributions, language weighting, and an opt-in import of the monthly history into long-term statistics.

> [!TIP]
> Charts for commits and language shares need no custom card: see the [dashboard example](docs/dashboard-example.md).

> [!NOTE]
> Why do totals differ from github.com, and why are some counts "restricted"? See [visible and restricted contributions](docs/contributions.md).

> [!NOTE]
> Language statistics are **estimated**: GitHub provides language data per repository, not per commit. The estimate weights your commits by each repository's language mix.

---

## 🧩 Blueprints

Two automation blueprints ship in [`blueprints/automation/github_pulse`](blueprints/automation/github_pulse). Copy them to `config/blueprints/automation/github_pulse/` and create automations from them.

| | Blueprint | Fires on |
|---|---|---|
| 🔴 | `ci_failed.yaml` | `github_pulse_workflow_failed`, optionally filtered by repository and branch |
| 👀 | `review_requested.yaml` | `github_pulse_review_requested`, optionally filtered by repository |

---

## 🗺️ Roadmap

Possible next steps: more presets for custom queries. A Packages module is not planned: GitHub's API returns package names and versions but no download counts. See [`docs/concept-and-plan.md`](docs/concept-and-plan.md).

---

## 🤝 Contributing

Issues and pull requests are welcome. See [`CONTRIBUTING.md`](CONTRIBUTING.md) for the project layout, conventions and the pull request process. Every behaviour change needs a test.

## 🛠️ Development

Requires Python 3.14 and [`uv`](https://docs.astral.sh/uv/).

```bash
uv venv --python 3.14 .venv
uv pip install --python .venv/bin/python -r requirements_test.txt
.venv/bin/ruff check . && .venv/bin/ruff format --check .
.venv/bin/mypy custom_components
.venv/bin/pytest
```

---

## 📜 Changelog

See [`CHANGELOG.md`](CHANGELOG.md).

---

## 📄 License

Released under the [MIT License](LICENSE).

<div align="center"><sub>Built for Home Assistant · data from the GitHub API</sub></div>
