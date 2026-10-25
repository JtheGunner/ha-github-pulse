# Contributing to GitHub Pulse

Thanks for helping. Bug reports, ideas and pull requests are all welcome.

## 🐞 Reporting issues

Open an issue on [GitHub](https://github.com/JtheGunner/ha-github-pulse/issues) and include:

- your Home Assistant and GitHub Pulse versions
- which modules are enabled and the kind of token you use (classic or fine-grained)
- the relevant log lines (Settings → System → Logs), with tokens removed
- the diagnostics download of the integration, which redacts the token

## 🛠️ Development setup

You need Python 3.14 and [`uv`](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/JtheGunner/ha-github-pulse.git
cd ha-github-pulse
uv venv --python 3.14 .venv
uv pip install --python .venv/bin/python -r requirements_test.txt
```

Run the checks before every pull request. CI runs the same ones, plus hassfest and the HACS validation.

```bash
.venv/bin/ruff check . && .venv/bin/ruff format --check .
.venv/bin/mypy custom_components
.venv/bin/pytest
```

While iterating, run a single file, for example `.venv/bin/pytest tests/test_rhythm.py`.

## 🧭 How the code is organised

```text
custom_components/github_pulse/
├── api/          GitHub client, errors, rate budget, query validation (no Home Assistant imports)
├── analytics/    pure calculations: periods, patterns, languages, events, rhythm (no Home Assistant imports)
├── *_fetch.py    request builders and parsers for one kind of data
├── *_coordinator.py  Home Assistant coordinators, one per data source
├── sensor*.py, binary_sensor.py, event.py   entities
└── *_flow.py     config, repository and custom query flows
```

Keep `api/` and `analytics/` free of Home Assistant imports so they stay easy to test. Data is fetched in **groups**; a group is only requested while an enabled entity needs it, so a new optional sensor should declare its group and be disabled by default.

## ✅ Conventions

- Every behaviour change comes with a test. Tests use a scripted fake HTTP session (`tests/fake_http.py`), never the real GitHub API.
- Code, comments, identifiers and commit messages are in English. Only user-facing text may be translated: add every new string to `translations/en.json` and `translations/de.json` (a test keeps both in sync).
- `hassfest` rejects URLs and curly braces in translation strings; use placeholders.
- Do not add dependencies without a reason. `graphql-core` is pinned to the range Home Assistant allows.
- Update `README.md` and `CHANGELOG.md` in the same pull request when behaviour changes.

## 🔀 Pull requests

1. Branch off `main`, one topic per branch.
2. Commit messages follow `<type>: <description>` with `feat`, `fix`, `refactor`, `docs`, `test`, `chore`, `perf`, `ci` or `build`; imperative, about 72 characters.
3. Describe the whole branch in the pull request and say how you tested it.
4. CI must be green (tests, hassfest, HACS). Squash merges keep the history linear.
