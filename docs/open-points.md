# Open points for discussion

Collected during implementation; to be discussed at the end. Newest entries at the bottom.

| # | Topic | Context | Needed from the maintainer |
| --- | --- | --- | --- |
| 1 | Initial commit on `main` | The repository was empty, so the first commit (license, `.gitignore`, concept document) went straight to `main`. All later work uses branches and pull requests. | Nothing, FYI. |
| 2 | Fine-grained test token | The permission matrix cannot confirm whether GraphQL contributions work with a fine-grained PAT. | A fine-grained PAT (read-only, own repositories) for a one-off probe, if you want this verified before 0.1.0. |
| 3 | `read:packages` scope | The Packages go/no-go (HGP-11) needs live download values. The `gh` token lacks this scope. | Run `gh auth refresh -s read:packages` (changes the scopes of the `gh` token) or provide a token, if the Packages module should be built. |
| 4 | Local folder name | The working copy lives in `~/Projects/ha-github-insights` while the repository is `ha-github-pulse`. | Rename the folder when convenient; nothing in the project depends on it. |
| 5 | Contribution time zone | GitHub buckets contribution days in Pacific Time by default. The integration therefore uses `America/Los_Angeles` unless changed in the options. | Your GitHub profile time zone, if you set one. |
| 6 | Language estimate evidence | Only two single-language repositories were measured. | Optionally name a repository with a real language mix for a follow-up measurement. |
