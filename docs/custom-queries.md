# ✍️ Custom queries

Turn any read-only GitHub GraphQL query into a sensor. Open the integration, choose **Add custom query**, pick a preset or write your own.

## How a query becomes a sensor

1. You write one GraphQL `query`.
2. GitHub Pulse runs it on your interval and keeps the `data` of the response.
3. Two templates read that data as `value_json`:
   - **State template**: must render a single value (a number or text of at most 255 characters).
   - **Attributes template** (optional): must render a mapping.

Before saving, the flow runs the query once and shows the raw result and the rendered state, so mistakes show up while you are still in the form.

## Variables

If the query declares one of these variables, GitHub Pulse fills it in on every run:

| Variable | Value |
| --- | --- |
| `$owner` | Your GitHub login |
| `$start_of_month`, `$end_of_month` | First and last second of the current month in the contribution time zone, as UTC |
| `$start_of_year` | First instant of the current year |
| `$one_year_ago` | Start of today one year ago |

Any other declared variable needs a value in the **Variables** field, written as a JSON object such as `{"first": 10}`. Variables the query does not declare are rejected.

## Templates

```jinja
{{ value_json.user.repositories.totalCount }}
```

```jinja
{{ {'login': value_json.viewer.login, 'followers': value_json.viewer.followers.totalCount} }}
```

`errors` holds partial GraphQL errors, for example from a field your token cannot see. A template that refers to something missing fails instead of silently rendering an empty value, and the sensor becomes unavailable with the reason in the log.

## Limits

| Rule | Why |
| --- | --- |
| Exactly one `query`; mutations and subscriptions are rejected | Custom queries only read. The check runs on the parsed query, so formatting tricks do not help |
| At most 50 rate-limit points per run | Checked with a `rateLimit(dryRun: true)` probe when you save |
| Minimum interval grows with cost | A query may use about 500 points per hour, and never polls faster than every 5 minutes |
| The GraphQL budget is shared | When it runs low, polling slows down for everything |

## Presets

| Preset | Matches the built-in sensor |
| --- | --- |
| Commits this month | Commits this month |
| Pull requests this month | Pull requests this month |
| Contributions this year | |
| Public repositories | |
| Followers | |

## One-off queries

The `github_pulse.query` service runs a query once and returns `data`, `errors` and `cost`. It uses the same validation and shares the rate budget, with a 30 second timeout and a 200 kB result limit.

```yaml
action: github_pulse.query
data:
  query: "query { viewer { login } }"
response_variable: result
```
