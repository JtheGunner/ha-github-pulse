# Open points

Status of the decisions collected during implementation.

| # | Topic | Status |
| --- | --- | --- |
| 1 | Initial commit on `main` | Closed. The first commit went straight to `main`; all later work uses branches and pull requests. |
| 2 | Fine-grained test token | Open, optional. A read-only fine-grained token would confirm that GraphQL contributions work with it. |
| 3, 12 | Packages module (HGP-51) | Won't fix. GitHub's REST API returns package names and versions but no download counts. |
| 4 | Local folder name | Open, cosmetic. The working copy is `ha-github-insights`, the repository is `ha-github-pulse`. |
| 5 | Contribution time zone | Closed. The owner's profile uses `Europe/Zurich`; set it as the contribution time zone in the options. The default stays `America/Los_Angeles`, which is what GitHub uses without a profile setting. |
| 6 | Language estimate evidence | Open, optional. Only two single-language repositories were measured. |
| 7 | Minimum Home Assistant 2026.9.0 | Closed. Required because HA replaced `voluptuous` by `probatio`. |
| 8 | Streaks cover 365 days | Closed. The sensor is named "Longest streak (last year)". An all-time value could come from the stored history later. |
| 9 | No live end-to-end test | Partly closed. HACS install and setup were verified by the owner; the first backfill and the repository subentry flow still need a report. |
| 10 | Actions billing minutes | Won't do. The legacy billing endpoint returns 404 and is being replaced. |
| 11 | Release 1.0.0 | Closed. Released as 1.0.0 and 1.0.1. |
| 13 | HACS default list | Open. Submit after one or two weeks of live use; the owner triggers it. |
| 14 | `graphql-core` requirement | Closed. Pinned to 3.2.6 because Home Assistant constrains it below 3.3. |
| 15 | Year in review data groups | Closed. Enabling the sensor also enables the history, language and calendar groups. |
| 16 | Rhythm and work-in-progress thresholds | Closed. They stay constants until there is concrete demand for options. |
