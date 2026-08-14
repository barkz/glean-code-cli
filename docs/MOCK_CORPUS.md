# Mock Corpus

Reference for the fake corpus that backs **mock mode**. See [Mock corpus](../README.md#mock-corpus)
in the README for the short version, and [Command Reference](COMMANDS.md) for the commands themselves.

Mock mode is what runs when no Client API credentials are configured — no `/auth` session
and no `/login` token — or when you force it with `/mode mock`. Instead of returning
templated placeholders, every mock endpoint reads from one corpus of seventy
documents belonging to a single fictional company, **Acme**. That means offline mode
behaves like one coherent index: a URL from `/search` resolves in `/docs.get`, summarizes
to the same document in `/summarize`, and shows up as a real citation in `/chat`.

The corpus lives in [`glean_code/mock_corpus.py`](../glean_code/mock_corpus.py) and can be
replaced wholesale — see [Bring your own corpus](#bring-your-own-corpus).

## Contents

- [The faux datasources](#the-faux-datasources)
- [The people roster](#the-people-roster)
- [Document inventory](#document-inventory)
- [Worked examples](#worked-examples)
- [Commands that read the corpus](#commands-that-read-the-corpus)
- [How ranking works](#how-ranking-works)
- [Quarter and fiscal-year placeholders](#quarter-and-fiscal-year-placeholders)
- [Bring your own corpus](#bring-your-own-corpus)
- [Tests](#tests)

## The faux datasources

Five datasource names, chosen because they are the ones most Glean tenants actually have.
These are the exact strings to pass to `--datasource`, and the exact values that come back
in each result's `datasource` field.

The corpus is balanced — fourteen documents per datasource, seventy in total.

| Datasource | Docs | What lives there | URL shape |
| --- | --- | --- | --- |
| `gdrive` | 14 | Planning charters, trackers, policies, decks, budget models, research, meeting notes | `https://docs.google.com/document/d/<id>/edit`, `…/spreadsheets/d/<id>/edit#gid=0`, `…/presentation/d/<id>/edit` |
| `confluence` | 14 | Handbook pages, runbooks, postmortems, onboarding, process docs, compliance matrices | `https://acme.atlassian.net/wiki/spaces/<SPACE>/pages/<id>/<Title>` |
| `jira` | 14 | Epics, stories, bugs, incidents, security and support tickets | `https://acme.atlassian.net/browse/<KEY-123>` |
| `github` | 14 | Pull requests and repository files across five repos | `https://github.com/acme/<repo>/pull/<n>`, `https://github.com/acme/<repo>/blob/main/<path>` |
| `slack` | 14 | Channel threads — kickoffs, war rooms, rollouts, announcements | `https://acme.slack.com/archives/<CHANNEL>/p<ts>` |

Confluence spaces in use: `ENG`, `SRE`, `SEC`, `PEOPLE`, `REV`, `PLAT`, `SUP`.
Jira boards: `PLAN`, `INC`, `SEC`, `PLAT`, `SUP`, `REV`.
GitHub repos: `acme/platform`, `acme/payments`, `acme/infra`, `acme/connectors`, `acme/web`.
Slack channels: `#planning`, `#incident-checkout`, `#sales-eng`, `#eng-general`, `#platform`,
`#security`, `#support`, `#product`, `#hiring`.

Every datasource is filterable:

```text
/search "planning" --datasource confluence
/search "incident" --datasource slack
/search "migration" --datasource github --page-size 3
```

Facet counts (the numbers `/datasources.list --with-counts` reports) are plausible index
sizes, deliberately unequal — the corpus is balanced so every source demos equally well, but a
real tenant's index never is:

```text
/datasources.list --with-counts
```

```text
  gdrive      1840
  confluence  920
  slack       611
  jira        430
  github      268
```

## The people roster

Eight people, all `@acme.com`. They are the authors on documents, the results of
`/entities.list`, the profiles behind `/people.get`, and the owners in `/docs.permissions`.

| Email | Name | Title | Department |
| --- | --- | --- | --- |
| `priya.raman@acme.com` | Priya Raman | Director of Engineering | Platform |
| `marcus.webb@acme.com` | Marcus Webb | Group Product Manager | Product |
| `sam.iyer@acme.com` | Sam Iyer | Staff SRE | Infrastructure |
| `dana.ortiz@acme.com` | Dana Ortiz | Finance Business Partner | Finance |
| `nina.kowalski@acme.com` | Nina Kowalski | Security Engineer | Security |
| `theo.lambert@acme.com` | Theo Lambert | Sales Engineer | Revenue |
| `yuki.tanaka@acme.com` | Yuki Tanaka | People Ops Lead | People |
| `rosa.mendez@acme.com` | Rosa Mendez | Support Lead | Customer Experience |

```text
/people.get priya.raman@acme.com
/entities.list --kind PEOPLE --page-size 5
```

## Document inventory

Seventy documents in ten clusters that cross-reference each other — the checkout incident
appears as a Jira ticket, a Slack war room, a Confluence postmortem, the GitHub PR that fixed
it, and a later Slack follow-up confirming the retry budget shipped. `{Q}` and `{Q+1}` in
titles are expanded at request time (see
[placeholders](#quarter-and-fiscal-year-placeholders)).

### Quarterly planning

| Id | Datasource | Title | Author | Tags |
| --- | --- | --- | --- | --- |
| `doc_plan_charter` | gdrive | {Q+1} Planning Charter — Platform Engineering | Priya Raman | quarterly, planning, roadmap, platform, okr |
| `doc_plan_tracker` | gdrive | Quarterly Planning Tracker — All Teams ({Q+1}) | Marcus Webb | quarterly, planning, tracker, capacity, commitments |
| `doc_plan_process` | confluence | How We Run Quarterly Planning (RFC → Commit → Review) | Priya Raman | quarterly, planning, process, handbook, rfc |
| `doc_plan_slack` | slack | Kickoff thread: {Q+1} quarterly planning | Marcus Webb | quarterly, planning, kickoff, deadline |
| `doc_plan_epic` | jira | PLAN-482 — {Q+1} planning: engineering capacity model | Dana Ortiz | quarterly, planning, capacity, headcount, finance |
| `doc_qbr_deck` | gdrive | {Q} Business Review — Company All-Hands Deck | Dana Ortiz | qbr, business review, metrics, planning, all-hands |

### On-call, incidents, reliability

| Id | Datasource | Title | Author | Tags |
| --- | --- | --- | --- | --- |
| `doc_runbook_payments` | confluence | On-Call Runbook — Payments Service | Sam Iyer | oncall, runbook, payments, sre, alerts |
| `doc_postmortem_checkout` | confluence | Postmortem: Checkout Latency Incident (INC-1183) | Sam Iyer | postmortem, incident, checkout, latency, oncall |
| `doc_inc_ticket` | jira | INC-1183 — Elevated 5xx on checkout API | Sam Iyer | incident, checkout, sev2, oncall, payments |
| `doc_inc_slack` | slack | War room thread: checkout 5xx spike | Rosa Mendez | incident, checkout, support, oncall |
| `doc_pr_breaker` | github | acme/payments#1841 — Add circuit breaker to charge path | Sam Iyer | payments, reliability, circuit breaker, postmortem |
| `doc_service_catalog` | confluence | Service Catalog — Ownership and SLOs | Priya Raman | services, ownership, slo, oncall, catalog |

### Onboarding and people

| Id | Datasource | Title | Author | Tags |
| --- | --- | --- | --- | --- |
| `doc_onboarding` | confluence | Engineering Onboarding — Your First 30 Days | Yuki Tanaka | onboarding, new hire, setup, handbook |
| `doc_pto` | gdrive | PTO and Leave Policy (FY{FY}) | Yuki Tanaka | pto, policy, leave, hr, benefits |
| `doc_interview_loop` | confluence | Interview Loop Guide — Backend Engineering | Yuki Tanaka | hiring, interview, rubric, engineering |
| `doc_eng_leads_notes` | gdrive | Meeting Notes — Weekly Engineering Leads Sync | Priya Raman | meeting notes, leads, weekly, planning |

### Security and compliance

| Id | Datasource | Title | Author | Tags |
| --- | --- | --- | --- | --- |
| `doc_soc2` | confluence | SOC 2 Evidence Collection — Owner Matrix | Nina Kowalski | soc2, compliance, audit, security, evidence |
| `doc_retention` | gdrive | Data Retention Standard v3 | Nina Kowalski | retention, data, policy, privacy, compliance |
| `doc_key_rotation` | jira | SEC-233 — Rotate service account keys before audit window | Nina Kowalski | security, keys, rotation, audit, compliance |
| `doc_threat_model` | github | acme/infra — security/threat-model.md | Nina Kowalski | security, threat model, architecture, review |

### Product, sales, customers

| Id | Datasource | Title | Author | Tags |
| --- | --- | --- | --- | --- |
| `doc_roadmap` | gdrive | Product Roadmap — {Q+1} and Beyond | Marcus Webb | roadmap, product, planning, strategy |
| `doc_pricing` | gdrive | Pricing and Packaging FAQ | Theo Lambert | pricing, packaging, sales, faq, enablement |
| `doc_battlecard` | confluence | Competitive Battlecard — Enterprise Search Vendors | Theo Lambert | competitive, sales, battlecard, enterprise |
| `doc_rfp_slack` | slack | RFP questions for Northwind — security section | Theo Lambert | rfp, sales, security, customer |
| `doc_qbr_northwind` | gdrive | Customer QBR — Northwind Retail | Rosa Mendez | qbr, customer, northwind, renewal, adoption |

### Platform engineering

| Id | Datasource | Title | Author | Tags |
| --- | --- | --- | --- | --- |
| `doc_api_search` | github | acme/platform — docs/api/search.md | Priya Raman | api, search, documentation, platform |
| `doc_pr_indexer` | github | acme/platform#2033 — Migrate indexing worker to async queue | Priya Raman | indexing, migration, platform, queue, performance |
| `doc_indexer_ticket` | jira | PLAT-908 — Migrate indexing worker off cron | Sam Iyer | indexing, migration, platform, quarterly |
| `doc_budget_model` | gdrive | Headcount and Budget Model FY{FY} | Dana Ortiz | budget, headcount, finance, planning, capacity |
| `doc_connector_status` | confluence | Connector Health Dashboard — Weekly Notes | Sam Iyer | connectors, indexing, health, platform, sync |

### Engineering process and architecture

| Id | Datasource | Title | Author | Tags |
| --- | --- | --- | --- | --- |
| `doc_deploy_process` | confluence | Deploy and Release Process | Priya Raman | deploy, release, process, ci, rollback |
| `doc_arch_decisions` | confluence | Architecture Decision Log | Priya Raman | architecture, adr, decisions, platform, history |
| `doc_sev_levels` | confluence | Incident Severity Levels and Comms Templates | Sam Iyer | incident, severity, comms, oncall, process |
| `doc_access_review` | confluence | Quarterly Access Review Procedure | Nina Kowalski | access review, security, compliance, audit, quarterly |
| `doc_support_kb` | confluence | Support Knowledge Base — Top 20 Customer Questions | Rosa Mendez | support, knowledge base, faq, customer, troubleshooting |

### Policies, research, planning artefacts

| Id | Datasource | Title | Author | Tags |
| --- | --- | --- | --- | --- |
| `doc_expense_policy` | gdrive | Travel and Expense Policy | Dana Ortiz | expenses, travel, policy, finance, approvals |
| `doc_user_research` | gdrive | User Research Findings — Search Relevance Interviews | Marcus Webb | research, search, relevance, product, interviews |
| `doc_support_playbook` | gdrive | Support Escalation Playbook | Rosa Mendez | support, escalation, playbook, sla, customer |
| `doc_okr_scorecard` | gdrive | {Q} OKR Scorecard — Company | Marcus Webb | okr, scorecard, metrics, quarterly, planning |

### Platform and connector work (Jira)

| Id | Datasource | Title | Author | Tags |
| --- | --- | --- | --- | --- |
| `doc_jira_sharding` | jira | PLAT-914 — Shard the search index by tenant | Sam Iyer | indexing, sharding, platform, scale, search |
| `doc_jira_coldstart` | jira | PLAT-931 — Reduce cold-start latency on the query service | Priya Raman | latency, performance, platform, query, startup |
| `doc_jira_slack_stall` | jira | INC-1207 — Slack connector sync stalled for six hours | Sam Iyer | incident, connectors, slack, sync, sev3 |
| `doc_jira_dupes` | jira | INC-1219 — Duplicate documents after Confluence re-index | Sam Iyer | incident, confluence, indexing, duplicates, sev3 |
| `doc_jira_mfa` | jira | SEC-241 — Enforce MFA on internal service dashboards | Nina Kowalski | security, mfa, access, dashboards, compliance |
| `doc_jira_dep_audit` | jira | SEC-256 — Third-party dependency audit for {Q+1} | Nina Kowalski | security, dependencies, audit, supply chain, compliance |
| `doc_jira_headcount` | jira | PLAN-497 — Define engineering headcount asks for {Q+1} | Dana Ortiz | headcount, planning, finance, hiring, quarterly |
| `doc_jira_northwind` | jira | SUP-882 — Northwind: search results missing Confluence attachments | Rosa Mendez | support, northwind, confluence, attachments, customer |
| `doc_jira_perm_tests` | jira | PLAT-902 — Add permissions fidelity tests to the connector suite | Priya Raman | permissions, testing, connectors, platform, quality |
| `doc_jira_roi` | jira | REV-141 — Build an ROI calculator for enterprise deals | Theo Lambert | sales, roi, enablement, enterprise, pricing |

### Repositories and pull requests (GitHub)

| Id | Datasource | Title | Author | Tags |
| --- | --- | --- | --- | --- |
| `doc_gh_slack_backfill` | github | acme/connectors#412 — Slack connector: backfill thread replies | Sam Iyer | slack, connectors, backfill, threads, indexing |
| `doc_gh_shard_writer` | github | acme/platform#2051 — Add tenant sharding to the index writer | Priya Raman | indexing, sharding, platform, writer, scale |
| `doc_gh_chat_api` | github | acme/platform — docs/api/chat.md | Priya Raman | api, chat, documentation, platform, citations |
| `doc_gh_queue_readme` | github | acme/infra — terraform/modules/queue/README.md | Sam Iyer | infrastructure, terraform, queue, indexing, runbook |
| `doc_gh_ds_badge` | github | acme/web#788 — Search results: show datasource badge | Marcus Webb | frontend, search, ui, datasource, results |
| `doc_gh_connector_checklist` | github | acme/connectors — docs/connector-checklist.md | Sam Iyer | connectors, checklist, permissions, indexing, quality |
| `doc_gh_idempotent_charges` | github | acme/payments#1902 — Make charge retries idempotent | Sam Iyer | payments, idempotency, retries, reliability, charges |
| `doc_gh_perm_cache` | github | acme/platform#2077 — Cache permission checks per request | Priya Raman | permissions, performance, cache, platform, latency |
| `doc_gh_ci_keys` | github | acme/infra#644 — Rotate CI signing keys | Nina Kowalski | security, ci, keys, rotation, infrastructure |
| `doc_gh_accessibility` | github | acme/web — docs/accessibility.md | Marcus Webb | accessibility, frontend, wcag, standards, ui |

### Channel conversation (Slack)

| Id | Datasource | Title | Author | Tags |
| --- | --- | --- | --- | --- |
| `doc_slack_freeze` | slack | Deploy freeze during the audit window | Priya Raman | deploy, freeze, audit, process, announcement |
| `doc_slack_sharding` | slack | Index sharding rollout plan | Sam Iyer | sharding, indexing, rollout, platform, migration |
| `doc_slack_mfa` | slack | MFA enforcement rollout — two week grace period | Nina Kowalski | security, mfa, rollout, access, announcement |
| `doc_slack_support_northwind` | slack | Northwind attachment issue — need connector eyes | Rosa Mendez | support, northwind, attachments, escalation, confluence |
| `doc_slack_roadmap_review` | slack | Roadmap review notes — three bets confirmed | Marcus Webb | roadmap, product, review, planning, notes |
| `doc_slack_hiring` | slack | Backend loop debriefs — please submit feedback first | Yuki Tanaka | hiring, interview, debrief, feedback, process |
| `doc_slack_retry_budget` | slack | Follow-up: retry budget change is live | Sam Iyer | incident, checkout, retries, postmortem, followup |
| `doc_slack_capacity_q` | slack | Questions on the capacity model numbers | Dana Ortiz | planning, capacity, finance, questions, quarterly |
| `doc_slack_demo_env` | slack | Demo environment refreshed for the quarter | Theo Lambert | demo, sales, environment, enablement, refresh |
| `doc_slack_new_starters` | slack | New starters this week — say hello | Yuki Tanaka | onboarding, new hire, announcement, team |
| `doc_slack_sync_lag` | slack | Connector sync lag dashboard is live | Sam Iyer | connectors, monitoring, sync, dashboard, platform |

## Worked examples

### Search, then follow the result

The point of a shared corpus: the URL you get back actually resolves.

```text
/mode mock
/search "quarterly planning" --page-size 3
```

```text
1. Kickoff thread: Q4 FY26 quarterly planning
   slack  https://acme.slack.com/archives/C02PLAN9K/p1719483920
   Marcus Webb  ·  Message  ·  #planning  ·  updated 6 days ago
   Kicking off Q4 FY26 planning. Drafts go in the tracker by Friday, and please link the RFC rather than pasting it inline. …

2. How We Run Quarterly Planning (RFC → Commit → Review)
   confluence  https://acme.atlassian.net/wiki/spaces/ENG/pages/482910/How+We+Run+Quarterly+Planning
   Priya Raman  ·  Page  ·  ENG space  ·  updated 23 days ago
   Quarterly planning at Acme runs in three phases. In RFC, teams write a one-page proposal describing the problem, the bet, and what gets dropped to make room. …

3. Quarterly Planning Tracker — All Teams (Q4 FY26)
   gdrive  https://docs.google.com/spreadsheets/d/1Tr4ckQpLanW7bXz/edit#gid=0
   Marcus Webb  ·  Spreadsheet  ·  Planning / Trackers  ·  updated yesterday
   One row per committed objective across the eleven product and platform teams. Columns cover owner, key result, engineer-weeks, dependency, confidence, and status. …
```

Take result 2's URL and keep going — same document every time:

```text
/summarize --url https://acme.atlassian.net/wiki/spaces/ENG/pages/482910/How+We+Run+Quarterly+Planning
/docs.get --url https://acme.atlassian.net/wiki/spaces/ENG/pages/482910/How+We+Run+Quarterly+Planning
/docs.permissions doc_plan_process
```

`/docs.permissions` reports the document's author as `owner` and the rest of the roster as
`viewer`, so permissions line up with the byline you just saw.

### One incident, five datasources

```text
/search "checkout incident" --page-size 5
```

Returns the Confluence postmortem, the Slack war room thread, and the Jira `INC-1183` ticket
as the top three — one event, three records, which is what a real index looks like. The
customer QBR and the payments runbook follow, because both reference the same incident. The
GitHub PR that fixed it surfaces on `checkout circuit breaker`.

Narrow to one source at a time:

```text
/search "checkout" --datasource jira
/search "checkout" --datasource slack
/search "circuit breaker" --datasource github
/search "postmortem" --datasource confluence
```

### Ask the assistant

```text
/chat "how do we run quarterly planning?"
```

Citations are drawn from the corpus by ranking the question, so the sources under the
answer are documents that exist and that `/docs.get` can fetch:

```text
Citations
  ▸ How We Run Quarterly Planning (RFC → Commit → Review)  https://acme.atlassian.net/wiki/…
  ▸ Kickoff thread: Q4 FY26 quarterly planning  https://acme.slack.com/archives/C02PLAN9K/p1719483920
  ▸ Quarterly Planning Tracker — All Teams (Q4 FY26)  https://docs.google.com/spreadsheets/…
```

### Everything else

```text
/autocomplete "quart"          # ▸ quart planning / quart tracker / quart capacity
/recommendations               # the five freshest documents
/verification.list             # corpus documents, alternating VERIFIED / UNVERIFIED
/collections.list              # Quarterly Planning · On-Call and Incidents · New Engineer Onboarding
/messages.get --id 1719483920 --datasource slack   # the Slack threads, with channel and author
/entities.list --kind PEOPLE   # the roster
/datasources.list --with-counts
```

### Topics that return good results

Queries the corpus is written to answer well:

`quarterly planning` · `capacity model` · `okr scorecard` · `oncall runbook` ·
`payments alert` · `checkout incident` · `postmortem` · `circuit breaker` ·
`idempotent charge retries` · `severity levels` · `deploy freeze` · `release process` ·
`architecture decisions` · `onboarding` · `new starters` · `pto policy` · `expense policy` ·
`interview loop` · `hiring debrief` · `soc 2 audit` · `access review` · `data retention` ·
`key rotation` · `mfa enforcement` · `threat model` · `dependency audit` ·
`product roadmap` · `user research` · `pricing` · `roi calculator` ·
`competitive battlecard` · `rfp` · `customer qbr` · `northwind attachments` ·
`support escalation` · `knowledge base` · `indexing migration` · `index sharding` ·
`connector health` · `connector sync lag` · `permissions cache` · `cold start latency` ·
`service catalog` · `headcount budget` · `search api` · `chat api` · `accessibility` ·
`datasource badge` · `demo environment`

## Commands that read the corpus

| Command | Endpoint | What the corpus provides |
| --- | --- | --- |
| [`/search`](COMMANDS.md#search) | `/search` | Ranked results with snippets, byline metadata, and facet counts; `--datasource` filters |
| [`/chat`](COMMANDS.md#chat) | `/chat` | Citations ranked against the question |
| [`/autocomplete`](COMMANDS.md#autocomplete) | `/autocomplete` | Completions built from the tags of matching documents |
| [`/recommendations`](COMMANDS.md#recommendations) | `/recommendations` | The freshest documents, in full result shape |
| [`/datasources.list`](COMMANDS.md#datasourceslist) | `/search` (facets) | The five datasource names and their index counts |
| [`/docs.get`](COMMANDS.md#docsget) | `/getdocuments` | Lookup by id or URL; unknown specs echo back |
| [`/docs.permissions`](COMMANDS.md#docspermissions) | `/getdocumentpermissions` | Author as `owner`, roster as `viewer` |
| [`/summarize`](COMMANDS.md#summarize) | `/summarize` | A summary built from that document's body, author, and age |
| [`/entities.list`](COMMANDS.md#entitieslist) | `/listentities` | The people roster |
| [`/people.get`](COMMANDS.md#peopleget) | `/people` | Profile for a roster email |
| [`/verification.list`](COMMANDS.md#verificationlist) | `/listverifications` | Corpus documents with alternating verification status |
| [`/messages.get`](COMMANDS.md#messagesget) | `/messages` | The Slack threads, with channel and author |
| [`/collections.list`](COMMANDS.md#collectionslist) | `/listcollections` | Collections named after the corpus clusters |

Everything else in mock mode — indexing commands, agents, tools, announcements, pins,
shortcuts, answers, insights — returns its own realistic shapes and does not read the
corpus. Indexing mock mode is documented separately in
[Mock mode for indexing](../README.md#mock-mode-for-indexing).

The corpus is a REPL convenience only. The [MCP server](../README.md#mcp-server) forces
`mode = "live"`, so agents calling Glean through `glean_mcp.py` never see it.

## How ranking works

Search is ranked, not templated.

- **Scoring** — each query term scores against the title (6, or 3 for a prefix match), tags (4),
  body (2), and the datasource or container name (3). An exact phrase in the title adds 8; in
  the body or tags, 4.
- **Ties** break toward the freshest document, then by id, so results are stable between runs.
- **Snippets** are taken from the sentence that contains the most query terms, extended by one
  sentence when there is room, and ellipsed at either end to show they were clipped.
- **`--datasource`** is applied before scoring. Both request shapes are honoured:
  `requestOptions.datasourceFilter` and a `datasource` entry in `requestOptions.facetFilters`.
- **Match-all** (`*` or an empty query) returns everything ordered by freshness. This is what
  `/datasources.list` and `/recommendations` use.
- **Padding** — when a query matches nothing, the page is filled with the freshest documents
  rather than coming back empty, so a demo never lands on a blank screen.
- **Page size** is capped at 10 per request.

## Quarter and fiscal-year placeholders

Titles and bodies may contain placeholders, expanded when the request is served:

| Placeholder | Expands to | Example |
| --- | --- | --- |
| `{Q}` | The current quarter | `Q3 FY26` |
| `{Q+1}` | Next quarter | `Q4 FY26` |
| `{Q+2}` | Two quarters out | `Q1 FY27` |
| `{FY}` | Two-digit fiscal year | `26` |

This is why the corpus doesn't rot: a planning charter written once still reads as next
quarter's charter a year from now. Ages work the same way — documents carry
`updated_days_ago`, rendered as `updated yesterday`, `updated 8 days ago`, `updated last
month`, and so on.

## Bring your own corpus

Point the CLI at a JSON file to replace the built-in documents entirely — useful for a demo
tailored to a specific audience, or for rehearsing against a corpus that mirrors a real
tenant's content.

```text
/config set mock_corpus_path ~/demo-corpus.json
```

Or, without touching config:

```bash
export GLEAN_MOCK_CORPUS=~/demo-corpus.json
```

The config key wins when both are set. `/status` shows which is in effect — the path, or
`(built-in Acme corpus)`.

### File format

```json
{
  "people": {
    "ada@northwind.com": {
      "name": "Ada Lovelace",
      "title": "Staff Engineer",
      "department": "Platform"
    }
  },
  "datasourceCounts": {"gdrive": 1840, "confluence": 920, "slack": 611},
  "documents": [
    {
      "id": "doc_widget_plan",
      "datasource": "gdrive",
      "doc_type": "Document",
      "container": "Platform / Planning",
      "title": "{Q+1} Widget Launch Plan",
      "url": "https://docs.google.com/document/d/widget1/edit",
      "author": "ada@northwind.com",
      "updated_days_ago": 2,
      "tags": ["launch", "widget", "planning"],
      "body": "The widget launch ships in three phases. Beta customers get access first."
    }
  ]
}
```

A bare JSON array of documents is also accepted — the `people` and `datasourceCounts` keys
are optional, and omitting them keeps the built-in roster and counts.

### Field reference

| Field | Required | Default | Notes |
| --- | --- | --- | --- |
| `title` | **yes** | — | Supports `{Q}` / `{Q+1}` / `{Q+2}` / `{FY}` |
| `body` | **yes** | the title | Full text; drives ranking, snippets, and summaries. Write real sentences — snippets are extracted per sentence |
| `id` | no | `doc_<n>` | Used by `/docs.get --id` and `/docs.permissions` |
| `datasource` | no | `gdrive` | Any string; becomes a `--datasource` value and a facet bucket |
| `url` | no | generated | Used by `/docs.get --url` and `/summarize --url` |
| `author` | no | none | An email; matched against `people` for the byline. Omit and the byline just shows type and freshness |
| `doc_type` | no | `Document` | Shown in the byline, e.g. `Page`, `Epic`, `Pull Request`, `Message` |
| `container` | no | empty | Space, board, channel, or folder; shown in the byline and scored |
| `updated_days_ago` | no | position in the file | Drives freshness ordering and the `updated …` phrasing |
| `tags` | no | none | Scored just below the title — the cheapest way to make a document findable |

### When a corpus file is bad

Errors surface as ordinary command errors, not tracebacks:

```text
✖ mock corpus file not found: /tmp/nope.json
✖ mock corpus file is not valid JSON (/tmp/bad.json): Expecting property name…
✖ mock corpus file has no documents: /tmp/empty.json
✖ document 3 is missing a title
```

Fix the file and re-run the command — it is re-read on the next call, with no restart needed.

## Tests

[`tests/test_mock_corpus.py`](../tests/test_mock_corpus.py) covers ranking, datasource
filtering, padding, snippet selection, placeholder expansion, cross-endpoint coherence
(a `/search` URL resolving through `/getdocuments` and `/summarize`), and every custom-corpus
failure mode. See [Test Harness](TESTING.md).

```bash
python3 -m unittest tests.test_mock_corpus -v
```
