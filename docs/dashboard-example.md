# Dashboard example

GitHub Pulse can write its monthly history to Home Assistant's long-term statistics. The standard **statistics graph** card then draws trends without any custom card.

## 1. Turn the import on

Open **Settings → Devices & services → GitHub Pulse → Configure** and enable **Import monthly history as statistics**. The import runs with the next refresh and fills the whole history depth you configured.

## 2. Find your statistic IDs

The IDs are built from your GitHub login in lower case, with every character that is not a letter or digit replaced by `_`. For the login `octocat`:

| Statistic | ID |
| --- | --- |
| Commits per month | `github_pulse:octocat_commits` |
| Contributions per month | `github_pulse:octocat_contributions` |
| Share of a language (%) | `github_pulse:octocat_language_php` |
| Everything outside the top languages (%) | `github_pulse:octocat_language_other` |

Language IDs use a simple slug of the language name: `C++` becomes `cplusplus`, `C#` becomes `csharp`, `Jupyter Notebook` becomes `jupyter_notebook`. The eight most used languages get a series each. You can check the exact IDs under **Developer tools → Statistics**.

> [!NOTE]
> Language shares are **estimated** from your commits and each repository's language mix, not measured per commit.

## 3. Add the cards

```yaml
type: vertical-stack
cards:
  - type: statistics-graph
    title: Commits per month
    chart_type: bar
    period: month
    days_to_show: 1095
    stat_types:
      - state
    entities:
      - github_pulse:octocat_commits
  - type: statistics-graph
    title: Language shares (estimated)
    chart_type: bar
    period: month
    days_to_show: 1095
    stat_types:
      - state
    entities:
      - github_pulse:octocat_language_php
      - github_pulse:octocat_language_go
      - github_pulse:octocat_language_javascript
      - github_pulse:octocat_language_other
```

Replace `octocat` and the languages with your own. `days_to_show: 1095` shows three years, matching the default history depth.

## 4. Use the raw data in scripts

The service `github_pulse.get_history` returns the same series as a response, for automations or templates:

```yaml
action: github_pulse.get_history
data:
  start: "2025-01"
  end: "2026-10"
response_variable: history
```
