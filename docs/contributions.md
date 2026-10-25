# Visible and restricted contributions

GitHub Pulse reports two numbers for your activity and keeps them apart.

| Number | What it contains |
| --- | --- |
| **Visible** | Commits, pull requests, issues and reviews in repositories your token can see |
| **Restricted** | Contributions in repositories your token cannot see. GitHub only reports a count, with no details |

The sensor **Contributions this month** adds both by default. Its attributes `visible`, `restricted` and `includes_restricted` show the split. The per-type sensors (commits, pull requests, reviews, issues) only ever count visible contributions, so they can be far lower than the total.

## Why the numbers depend on the token

GitHub decides what a token may see:

- **Public repositories** are visible to every token.
- **Private repositories** are visible to a classic token with the `repo` scope (add `read:org` for organization repositories), and to a fine-grained token only for its single owner and the repositories you selected.
- Everything else is reported as one anonymous restricted count per period.

An account with mostly private work can therefore show few commits and many restricted contributions. That is expected, not a bug.

## Make more contributions visible

1. Use a classic token with `repo` and `read:org`, or a fine-grained token that includes your private repositories.
2. For organization repositories, authorize the token for the organization (SSO) if it enforces that.
3. On github.com, open your profile settings and enable **Private contributions** so the public calendar matches.

## Leave restricted contributions out

Turn off **Include restricted contributions** in the integration options. **Contributions this month** and **Busiest month this year** then use visible contributions only.

## Time zone

GitHub groups contributions into days using Pacific Time unless your profile says otherwise. If your month totals differ from github.com, set the **contribution time zone** option to your profile's time zone.
