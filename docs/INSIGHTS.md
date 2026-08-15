# Insights

`/insights` retrieves aggregate usage data from the Glean Insights Dashboard — the same data visible in the admin UI. It covers search adoption, active user counts, search session satisfaction, datasource click distribution, and AI assistant activity.

Uses the same Client API token as search and chat — no extra credentials required.

## Flags

| Flag | Description |
| --- | --- |
| _(none)_ | Overview only: MAU, WAU, employee count, sign-ups, search satisfaction, clicks by datasource |
| `--assistant` | Adds Assistant metrics: MAU, WAU, chat messages, AI answers, summarizations |
| `--agents` | Adds Agents metrics: MAU, WAU |
| `--all` | All three surfaces in one call |
| `--no-per-user` | Suppresses the per-user breakdown in the response |
| `--export <file>` | Write all returned metrics to a CSV file (columns: `section`, `metric`, `value`) |

## Examples

```text
/insights
/insights --all
/insights --assistant
/insights --agents --no-per-user
/insights --all --export insights.csv
```

## What the output shows

### Overview

- Monthly and weekly active users
- Employee count and total sign-ups (from org chart)
- Search session satisfaction rate (%)
- Last updated timestamp
- Search clicks broken down by datasource (gdrive, confluence, slack, jira, etc.)

### Assistant (with `--assistant` or `--all`)

- Monthly and weekly active users of the Glean Assistant
- Chat message, AI answer, and summarization activity

### Agents (with `--agents` or `--all`)

- Monthly and weekly active users across agent runs

## Endpoint

```text
POST /rest/api/v1/insights
```

---

[← Back to README](../README.md) · [Command Reference](COMMANDS.md)
