<div align="center">

# 📈 GitHub Pulse

**Your GitHub activity, inside Home Assistant.**

<code>GitHub API</code> &nbsp;→&nbsp; <code>sensors, events & history</code> &nbsp;→&nbsp; <code>dashboards & automations</code>

[![License](https://img.shields.io/badge/license-MIT-22c55e?style=flat-square)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.14-3776ab?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![Home Assistant](https://img.shields.io/badge/home%20assistant-2026.9%2B-0ea5e9?style=flat-square&logo=homeassistant&logoColor=white)](https://www.home-assistant.io/)
[![HACS](https://img.shields.io/badge/HACS-custom-8b5cf6?style=flat-square)](https://hacs.xyz/)
[![Status](https://img.shields.io/badge/status-in%20development-f59e0b?style=flat-square)](#-status)

</div>

---

## 🎯 What it is

GitHub Pulse turns your GitHub account into Home Assistant entities. It looks at the whole account, not only a single repository:

- 📊 commits and pull requests this month, compared with last month and last year
- 🗓️ your busiest month, contribution streaks and weekday rhythm
- 🧑‍💻 the programming languages you use most, and how that changed over time (an estimate, see below)
- 📦 per-repository stats, releases and CI state
- 🔧 your own GraphQL queries as sensors

You choose which parts to enable. That also decides which access token permissions you need.

---

## 🚧 Status

The integration is under development and not yet installable. See [`docs/concept-and-plan.md`](docs/concept-and-plan.md) for the design and roadmap.

---

## 🧩 Design at a glance

| | Part | Purpose |
| --- | --- | --- |
| 👤 | Profile | Account-wide activity and history |
| 📁 | Repositories | Per-repository stats and CI state |
| ⚙️ | Actions | Workflow runs and failure rates |
| 🔧 | Custom queries | Your own read-only GraphQL queries |

> [!NOTE]
> Language statistics are **estimated**: GitHub provides language data per repository, not per commit. The estimate weights your commits by each repository's language mix.

---

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

## 📄 License

Released under the [MIT License](LICENSE).

<div align="center"><sub>Built for Home Assistant · data from the GitHub API</sub></div>
