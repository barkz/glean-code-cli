"""A small, coherent fake corpus that backs mock mode.

Every mock endpoint in client.py resolves against the documents below, so the
offline CLI behaves like one company's index instead of a pile of unrelated
placeholders: you can `/search "quarterly planning"`, take the URL off result
3, `/docs.summarize` it, and get a summary of that same document.

The fictional company is Acme. Seventy documents, balanced at fourteen per datasource
(`gdrive`, `confluence`, `jira`, `github`, `slack`), so no source is thin in a demo.
Documents carry per-datasource URL shapes
(Google Docs ids, Slack archive permalinks, Confluence page paths, Jira keys,
GitHub blob/PR paths), an author drawn from a fixed roster, and an age in days
that is rendered relative to now — so the corpus never reads as stale.

Titles may contain `{Q}` / `{Q+1}` / `{FY}` placeholders, expanded at request
time to the current and next quarter (e.g. "Q3 FY26").

Bring your own corpus
---------------------
Point `mock_corpus_path` in config (or the GLEAN_MOCK_CORPUS env var) at a
JSON file to replace the built-in set — handy for tailoring a demo:

    {
      "people": {"ada@acme.com": {"name": "Ada Lovelace",
                                   "title": "Engineer",
                                   "department": "Platform"}},
      "datasourceCounts": {"gdrive": 1840},
      "documents": [
        {"id": "doc_1", "datasource": "gdrive", "title": "...",
         "url": "https://...", "author": "ada@acme.com", "updated_days_ago": 3,
         "tags": ["planning"], "body": "Full text used for ranking, snippets "
                                       "and summaries."}
      ]
    }

Only `title` and `body` are required per document; everything else is filled
in with a sensible default.
"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

COMPANY = "Acme"
CORPUS_ENV_VAR = "GLEAN_MOCK_CORPUS"

# Results are capped here regardless of the requested page size, matching the
# behaviour callers of mock mode have always seen.
MAX_RESULTS = 10


class CorpusError(Exception):
    """Raised when a user-supplied corpus file cannot be used."""


# -------------------- people --------------------

PEOPLE: Dict[str, Dict[str, str]] = {
    "priya.raman@acme.com":  {"name": "Priya Raman",   "title": "Director of Engineering", "department": "Platform"},
    "marcus.webb@acme.com":  {"name": "Marcus Webb",   "title": "Group Product Manager",   "department": "Product"},
    "sam.iyer@acme.com":     {"name": "Sam Iyer",      "title": "Staff SRE",               "department": "Infrastructure"},
    "dana.ortiz@acme.com":   {"name": "Dana Ortiz",    "title": "Finance Business Partner","department": "Finance"},
    "nina.kowalski@acme.com":{"name": "Nina Kowalski", "title": "Security Engineer",       "department": "Security"},
    "theo.lambert@acme.com": {"name": "Theo Lambert",  "title": "Sales Engineer",          "department": "Revenue"},
    "yuki.tanaka@acme.com":  {"name": "Yuki Tanaka",   "title": "People Ops Lead",         "department": "People"},
    "rosa.mendez@acme.com":  {"name": "Rosa Mendez",   "title": "Support Lead",            "department": "Customer Experience"},
}

# Plausible index sizes per datasource, used for facet counts. Kept in the
# same rank order as the document spread below so counts and results agree.
DATASOURCE_COUNTS: Dict[str, int] = {
    "gdrive": 1840,
    "confluence": 920,
    "slack": 611,
    "jira": 430,
    "github": 268,
}


# -------------------- documents --------------------

DOCS: List[Dict[str, Any]] = [
    # ---- quarterly planning ----
    {
        "id": "doc_plan_charter",
        "datasource": "gdrive",
        "doc_type": "Document",
        "container": "Platform Eng / Planning",
        "title": "{Q+1} Planning Charter — Platform Engineering",
        "url": "https://docs.google.com/document/d/1QpLan4aXk2Bc7Rm9TdZ/edit",
        "author": "priya.raman@acme.com",
        "updated_days_ago": 4,
        "tags": ["quarterly", "planning", "roadmap", "platform", "okr"],
        "body": (
            "This charter opens {Q+1} quarterly planning for Platform Engineering. "
            "Teams submit draft objectives by week two, review capacity with Finance in week three, "
            "and lock commitments at the planning review on the last Thursday of {Q}. "
            "Each objective needs a named owner, a measurable key result, and an estimate in engineer-weeks. "
            "Carry-over work from {Q} counts against capacity before any new commitment is accepted."
        ),
    },
    {
        "id": "doc_plan_tracker",
        "datasource": "gdrive",
        "doc_type": "Spreadsheet",
        "container": "Planning / Trackers",
        "title": "Quarterly Planning Tracker — All Teams ({Q+1})",
        "url": "https://docs.google.com/spreadsheets/d/1Tr4ckQpLanW7bXz/edit#gid=0",
        "author": "marcus.webb@acme.com",
        "updated_days_ago": 1,
        "tags": ["quarterly", "planning", "tracker", "capacity", "commitments"],
        "body": (
            "One row per committed objective across the eleven product and platform teams. "
            "Columns cover owner, key result, engineer-weeks, dependency, confidence, and status. "
            "Confidence below 70 percent at lock triggers a scope conversation with the sponsoring PM rather than a silent slip. "
            "The rollup tab compares committed engineer-weeks against the capacity model."
        ),
    },
    {
        "id": "doc_plan_process",
        "datasource": "confluence",
        "doc_type": "Page",
        "container": "ENG space",
        "title": "How We Run Quarterly Planning (RFC → Commit → Review)",
        "url": "https://acme.atlassian.net/wiki/spaces/ENG/pages/482910/How+We+Run+Quarterly+Planning",
        "author": "priya.raman@acme.com",
        "updated_days_ago": 23,
        "tags": ["quarterly", "planning", "process", "handbook", "rfc"],
        "body": (
            "Quarterly planning at Acme runs in three phases. "
            "In RFC, teams write a one-page proposal describing the problem, the bet, and what gets dropped to make room. "
            "In Commit, directors reconcile proposals against the capacity model and cut the bottom twenty percent. "
            "In Review, every team demos what shipped against last quarter's commitments before new work is approved. "
            "The whole cycle takes four weeks and ends the week before the quarter turns."
        ),
    },
    {
        "id": "doc_plan_slack",
        "datasource": "slack",
        "doc_type": "Message",
        "container": "#planning",
        "title": "Kickoff thread: {Q+1} quarterly planning",
        "url": "https://acme.slack.com/archives/C02PLAN9K/p1719483920",
        "author": "marcus.webb@acme.com",
        "updated_days_ago": 6,
        "tags": ["quarterly", "planning", "kickoff", "deadline"],
        "body": (
            "Kicking off {Q+1} planning. Drafts go in the tracker by Friday, and please link the RFC rather than pasting it inline. "
            "Reminder that capacity is down roughly eight percent this quarter because of the compliance work landing in the same window. "
            "If your team is blocked on a dependency, flag it in this thread now instead of at the review."
        ),
    },
    {
        "id": "doc_plan_epic",
        "datasource": "jira",
        "doc_type": "Epic",
        "container": "PLAN board",
        "title": "PLAN-482 — {Q+1} planning: engineering capacity model",
        "url": "https://acme.atlassian.net/browse/PLAN-482",
        "author": "dana.ortiz@acme.com",
        "updated_days_ago": 9,
        "tags": ["quarterly", "planning", "capacity", "headcount", "finance"],
        "body": (
            "Rebuild the capacity model that feeds quarterly planning so it accounts for on-call load, open requisitions, and holiday coverage. "
            "The current spreadsheet overstates available engineer-weeks by about twelve percent because it ignores on-call rotation and interview time. "
            "Deliverable is a model Finance and Engineering both sign off on before the {Q+1} commit phase."
        ),
    },
    {
        "id": "doc_qbr_deck",
        "datasource": "gdrive",
        "doc_type": "Presentation",
        "container": "Company / All-Hands",
        "title": "{Q} Business Review — Company All-Hands Deck",
        "url": "https://docs.google.com/presentation/d/1QbR9vNzKw3PmXt/edit",
        "author": "dana.ortiz@acme.com",
        "updated_days_ago": 12,
        "tags": ["qbr", "business review", "metrics", "planning", "all-hands"],
        "body": (
            "Quarter in review: revenue, retention, and delivery against the commitments locked at the start of {Q}. "
            "Engineering shipped fourteen of seventeen committed objectives; the three misses all traced to a single dependency on the payments migration. "
            "The final section sets up {Q+1} planning priorities for discussion."
        ),
    },

    # ---- on-call, incidents, reliability ----
    {
        "id": "doc_runbook_payments",
        "datasource": "confluence",
        "doc_type": "Page",
        "container": "SRE space",
        "title": "On-Call Runbook — Payments Service",
        "url": "https://acme.atlassian.net/wiki/spaces/SRE/pages/771204/On-Call+Runbook+Payments",
        "author": "sam.iyer@acme.com",
        "updated_days_ago": 8,
        "tags": ["oncall", "runbook", "payments", "sre", "alerts"],
        "body": (
            "First response for every payments alert. Check the charge success rate panel before touching anything else. "
            "If 5xx on the charge path is above two percent for five minutes, open the circuit breaker with the feature flag and page the payments on-call. "
            "Do not restart the worker pool during a spike; in-flight charges are not idempotent until PAY-4419 ships. "
            "Escalation path is payments on-call, then the platform director, then the incident commander rotation."
        ),
    },
    {
        "id": "doc_postmortem_checkout",
        "datasource": "confluence",
        "doc_type": "Page",
        "container": "SRE space",
        "title": "Postmortem: Checkout Latency Incident (INC-1183)",
        "url": "https://acme.atlassian.net/wiki/spaces/SRE/pages/779911/Postmortem+INC-1183",
        "author": "sam.iyer@acme.com",
        "updated_days_ago": 17,
        "tags": ["postmortem", "incident", "checkout", "latency", "oncall"],
        "body": (
            "A connection pool exhaustion in the charge service pushed checkout p99 latency from 400ms to 9 seconds for 42 minutes. "
            "Root cause was a retry loop added the week before that held connections while waiting on a downstream timeout. "
            "Detection took eleven minutes because the alert was wired to average rather than p99 latency. "
            "Action items: alert on p99, add a circuit breaker to the charge path, and make the retry budget explicit."
        ),
    },
    {
        "id": "doc_inc_ticket",
        "datasource": "jira",
        "doc_type": "Incident",
        "container": "INC board",
        "title": "INC-1183 — Elevated 5xx on checkout API",
        "url": "https://acme.atlassian.net/browse/INC-1183",
        "author": "sam.iyer@acme.com",
        "updated_days_ago": 19,
        "tags": ["incident", "checkout", "sev2", "oncall", "payments"],
        "body": (
            "Sev-2 declared at 14:02 UTC after checkout error rate crossed five percent. "
            "Mitigated by draining the affected worker pool and rolling back the retry change. "
            "Customer impact: roughly 3,100 failed checkouts across 42 minutes, all recoverable on retry."
        ),
    },
    {
        "id": "doc_inc_slack",
        "datasource": "slack",
        "doc_type": "Message",
        "container": "#incident-checkout",
        "title": "War room thread: checkout 5xx spike",
        "url": "https://acme.slack.com/archives/C03INC118/p1718992044",
        "author": "rosa.mendez@acme.com",
        "updated_days_ago": 19,
        "tags": ["incident", "checkout", "support", "oncall"],
        "body": (
            "Support is seeing a wave of failed checkout reports, roughly forty tickets in the last ten minutes. "
            "Confirming the same signature as the alert: 502 from the charge endpoint, retry succeeds. "
            "Holding customer comms until we have a mitigation ETA from the on-call."
        ),
    },
    {
        "id": "doc_pr_breaker",
        "datasource": "github",
        "doc_type": "Pull Request",
        "container": "acme/payments",
        "title": "acme/payments#1841 — Add circuit breaker to charge path",
        "url": "https://github.com/acme/payments/pull/1841",
        "author": "sam.iyer@acme.com",
        "updated_days_ago": 14,
        "tags": ["payments", "reliability", "circuit breaker", "postmortem"],
        "body": (
            "Implements the circuit breaker action item from the INC-1183 postmortem. "
            "Opens after twenty consecutive downstream failures or a five percent error rate over a thirty second window, "
            "and half-opens with a single probe request after sixty seconds. "
            "Behind the payments.breaker flag, defaulted off until the runbook is updated."
        ),
    },
    {
        "id": "doc_service_catalog",
        "datasource": "confluence",
        "doc_type": "Page",
        "container": "ENG space",
        "title": "Service Catalog — Ownership and SLOs",
        "url": "https://acme.atlassian.net/wiki/spaces/ENG/pages/512044/Service+Catalog",
        "author": "priya.raman@acme.com",
        "updated_days_ago": 34,
        "tags": ["services", "ownership", "slo", "oncall", "catalog"],
        "body": (
            "Every production service, its owning team, its on-call rotation, and its SLO. "
            "Payments and checkout run a 99.95 percent availability target; internal tooling runs 99.5 percent. "
            "A service without a named owner cannot be deployed to production — the deploy gate checks this table."
        ),
    },

    # ---- onboarding and people ----
    {
        "id": "doc_onboarding",
        "datasource": "confluence",
        "doc_type": "Page",
        "container": "ENG space",
        "title": "Engineering Onboarding — Your First 30 Days",
        "url": "https://acme.atlassian.net/wiki/spaces/ENG/pages/331002/Engineering+Onboarding",
        "author": "yuki.tanaka@acme.com",
        "updated_days_ago": 27,
        "tags": ["onboarding", "new hire", "setup", "handbook"],
        "body": (
            "Day one is accounts and laptop setup; day two is a local build of the platform monorepo. "
            "Every new engineer ships a documentation fix in their first week and a reviewed code change in their first two weeks. "
            "Your onboarding buddy owns unblocking you — use them before filing a ticket. "
            "By day thirty you should have joined an on-call shadow rotation."
        ),
    },
    {
        "id": "doc_pto",
        "datasource": "gdrive",
        "doc_type": "Document",
        "container": "People Ops / Policies",
        "title": "PTO and Leave Policy (FY{FY})",
        "url": "https://docs.google.com/document/d/1PtOpOl1cYaCm3Nq/edit",
        "author": "yuki.tanaka@acme.com",
        "updated_days_ago": 61,
        "tags": ["pto", "policy", "leave", "hr", "benefits"],
        "body": (
            "Full-time employees accrue twenty days of paid time off per year plus company holidays. "
            "Up to five unused days roll into the next year; anything above that expires at the end of January. "
            "Requests over five consecutive days need manager approval two weeks ahead so on-call coverage can be arranged. "
            "Parental leave and sick leave are tracked separately and do not draw down PTO."
        ),
    },
    {
        "id": "doc_interview_loop",
        "datasource": "confluence",
        "doc_type": "Page",
        "container": "PEOPLE space",
        "title": "Interview Loop Guide — Backend Engineering",
        "url": "https://acme.atlassian.net/wiki/spaces/PEOPLE/pages/221580/Interview+Loop+Backend",
        "author": "yuki.tanaka@acme.com",
        "updated_days_ago": 45,
        "tags": ["hiring", "interview", "rubric", "engineering"],
        "body": (
            "The backend loop is four rounds: systems design, coding, debugging a real service, and values. "
            "Interviewers submit written feedback within twenty-four hours and do not read others' feedback first. "
            "The debrief is a discussion, not a vote average; the hiring manager makes the call and writes the rationale."
        ),
    },
    {
        "id": "doc_eng_leads_notes",
        "datasource": "gdrive",
        "doc_type": "Document",
        "container": "Platform Eng / Meetings",
        "title": "Meeting Notes — Weekly Engineering Leads Sync",
        "url": "https://docs.google.com/document/d/1WkLyEngL34dSyNc/edit",
        "author": "priya.raman@acme.com",
        "updated_days_ago": 2,
        "tags": ["meeting notes", "leads", "weekly", "planning"],
        "body": (
            "Running notes from the Monday leads sync, newest at the top. "
            "This week: quarterly planning drafts are behind by two teams, the indexing worker migration slipped a week, "
            "and Security asked for a decision on key rotation before the audit window opens."
        ),
    },

    # ---- security and compliance ----
    {
        "id": "doc_soc2",
        "datasource": "confluence",
        "doc_type": "Page",
        "container": "SEC space",
        "title": "SOC 2 Evidence Collection — Owner Matrix",
        "url": "https://acme.atlassian.net/wiki/spaces/SEC/pages/640117/SOC+2+Evidence+Matrix",
        "author": "nina.kowalski@acme.com",
        "updated_days_ago": 11,
        "tags": ["soc2", "compliance", "audit", "security", "evidence"],
        "body": (
            "Maps each SOC 2 control to the person who owns its evidence and where that evidence lives. "
            "Access reviews are due quarterly; change management evidence is pulled from the deploy log automatically. "
            "The audit window opens six weeks from the last update to this page, and any control without an owner blocks the readiness sign-off."
        ),
    },
    {
        "id": "doc_retention",
        "datasource": "gdrive",
        "doc_type": "Document",
        "container": "Security / Standards",
        "title": "Data Retention Standard v3",
        "url": "https://docs.google.com/document/d/1DaTaRt3Nsh0Nq2/edit",
        "author": "nina.kowalski@acme.com",
        "updated_days_ago": 73,
        "tags": ["retention", "data", "policy", "privacy", "compliance"],
        "body": (
            "Customer content is retained for the life of the contract plus ninety days. "
            "Application logs are kept for thirty days, access logs for one year, and anything containing personal data is minimised at ingest. "
            "Deletion requests are fulfilled within thirty days and are verified by a sampling job that runs monthly."
        ),
    },
    {
        "id": "doc_key_rotation",
        "datasource": "jira",
        "doc_type": "Task",
        "container": "SEC board",
        "title": "SEC-233 — Rotate service account keys before audit window",
        "url": "https://acme.atlassian.net/browse/SEC-233",
        "author": "nina.kowalski@acme.com",
        "updated_days_ago": 5,
        "tags": ["security", "keys", "rotation", "audit", "compliance"],
        "body": (
            "Rotate the eleven long-lived service account keys flagged in the last access review. "
            "Four are used by the indexing worker and need a coordinated deploy so nothing drops mid-rotation. "
            "Blocked on the platform team confirming a maintenance window during quarterly planning."
        ),
    },
    {
        "id": "doc_threat_model",
        "datasource": "github",
        "doc_type": "File",
        "container": "acme/infra",
        "title": "acme/infra — security/threat-model.md",
        "url": "https://github.com/acme/infra/blob/main/security/threat-model.md",
        "author": "nina.kowalski@acme.com",
        "updated_days_ago": 38,
        "tags": ["security", "threat model", "architecture", "review"],
        "body": (
            "Trust boundaries for the platform, written against the STRIDE categories. "
            "The highest-rated risks are token replay against the public API and privilege escalation through the shared indexing service account. "
            "Every new service gets a threat model review before it handles customer data."
        ),
    },

    # ---- product, sales, customers ----
    {
        "id": "doc_roadmap",
        "datasource": "gdrive",
        "doc_type": "Presentation",
        "container": "Product / Roadmap",
        "title": "Product Roadmap — {Q+1} and Beyond",
        "url": "https://docs.google.com/presentation/d/1RdMp8QwNxTz4Vb/edit",
        "author": "marcus.webb@acme.com",
        "updated_days_ago": 7,
        "tags": ["roadmap", "product", "planning", "strategy"],
        "body": (
            "Three bets for {Q+1}: finish the indexing migration, ship granular permissions, and open the public API beta. "
            "Anything not on this page is not committed, no matter what a customer was told in the room. "
            "Dates on the slides are quarter-level, deliberately — team-level dates live in the planning tracker."
        ),
    },
    {
        "id": "doc_pricing",
        "datasource": "gdrive",
        "doc_type": "Document",
        "container": "Revenue / Enablement",
        "title": "Pricing and Packaging FAQ",
        "url": "https://docs.google.com/document/d/1PrIcInGfAq7Zx/edit",
        "author": "theo.lambert@acme.com",
        "updated_days_ago": 21,
        "tags": ["pricing", "packaging", "sales", "faq", "enablement"],
        "body": (
            "Answers to the twenty questions that come up most in deals. "
            "Seat pricing is tiered at 50, 250, and 1000 seats; the platform fee covers two connectors and each additional connector is priced separately. "
            "Discount approval above fifteen percent goes to the deal desk, and anything touching a multi-year term goes to Finance."
        ),
    },
    {
        "id": "doc_battlecard",
        "datasource": "confluence",
        "doc_type": "Page",
        "container": "REV space",
        "title": "Competitive Battlecard — Enterprise Search Vendors",
        "url": "https://acme.atlassian.net/wiki/spaces/REV/pages/410233/Competitive+Battlecard",
        "author": "theo.lambert@acme.com",
        "updated_days_ago": 29,
        "tags": ["competitive", "sales", "battlecard", "enterprise"],
        "body": (
            "How we position against the three vendors we see most in enterprise evaluations. "
            "Lead with permissions fidelity and connector depth; do not lead with model quality, which is table stakes in every bake-off now. "
            "The trap question to expect is about indexing latency on large corpora — the honest answer is in the FAQ section."
        ),
    },
    {
        "id": "doc_rfp_slack",
        "datasource": "slack",
        "doc_type": "Message",
        "container": "#sales-eng",
        "title": "RFP questions for Northwind — security section",
        "url": "https://acme.slack.com/archives/C04SEQ22M/p1719120388",
        "author": "theo.lambert@acme.com",
        "updated_days_ago": 10,
        "tags": ["rfp", "sales", "security", "customer"],
        "body": (
            "Northwind's RFP has fourteen security questions due Friday. "
            "Most map to the SOC 2 evidence matrix, but two are about data retention and I want Security to review the wording before it goes out. "
            "Also asking for our incident response SLA, which I do not think we have published anywhere."
        ),
    },
    {
        "id": "doc_qbr_northwind",
        "datasource": "gdrive",
        "doc_type": "Document",
        "container": "Customer Success / Accounts",
        "title": "Customer QBR — Northwind Retail",
        "url": "https://docs.google.com/document/d/1NwQbR5tLmXq8/edit",
        "author": "rosa.mendez@acme.com",
        "updated_days_ago": 16,
        "tags": ["qbr", "customer", "northwind", "renewal", "adoption"],
        "body": (
            "Adoption is up to 68 percent weekly active across their 2,400 licensed seats, from 51 percent last quarter. "
            "Two open risks going into renewal: the checkout incident in June and slow connector sync on their Confluence instance. "
            "They want a roadmap conversation about granular permissions before they commit to a multi-year term."
        ),
    },

    # ---- platform engineering ----
    {
        "id": "doc_api_search",
        "datasource": "github",
        "doc_type": "File",
        "container": "acme/platform",
        "title": "acme/platform — docs/api/search.md",
        "url": "https://github.com/acme/platform/blob/main/docs/api/search.md",
        "author": "priya.raman@acme.com",
        "updated_days_ago": 13,
        "tags": ["api", "search", "documentation", "platform"],
        "body": (
            "Reference for the internal search API: request shape, page size limits, facet filters, and tracking tokens. "
            "Page size is capped at 100 per request and cursors expire after five minutes. "
            "Every result carries a tracking token that must be echoed on feedback calls, otherwise ranking signals are dropped."
        ),
    },
    {
        "id": "doc_pr_indexer",
        "datasource": "github",
        "doc_type": "Pull Request",
        "container": "acme/platform",
        "title": "acme/platform#2033 — Migrate indexing worker to async queue",
        "url": "https://github.com/acme/platform/pull/2033",
        "author": "priya.raman@acme.com",
        "updated_days_ago": 3,
        "tags": ["indexing", "migration", "platform", "queue", "performance"],
        "body": (
            "Replaces the cron-driven indexing worker with an async queue consumer. "
            "Cuts median document freshness from eleven minutes to under ninety seconds and removes the thundering-herd problem at the top of each hour. "
            "Rollout is per-datasource behind a flag, starting with the smallest connector."
        ),
    },
    {
        "id": "doc_indexer_ticket",
        "datasource": "jira",
        "doc_type": "Story",
        "container": "PLAT board",
        "title": "PLAT-908 — Migrate indexing worker off cron",
        "url": "https://acme.atlassian.net/browse/PLAT-908",
        "author": "sam.iyer@acme.com",
        "updated_days_ago": 3,
        "tags": ["indexing", "migration", "platform", "quarterly"],
        "body": (
            "Committed work for the quarter: move the indexing worker to the async queue and retire the cron entry. "
            "Slipped one week because the key rotation work needs the same maintenance window. "
            "Exit criteria are freshness under two minutes at p95 and no increase in connector error rate."
        ),
    },
    {
        "id": "doc_budget_model",
        "datasource": "gdrive",
        "doc_type": "Spreadsheet",
        "container": "Finance / Models",
        "title": "Headcount and Budget Model FY{FY}",
        "url": "https://docs.google.com/spreadsheets/d/1HcBdG7tMdLfY/edit#gid=2",
        "author": "dana.ortiz@acme.com",
        "updated_days_ago": 15,
        "tags": ["budget", "headcount", "finance", "planning", "capacity"],
        "body": (
            "Approved headcount by team with start-date assumptions, fully loaded cost, and the resulting engineer-week capacity per quarter. "
            "Nine open requisitions, six of them in Platform. "
            "This model feeds the quarterly planning capacity numbers — change it here, not in the planning tracker."
        ),
    },
    {
        "id": "doc_connector_status",
        "datasource": "confluence",
        "doc_type": "Page",
        "container": "PLAT space",
        "title": "Connector Health Dashboard — Weekly Notes",
        "url": "https://acme.atlassian.net/wiki/spaces/PLAT/pages/560788/Connector+Health",
        "author": "sam.iyer@acme.com",
        "updated_days_ago": 5,
        "tags": ["connectors", "indexing", "health", "platform", "sync"],
        "body": (
            "Weekly review of connector sync lag and error rates across the five production datasources. "
            "Confluence sync is the slow one at 40 minutes p95, mostly attachment fetches. "
            "Slack and Jira are both under five minutes. Github re-indexes on webhook and is effectively real time."
        ),
    },

    # ---- engineering process and architecture ----
    {
        "id": "doc_deploy_process",
        "datasource": "confluence",
        "doc_type": "Page",
        "container": "ENG space",
        "title": "Deploy and Release Process",
        "url": "https://acme.atlassian.net/wiki/spaces/ENG/pages/498201/Deploy+and+Release+Process",
        "author": "priya.raman@acme.com",
        "updated_days_ago": 20,
        "tags": ["deploy", "release", "process", "ci", "rollback"],
        "body": (
            "Every change ships behind a flag and rolls out to ten percent of traffic for thirty minutes before going wide. "
            "The deploy gate blocks any service missing an owner in the service catalog. "
            "Rollback is a single command and never needs an incident to be declared first — roll back, then investigate."
        ),
    },
    {
        "id": "doc_arch_decisions",
        "datasource": "confluence",
        "doc_type": "Page",
        "container": "PLAT space",
        "title": "Architecture Decision Log",
        "url": "https://acme.atlassian.net/wiki/spaces/PLAT/pages/524610/Architecture+Decision+Log",
        "author": "priya.raman@acme.com",
        "updated_days_ago": 41,
        "tags": ["architecture", "adr", "decisions", "platform", "history"],
        "body": (
            "One entry per architectural decision: the context, the options considered, the call, and who made it. "
            "Recent entries cover the move to an async indexing queue, per-tenant index sharding, and the choice to keep permissions checks synchronous. "
            "Decisions are never edited after the fact — superseded ones get a new entry that links back."
        ),
    },
    {
        "id": "doc_sev_levels",
        "datasource": "confluence",
        "doc_type": "Page",
        "container": "SRE space",
        "title": "Incident Severity Levels and Comms Templates",
        "url": "https://acme.atlassian.net/wiki/spaces/SRE/pages/783440/Incident+Severity+Levels",
        "author": "sam.iyer@acme.com",
        "updated_days_ago": 26,
        "tags": ["incident", "severity", "comms", "oncall", "process"],
        "body": (
            "Sev-1 is customer-visible data loss or a full outage and pages the incident commander immediately. "
            "Sev-2 is degraded service for a subset of customers, which is where most checkout and connector incidents land. "
            "Sev-3 is internal-only impact. Each level has a customer comms template and a required update cadence — thirty minutes for Sev-1, hourly for Sev-2."
        ),
    },
    {
        "id": "doc_access_review",
        "datasource": "confluence",
        "doc_type": "Page",
        "container": "SEC space",
        "title": "Quarterly Access Review Procedure",
        "url": "https://acme.atlassian.net/wiki/spaces/SEC/pages/651903/Quarterly+Access+Review",
        "author": "nina.kowalski@acme.com",
        "updated_days_ago": 18,
        "tags": ["access review", "security", "compliance", "audit", "quarterly"],
        "body": (
            "Every quarter, each system owner confirms who still needs access to what and revokes the rest. "
            "The review covers production databases, cloud accounts, the admin console, and all long-lived service account keys. "
            "Evidence lands in the SOC 2 matrix automatically; a review that misses its window becomes an audit finding."
        ),
    },
    {
        "id": "doc_support_kb",
        "datasource": "confluence",
        "doc_type": "Page",
        "container": "SUP space",
        "title": "Support Knowledge Base — Top 20 Customer Questions",
        "url": "https://acme.atlassian.net/wiki/spaces/SUP/pages/340118/Support+Knowledge+Base",
        "author": "rosa.mendez@acme.com",
        "updated_days_ago": 12,
        "tags": ["support", "knowledge base", "faq", "customer", "troubleshooting"],
        "body": (
            "The twenty questions that account for roughly seventy percent of inbound tickets, with the answer and the escalation path for each. "
            "The top three are always about missing search results, connector sync delays, and permission mismatches after an org change. "
            "Anything answered here three times in a week becomes a candidate for a published Answer."
        ),
    },

    # ---- policies, research, planning artefacts ----
    {
        "id": "doc_expense_policy",
        "datasource": "gdrive",
        "doc_type": "Document",
        "container": "Finance / Policies",
        "title": "Travel and Expense Policy",
        "url": "https://docs.google.com/document/d/1TrVeXp3NsPl9Cy/edit",
        "author": "dana.ortiz@acme.com",
        "updated_days_ago": 88,
        "tags": ["expenses", "travel", "policy", "finance", "approvals"],
        "body": (
            "Anything under 200 dollars is self-approved with a receipt; above that needs manager approval before the spend, not after. "
            "Team offsites and customer travel are budgeted per quarter and tracked against the same model that feeds planning. "
            "Reimbursements are paid on the next payroll run after approval."
        ),
    },
    {
        "id": "doc_user_research",
        "datasource": "gdrive",
        "doc_type": "Document",
        "container": "Product / Research",
        "title": "User Research Findings — Search Relevance Interviews",
        "url": "https://docs.google.com/document/d/1UsRs3ArCh8Fn/edit",
        "author": "marcus.webb@acme.com",
        "updated_days_ago": 19,
        "tags": ["research", "search", "relevance", "product", "interviews"],
        "body": (
            "Fourteen interviews across six customers about why people abandon a search. "
            "The dominant complaint is not ranking quality but staleness — results that point at a document edited three weeks ago read as broken. "
            "Second is permissions confusion: seeing a title you cannot open erodes trust faster than seeing nothing at all."
        ),
    },
    {
        "id": "doc_support_playbook",
        "datasource": "gdrive",
        "doc_type": "Document",
        "container": "Support / Playbooks",
        "title": "Support Escalation Playbook",
        "url": "https://docs.google.com/document/d/1SuPpEsC4LaT7n/edit",
        "author": "rosa.mendez@acme.com",
        "updated_days_ago": 33,
        "tags": ["support", "escalation", "playbook", "sla", "customer"],
        "body": (
            "When a ticket needs engineering, support files against the owning team's board and links the customer thread. "
            "Enterprise accounts carry a four-hour first-response SLA and a named escalation contact. "
            "Anything that looks like an outage goes to the on-call rotation directly rather than waiting in the queue."
        ),
    },
    {
        "id": "doc_okr_scorecard",
        "datasource": "gdrive",
        "doc_type": "Spreadsheet",
        "container": "Company / OKRs",
        "title": "{Q} OKR Scorecard — Company",
        "url": "https://docs.google.com/spreadsheets/d/1OkRsC0rDcRd2/edit#gid=1",
        "author": "marcus.webb@acme.com",
        "updated_days_ago": 6,
        "tags": ["okr", "scorecard", "metrics", "quarterly", "planning"],
        "body": (
            "Scored weekly against the objectives locked at the start of {Q}. "
            "Green is on track, amber means the owner has a recovery plan, red means the objective is being renegotiated at the next review. "
            "Two of nine company objectives are amber this week, both waiting on the indexing migration."
        ),
    },

    # ---- platform and connector work (jira) ----
    {
        "id": "doc_jira_sharding",
        "datasource": "jira",
        "doc_type": "Story",
        "container": "PLAT board",
        "title": "PLAT-914 — Shard the search index by tenant",
        "url": "https://acme.atlassian.net/browse/PLAT-914",
        "author": "sam.iyer@acme.com",
        "updated_days_ago": 7,
        "tags": ["indexing", "sharding", "platform", "scale", "search"],
        "body": (
            "Split the single index into per-tenant shards so a large customer's re-index stops slowing everyone else's queries. "
            "Depends on the async indexing queue landing first. "
            "Exit criteria are no cross-tenant query interference under a full re-index and no regression in p95 query latency."
        ),
    },
    {
        "id": "doc_jira_coldstart",
        "datasource": "jira",
        "doc_type": "Story",
        "container": "PLAT board",
        "title": "PLAT-931 — Reduce cold-start latency on the query service",
        "url": "https://acme.atlassian.net/browse/PLAT-931",
        "author": "priya.raman@acme.com",
        "updated_days_ago": 4,
        "tags": ["latency", "performance", "platform", "query", "startup"],
        "body": (
            "First query after a deploy takes 2.4 seconds because the permissions cache starts empty. "
            "Plan is to warm the cache during the rollout window before the instance takes traffic. "
            "Target is under 400ms for the first query, matching steady state."
        ),
    },
    {
        "id": "doc_jira_slack_stall",
        "datasource": "jira",
        "doc_type": "Incident",
        "container": "INC board",
        "title": "INC-1207 — Slack connector sync stalled for six hours",
        "url": "https://acme.atlassian.net/browse/INC-1207",
        "author": "sam.iyer@acme.com",
        "updated_days_ago": 22,
        "tags": ["incident", "connectors", "slack", "sync", "sev3"],
        "body": (
            "The Slack connector stopped advancing its cursor after a rate-limit response it did not retry. "
            "Six hours of messages were missing from search before the sync lag alert fired. "
            "Backfill completed cleanly; the missing retry is tracked on the connector board."
        ),
    },
    {
        "id": "doc_jira_dupes",
        "datasource": "jira",
        "doc_type": "Incident",
        "container": "INC board",
        "title": "INC-1219 — Duplicate documents after Confluence re-index",
        "url": "https://acme.atlassian.net/browse/INC-1219",
        "author": "sam.iyer@acme.com",
        "updated_days_ago": 11,
        "tags": ["incident", "confluence", "indexing", "duplicates", "sev3"],
        "body": (
            "A full Confluence re-index produced two entries for every page whose title contained a slash. "
            "Root cause was id derivation from the page path rather than the page id. "
            "Deduplicated in place; the connector checklist now calls out stable id derivation explicitly."
        ),
    },
    {
        "id": "doc_jira_mfa",
        "datasource": "jira",
        "doc_type": "Task",
        "container": "SEC board",
        "title": "SEC-241 — Enforce MFA on internal service dashboards",
        "url": "https://acme.atlassian.net/browse/SEC-241",
        "author": "nina.kowalski@acme.com",
        "updated_days_ago": 16,
        "tags": ["security", "mfa", "access", "dashboards", "compliance"],
        "body": (
            "Four internal dashboards still accept password-only sign-in, including the connector admin console. "
            "Enforcement lands behind SSO with a two-week grace period and a banner warning. "
            "Required for the access review to pass this quarter."
        ),
    },
    {
        "id": "doc_jira_dep_audit",
        "datasource": "jira",
        "doc_type": "Task",
        "container": "SEC board",
        "title": "SEC-256 — Third-party dependency audit for {Q+1}",
        "url": "https://acme.atlassian.net/browse/SEC-256",
        "author": "nina.kowalski@acme.com",
        "updated_days_ago": 2,
        "tags": ["security", "dependencies", "audit", "supply chain", "compliance"],
        "body": (
            "Review every direct dependency across the platform, payments, and connector repositories for known advisories and maintenance status. "
            "Anything unmaintained for over a year gets an owner and a replacement plan. "
            "Output feeds the SOC 2 evidence matrix and the {Q+1} security roadmap."
        ),
    },
    {
        "id": "doc_jira_headcount",
        "datasource": "jira",
        "doc_type": "Task",
        "container": "PLAN board",
        "title": "PLAN-497 — Define engineering headcount asks for {Q+1}",
        "url": "https://acme.atlassian.net/browse/PLAN-497",
        "author": "dana.ortiz@acme.com",
        "updated_days_ago": 8,
        "tags": ["headcount", "planning", "finance", "hiring", "quarterly"],
        "body": (
            "Each director submits ranked headcount asks with the work that does not happen if the requisition is not approved. "
            "Nine open requisitions carry over from this quarter, six of them in Platform. "
            "Asks are due before the capacity model is locked, not after."
        ),
    },
    {
        "id": "doc_jira_northwind",
        "datasource": "jira",
        "doc_type": "Bug",
        "container": "SUP board",
        "title": "SUP-882 — Northwind: search results missing Confluence attachments",
        "url": "https://acme.atlassian.net/browse/SUP-882",
        "author": "rosa.mendez@acme.com",
        "updated_days_ago": 6,
        "tags": ["support", "northwind", "confluence", "attachments", "customer"],
        "body": (
            "Northwind reports that PDFs attached to Confluence pages never appear in search, though the pages themselves do. "
            "Reproduced on their instance: attachment fetch times out on files over 20MB and the connector drops them silently. "
            "Escalated to the connector team; this is the second of two risks flagged going into their renewal."
        ),
    },
    {
        "id": "doc_jira_perm_tests",
        "datasource": "jira",
        "doc_type": "Story",
        "container": "PLAT board",
        "title": "PLAT-902 — Add permissions fidelity tests to the connector suite",
        "url": "https://acme.atlassian.net/browse/PLAT-902",
        "author": "priya.raman@acme.com",
        "updated_days_ago": 30,
        "tags": ["permissions", "testing", "connectors", "platform", "quality"],
        "body": (
            "Every connector needs a test proving that a user who cannot open a document in the source system cannot see it in search. "
            "Today this is verified by hand at connector launch and never again. "
            "The suite runs per-connector on every release and blocks the deploy on any leak."
        ),
    },
    {
        "id": "doc_jira_roi",
        "datasource": "jira",
        "doc_type": "Task",
        "container": "REV board",
        "title": "REV-141 — Build an ROI calculator for enterprise deals",
        "url": "https://acme.atlassian.net/browse/REV-141",
        "author": "theo.lambert@acme.com",
        "updated_days_ago": 24,
        "tags": ["sales", "roi", "enablement", "enterprise", "pricing"],
        "body": (
            "Sales needs a defensible model for time-saved-per-seat to use in enterprise evaluations. "
            "Inputs are seat count, average searches per week, and the customer's loaded hourly cost. "
            "Numbers have to be sourced from the research findings, not invented in the room."
        ),
    },

    # ---- repositories and pull requests (github) ----
    {
        "id": "doc_gh_slack_backfill",
        "datasource": "github",
        "doc_type": "Pull Request",
        "container": "acme/connectors",
        "title": "acme/connectors#412 — Slack connector: backfill thread replies",
        "url": "https://github.com/acme/connectors/pull/412",
        "author": "sam.iyer@acme.com",
        "updated_days_ago": 9,
        "tags": ["slack", "connectors", "backfill", "threads", "indexing"],
        "body": (
            "Thread replies were only indexed if they arrived after the connector was installed, so historical threads looked empty. "
            "This walks the reply history for every parent message during backfill. "
            "Adds retry-with-backoff on rate limits, which is what stalled the sync in INC-1207."
        ),
    },
    {
        "id": "doc_gh_shard_writer",
        "datasource": "github",
        "doc_type": "Pull Request",
        "container": "acme/platform",
        "title": "acme/platform#2051 — Add tenant sharding to the index writer",
        "url": "https://github.com/acme/platform/pull/2051",
        "author": "priya.raman@acme.com",
        "updated_days_ago": 5,
        "tags": ["indexing", "sharding", "platform", "writer", "scale"],
        "body": (
            "Routes writes to a per-tenant shard keyed on tenant id, with a compatibility path that reads from both during migration. "
            "Implements the first half of PLAT-914; the query side lands separately. "
            "Rolls out one tenant at a time, smallest first, behind the platform.sharding flag."
        ),
    },
    {
        "id": "doc_gh_chat_api",
        "datasource": "github",
        "doc_type": "File",
        "container": "acme/platform",
        "title": "acme/platform — docs/api/chat.md",
        "url": "https://github.com/acme/platform/blob/main/docs/api/chat.md",
        "author": "priya.raman@acme.com",
        "updated_days_ago": 17,
        "tags": ["api", "chat", "documentation", "platform", "citations"],
        "body": (
            "Reference for the chat API: message fragments, thread continuation via chat id, streaming, and the citation shape. "
            "Every answer carries source documents; clients are expected to render them rather than hide them. "
            "Thread ids expire after thirty days of inactivity."
        ),
    },
    {
        "id": "doc_gh_queue_readme",
        "datasource": "github",
        "doc_type": "File",
        "container": "acme/infra",
        "title": "acme/infra — terraform/modules/queue/README.md",
        "url": "https://github.com/acme/infra/blob/main/terraform/modules/queue/README.md",
        "author": "sam.iyer@acme.com",
        "updated_days_ago": 28,
        "tags": ["infrastructure", "terraform", "queue", "indexing", "runbook"],
        "body": (
            "Terraform module for the async indexing queue: sizing, dead-letter configuration, and alarm thresholds. "
            "Consumers are expected to be idempotent — the queue guarantees at-least-once delivery, not exactly-once. "
            "Includes the drain procedure used during maintenance windows."
        ),
    },
    {
        "id": "doc_gh_ds_badge",
        "datasource": "github",
        "doc_type": "Pull Request",
        "container": "acme/web",
        "title": "acme/web#788 — Search results: show datasource badge",
        "url": "https://github.com/acme/web/pull/788",
        "author": "marcus.webb@acme.com",
        "updated_days_ago": 13,
        "tags": ["frontend", "search", "ui", "datasource", "results"],
        "body": (
            "Adds a per-result badge naming the source system, which came directly out of the relevance interviews. "
            "Users could not tell whether a result was a Slack message or a document until they clicked it. "
            "Badge sits next to the freshness label so both signals read together."
        ),
    },
    {
        "id": "doc_gh_connector_checklist",
        "datasource": "github",
        "doc_type": "File",
        "container": "acme/connectors",
        "title": "acme/connectors — docs/connector-checklist.md",
        "url": "https://github.com/acme/connectors/blob/main/docs/connector-checklist.md",
        "author": "sam.iyer@acme.com",
        "updated_days_ago": 36,
        "tags": ["connectors", "checklist", "permissions", "indexing", "quality"],
        "body": (
            "What a connector must do before it ships: stable document ids, permission mapping, incremental sync, and a backfill path. "
            "Ids must derive from the source system's own id, never from a title or path — that is what produced the duplicate pages in INC-1219. "
            "Every item needs a test, not an assertion in the pull request description."
        ),
    },
    {
        "id": "doc_gh_idempotent_charges",
        "datasource": "github",
        "doc_type": "Pull Request",
        "container": "acme/payments",
        "title": "acme/payments#1902 — Make charge retries idempotent",
        "url": "https://github.com/acme/payments/pull/1902",
        "author": "sam.iyer@acme.com",
        "updated_days_ago": 6,
        "tags": ["payments", "idempotency", "retries", "reliability", "charges"],
        "body": (
            "Attaches a client-generated idempotency key to every charge so a retry cannot double-charge. "
            "This is PAY-4419, the blocker called out in the payments runbook — once it lands, restarting the worker pool mid-spike stops being dangerous. "
            "Keys are held for 24 hours, which covers every retry path we have."
        ),
    },
    {
        "id": "doc_gh_perm_cache",
        "datasource": "github",
        "doc_type": "Pull Request",
        "container": "acme/platform",
        "title": "acme/platform#2077 — Cache permission checks per request",
        "url": "https://github.com/acme/platform/pull/2077",
        "author": "priya.raman@acme.com",
        "updated_days_ago": 2,
        "tags": ["permissions", "performance", "cache", "platform", "latency"],
        "body": (
            "A single search was making one permission call per result, up to a hundred per query. "
            "This caches checks for the life of the request, cutting median query time by 180ms. "
            "Cache is per-request by design — nothing is held across requests, so a revoked grant takes effect immediately."
        ),
    },
    {
        "id": "doc_gh_ci_keys",
        "datasource": "github",
        "doc_type": "Pull Request",
        "container": "acme/infra",
        "title": "acme/infra#644 — Rotate CI signing keys",
        "url": "https://github.com/acme/infra/pull/644",
        "author": "nina.kowalski@acme.com",
        "updated_days_ago": 15,
        "tags": ["security", "ci", "keys", "rotation", "infrastructure"],
        "body": (
            "Rotates the build signing keys and moves them out of the CI environment into the secret manager. "
            "Part of the key rotation work tracked in SEC-233, scheduled for the same maintenance window. "
            "Old keys stay valid for seven days so in-flight artefacts still verify."
        ),
    },
    {
        "id": "doc_gh_accessibility",
        "datasource": "github",
        "doc_type": "File",
        "container": "acme/web",
        "title": "acme/web — docs/accessibility.md",
        "url": "https://github.com/acme/web/blob/main/docs/accessibility.md",
        "author": "marcus.webb@acme.com",
        "updated_days_ago": 44,
        "tags": ["accessibility", "frontend", "wcag", "standards", "ui"],
        "body": (
            "Accessibility standards for the web client, targeting WCAG 2.2 AA. "
            "Search results must be navigable by keyboard alone and every interactive element needs a visible focus state. "
            "Colour is never the only signal — the datasource badge carries text, not just a hue."
        ),
    },

    # ---- channel conversation (slack) ----
    {
        "id": "doc_slack_freeze",
        "datasource": "slack",
        "doc_type": "Message",
        "container": "#eng-general",
        "title": "Deploy freeze during the audit window",
        "url": "https://acme.slack.com/archives/C01ENGGEN/p1719901220",
        "author": "priya.raman@acme.com",
        "updated_days_ago": 5,
        "tags": ["deploy", "freeze", "audit", "process", "announcement"],
        "body": (
            "We are freezing non-critical deploys for the three days the auditors are collecting evidence. "
            "Security fixes and incident mitigations are exempt and do not need to ask. "
            "If your change is already behind a flag, ship the code and hold the flag — that is not a deploy for these purposes."
        ),
    },
    {
        "id": "doc_slack_sharding",
        "datasource": "slack",
        "doc_type": "Message",
        "container": "#platform",
        "title": "Index sharding rollout plan",
        "url": "https://acme.slack.com/archives/C02PLATF9/p1719989410",
        "author": "sam.iyer@acme.com",
        "updated_days_ago": 4,
        "tags": ["sharding", "indexing", "rollout", "platform", "migration"],
        "body": (
            "Rollout order is smallest tenant first, one per day, with a full day of soak between each. "
            "We read from both the old index and the new shard during migration, so a bad shard degrades to the old path rather than losing results. "
            "Northwind goes last because their corpus is four times the next largest."
        ),
    },
    {
        "id": "doc_slack_mfa",
        "datasource": "slack",
        "doc_type": "Message",
        "container": "#security",
        "title": "MFA enforcement rollout — two week grace period",
        "url": "https://acme.slack.com/archives/C03SECOPS/p1719120088",
        "author": "nina.kowalski@acme.com",
        "updated_days_ago": 14,
        "tags": ["security", "mfa", "rollout", "access", "announcement"],
        "body": (
            "MFA becomes mandatory on the internal dashboards in two weeks, including the connector admin console. "
            "You will see a banner every sign-in until you enrol. "
            "If you own a service account that signs in interactively, that is the thing to fix now rather than the day enforcement lands."
        ),
    },
    {
        "id": "doc_slack_support_northwind",
        "datasource": "slack",
        "doc_type": "Message",
        "container": "#support",
        "title": "Northwind attachment issue — need connector eyes",
        "url": "https://acme.slack.com/archives/C04SUPRT2/p1719880155",
        "author": "rosa.mendez@acme.com",
        "updated_days_ago": 6,
        "tags": ["support", "northwind", "attachments", "escalation", "confluence"],
        "body": (
            "Northwind's attachments still are not showing up in search and their renewal conversation is in three weeks. "
            "Filed as SUP-882 with a reproduction on their instance — large PDFs time out during the attachment fetch. "
            "Can someone from connectors pick this up today rather than leaving it in the queue?"
        ),
    },
    {
        "id": "doc_slack_roadmap_review",
        "datasource": "slack",
        "doc_type": "Message",
        "container": "#product",
        "title": "Roadmap review notes — three bets confirmed",
        "url": "https://acme.slack.com/archives/C05PRODCT/p1719720900",
        "author": "marcus.webb@acme.com",
        "updated_days_ago": 8,
        "tags": ["roadmap", "product", "review", "planning", "notes"],
        "body": (
            "Confirmed the three bets for {Q+1}: finish the indexing migration, ship granular permissions, open the public API beta. "
            "Everything else moves to the parked list, including the reporting work two teams had already started scoping. "
            "If you promised a customer something not on that list, tell me before they hear it from someone else."
        ),
    },
    {
        "id": "doc_slack_hiring",
        "datasource": "slack",
        "doc_type": "Message",
        "container": "#hiring",
        "title": "Backend loop debriefs — please submit feedback first",
        "url": "https://acme.slack.com/archives/C06HIRING/p1718650440",
        "author": "yuki.tanaka@acme.com",
        "updated_days_ago": 21,
        "tags": ["hiring", "interview", "debrief", "feedback", "process"],
        "body": (
            "Three debriefs slipped this week because feedback was not in before the meeting. "
            "Write yours within twenty-four hours and do not read anyone else's first — that is the whole point of the format. "
            "If you cannot make the debrief, submit feedback anyway and the hiring manager will read it out."
        ),
    },
    {
        "id": "doc_slack_retry_budget",
        "datasource": "slack",
        "doc_type": "Message",
        "container": "#incident-checkout",
        "title": "Follow-up: retry budget change is live",
        "url": "https://acme.slack.com/archives/C03INC118/p1719300777",
        "author": "sam.iyer@acme.com",
        "updated_days_ago": 12,
        "tags": ["incident", "checkout", "retries", "postmortem", "followup"],
        "body": (
            "The explicit retry budget from the INC-1183 action items is deployed. "
            "Retries are now capped per request rather than per client, which is what let the pool exhaust itself last time. "
            "Two action items left: the p99 alert is done, the circuit breaker is still behind a flag pending the runbook update."
        ),
    },
    {
        "id": "doc_slack_capacity_q",
        "datasource": "slack",
        "doc_type": "Message",
        "container": "#planning",
        "title": "Questions on the capacity model numbers",
        "url": "https://acme.slack.com/archives/C02PLAN9K/p1719650300",
        "author": "dana.ortiz@acme.com",
        "updated_days_ago": 7,
        "tags": ["planning", "capacity", "finance", "questions", "quarterly"],
        "body": (
            "A few teams are asking why their available engineer-weeks dropped compared with last quarter. "
            "Short answer: the new model subtracts on-call and interview time, which the old spreadsheet ignored. "
            "The numbers are lower but they are real — please plan against them rather than the old ones."
        ),
    },
    {
        "id": "doc_slack_demo_env",
        "datasource": "slack",
        "doc_type": "Message",
        "container": "#sales-eng",
        "title": "Demo environment refreshed for the quarter",
        "url": "https://acme.slack.com/archives/C04SEQ22M/p1720051133",
        "author": "theo.lambert@acme.com",
        "updated_days_ago": 3,
        "tags": ["demo", "sales", "environment", "enablement", "refresh"],
        "body": (
            "The demo tenant has fresh content across all five connectors and the datasource badges are enabled. "
            "Please do not run live demos against a customer's own instance — use this one, it is stable and the data is ours. "
            "Ping me if you need a scenario that is not covered."
        ),
    },
    {
        "id": "doc_slack_new_starters",
        "datasource": "slack",
        "doc_type": "Message",
        "container": "#eng-general",
        "title": "New starters this week — say hello",
        "url": "https://acme.slack.com/archives/C01ENGGEN/p1720120800",
        "author": "yuki.tanaka@acme.com",
        "updated_days_ago": 2,
        "tags": ["onboarding", "new hire", "announcement", "team"],
        "body": (
            "Two engineers joined Platform this week and one joined Payments. "
            "Buddies are assigned and the first-thirty-days page is in their onboarding checklist. "
            "They each ship a documentation fix this week, so expect small pull requests from unfamiliar names."
        ),
    },
    {
        "id": "doc_slack_sync_lag",
        "datasource": "slack",
        "doc_type": "Message",
        "container": "#platform",
        "title": "Connector sync lag dashboard is live",
        "url": "https://acme.slack.com/archives/C02PLATF9/p1719480222",
        "author": "sam.iyer@acme.com",
        "updated_days_ago": 10,
        "tags": ["connectors", "monitoring", "sync", "dashboard", "platform"],
        "body": (
            "Sync lag per connector is now on a dashboard instead of buried in the weekly notes. "
            "Alerts fire at thirty minutes of lag for Slack and Jira, ninety for Confluence given the attachment fetches. "
            "This is the alert that should have caught the six-hour Slack stall in INC-1207."
        ),
    },
]


# -------------------- time and placeholder helpers --------------------

def _now() -> float:
    return time.time()


def _quarter_label(offset: int = 0) -> str:
    """Return a label like 'Q3 FY26' for the current quarter plus offset."""
    tm = time.gmtime(_now())
    index = (tm.tm_year * 4) + ((tm.tm_mon - 1) // 3) + offset
    year, quarter = divmod(index, 4)
    return f"Q{quarter + 1} FY{year % 100:02d}"


def _fiscal_year() -> str:
    return f"{time.gmtime(_now()).tm_year % 100:02d}"


def expand(text: str) -> str:
    """Expand {Q}, {Q+1}, {Q+2} and {FY} placeholders in corpus text."""
    if "{" not in text:
        return text
    for offset in (2, 1):
        text = text.replace("{Q+%d}" % offset, _quarter_label(offset))
    return text.replace("{Q}", _quarter_label(0)).replace("{FY}", _fiscal_year())


def _epoch_days_ago(days: int) -> int:
    return int(_now() - days * 86400)


def ago(days: int) -> str:
    """Human phrasing for a document age, e.g. 'updated 3 days ago'."""
    if days <= 0:
        return "updated today"
    if days == 1:
        return "updated yesterday"
    if days < 30:
        return f"updated {days} days ago"
    if days < 60:
        return "updated last month"
    return f"updated {days // 30} months ago"


# -------------------- corpus loading --------------------

_active: Optional[Dict[str, Any]] = None
_active_key: Optional[str] = None   # the path the cached corpus came from
_override_path: Optional[str] = None


def use_path(path: Optional[str]) -> None:
    """Set the corpus file path (from config). None falls back to env/built-in."""
    global _override_path
    _override_path = path or None


def _corpus_path() -> Optional[str]:
    return _override_path or os.environ.get(CORPUS_ENV_VAR) or None


def _normalise_doc(raw: Dict[str, Any], index: int) -> Dict[str, Any]:
    if not isinstance(raw, dict) or not raw.get("title"):
        raise CorpusError(f"document {index} is missing a title")
    doc = dict(raw)
    doc.setdefault("id", f"doc_{index + 1}")
    doc.setdefault("datasource", "gdrive")
    doc.setdefault("doc_type", "Document")
    doc.setdefault("container", "")
    doc.setdefault("url", f"https://{COMPANY.lower()}.example.com/doc/{doc['id']}")
    doc.setdefault("author", "")   # bylines simply omit an author we don't have
    doc.setdefault("updated_days_ago", index)
    doc.setdefault("tags", [])
    doc.setdefault("body", doc["title"])
    return doc


def _load_file(path: str) -> Dict[str, Any]:
    try:
        raw = json.loads(Path(path).expanduser().read_text())
    except FileNotFoundError:
        raise CorpusError(f"mock corpus file not found: {path}") from None
    except json.JSONDecodeError as e:
        raise CorpusError(f"mock corpus file is not valid JSON ({path}): {e}") from None
    except OSError as e:
        raise CorpusError(f"could not read mock corpus file ({path}): {e}") from None

    docs = raw.get("documents") if isinstance(raw, dict) else raw
    if not isinstance(docs, list) or not docs:
        raise CorpusError(f"mock corpus file has no documents: {path}")

    people = dict(PEOPLE)
    if isinstance(raw, dict) and isinstance(raw.get("people"), dict):
        people.update(raw["people"])
    counts = dict(DATASOURCE_COUNTS)
    if isinstance(raw, dict) and isinstance(raw.get("datasourceCounts"), dict):
        counts = {k: int(v) for k, v in raw["datasourceCounts"].items()}

    return {
        "documents": [_normalise_doc(d, i) for i, d in enumerate(docs)],
        "people": people,
        "counts": counts,
    }


def corpus() -> Dict[str, Any]:
    """Return the active corpus, loading a user-supplied file if configured."""
    global _active, _active_key
    key = _corpus_path()
    if _active is not None and _active_key == key:
        return _active
    _active = _load_file(key) if key else {
        "documents": DOCS,
        "people": PEOPLE,
        "counts": DATASOURCE_COUNTS,
    }
    _active_key = key
    return _active


def documents() -> List[Dict[str, Any]]:
    return corpus()["documents"]


def roster() -> Dict[str, Dict[str, str]]:
    return corpus()["people"]


def reset() -> None:
    """Drop the cached corpus (used by tests)."""
    global _active, _active_key
    _active = None
    _active_key = None


# -------------------- ranking --------------------

_WORD_RE = re.compile(r"[a-z0-9]+")

_STOPWORDS = frozenset("""
a an and are as at be by do does for from how has have i in is it its me my of on or our
the their there this to us was we what when where which who why will with you your
""".split())


def _tokens(text: str) -> List[str]:
    return [w for w in _WORD_RE.findall(text.lower()) if w not in _STOPWORDS]


def _score(doc: Dict[str, Any], query_tokens: List[str], query_text: str) -> int:
    title = expand(doc["title"]).lower()
    body = doc["body"].lower()
    title_words = set(_WORD_RE.findall(title))
    body_words = set(_WORD_RE.findall(body))
    tags = {t.lower() for t in doc.get("tags", [])}
    tag_words = set(_WORD_RE.findall(" ".join(tags)))

    score = 0
    for token in query_tokens:
        if token in title_words:
            score += 6
        elif any(w.startswith(token) for w in title_words):
            score += 3
        if token in tag_words:
            score += 4
        if token in body_words:
            score += 2
        if token == doc["datasource"] or token in doc.get("container", "").lower():
            score += 3
    if query_text:
        if query_text in title:
            score += 8
        elif query_text in body or query_text in " ".join(sorted(tags)):
            score += 4
    return score


def _snippet(doc: Dict[str, Any], query_tokens: List[str], limit: int = 220) -> str:
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", doc["body"]) if s.strip()]
    if not sentences:
        return expand(doc["title"])
    best_i = 0
    if query_tokens:
        best_hits = -1
        for i, sentence in enumerate(sentences):
            words = set(_WORD_RE.findall(sentence.lower()))
            hits = sum(1 for t in query_tokens if t in words)
            if hits > best_hits:
                best_hits, best_i = hits, i
    text = sentences[best_i]
    # Pull in the following sentence when there is room — reads more like a
    # real snippet than a single clipped line.
    if best_i + 1 < len(sentences) and len(text) + len(sentences[best_i + 1]) + 1 <= limit:
        text = f"{text} {sentences[best_i + 1]}"
    if len(text) > limit:
        text = text[:limit].rsplit(" ", 1)[0] + "…"
    prefix = "…" if best_i > 0 else ""
    suffix = "" if text.endswith("…") or best_i >= len(sentences) - 1 else " …"
    return f"{prefix}{expand(text)}{suffix}"


def _matches_datasource(doc: Dict[str, Any], datasource: Optional[str]) -> bool:
    return not datasource or doc["datasource"] == datasource.lower()


# -------------------- result shaping --------------------

def _author(doc: Dict[str, Any]) -> Optional[Dict[str, str]]:
    email = doc.get("author") or ""
    if not email:
        return None
    person = roster().get(email, {})
    return {"name": person.get("name", email), "email": email}


def _metadata(doc: Dict[str, Any]) -> Dict[str, Any]:
    days = int(doc.get("updated_days_ago", 0))
    md = {
        "datasource": doc["datasource"],
        "documentType": doc.get("doc_type", "Document"),
        "container": doc.get("container", ""),
        "updateTime": _epoch_days_ago(days),
        "updatedAgo": ago(days),
    }
    author = _author(doc)
    if author:
        md["author"] = author
    return md


def as_result(doc: Dict[str, Any], query_tokens: Optional[List[str]] = None) -> Dict[str, Any]:
    """Shape a corpus document as a /search result."""
    return {
        "id": doc["id"],
        "title": expand(doc["title"]),
        "url": doc["url"],
        "datasource": doc["datasource"],
        "snippets": [{"text": _snippet(doc, query_tokens or [])}],
        "trackingToken": f"tok_{doc['id']}",
        "metadata": _metadata(doc),
    }


def as_document(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Shape a corpus document as a /getdocuments document."""
    return {
        "id": doc["id"],
        "title": expand(doc["title"]),
        "url": doc["url"],
        "datasource": doc["datasource"],
        "metadata": _metadata(doc),
    }


# -------------------- queries --------------------

def rank(query: str, datasource: Optional[str] = None) -> List[Dict[str, Any]]:
    """Return corpus documents ordered by relevance to query (best first).

    A match-all query ("", "*") returns everything, freshest first.
    """
    pool = [d for d in documents() if _matches_datasource(d, datasource)]
    query = (query or "").strip()
    if not query or query == "*":
        return sorted(pool, key=lambda d: d.get("updated_days_ago", 0))
    tokens = _tokens(query)
    text = query.lower().strip()
    scored = [(_score(d, tokens, text), d) for d in pool]
    matched = [(s, d) for s, d in scored if s > 0]
    rest = [(s, d) for s, d in scored if s <= 0]
    matched.sort(key=lambda sd: (-sd[0], sd[1].get("updated_days_ago", 0), sd[1]["id"]))
    rest.sort(key=lambda sd: (sd[1].get("updated_days_ago", 0), sd[1]["id"]))
    # Genuine matches first, then the freshest remaining documents as filler so
    # a page is never short — an empty screen is a bad demo, and callers of mock
    # mode expect a full page.
    return [d for _, d in matched] + [d for _, d in rest]


def search(query: str, page_size: int = 10,
           datasource: Optional[str] = None) -> List[Dict[str, Any]]:
    ranked = rank(query, datasource)
    n = max(0, min(int(page_size or 10), MAX_RESULTS, len(ranked)))
    tokens = _tokens(query or "")
    return [as_result(d, tokens) for d in ranked[:n]]


def facet_buckets(datasource: Optional[str] = None) -> List[Dict[str, Any]]:
    counts = corpus()["counts"]
    seen = [d["datasource"] for d in documents()]
    buckets = []
    for name in sorted(set(seen), key=lambda n: -counts.get(n, seen.count(n))):
        if datasource and name != datasource.lower():
            continue
        buckets.append({"value": name, "count": counts.get(name, seen.count(name))})
    return buckets


def find(spec: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Look up a document by {'id': ...} or {'url': ...}."""
    if not isinstance(spec, dict):
        return None
    doc_id = spec.get("id") or spec.get("documentId")
    url = spec.get("url")
    for doc in documents():
        if doc_id and doc["id"] == doc_id:
            return doc
        if url and doc["url"] == url:
            return doc
    return None


def summarize(doc: Dict[str, Any]) -> str:
    """A summary that actually reflects the document."""
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", doc["body"]) if s.strip()]
    lead = " ".join(sentences[:2])
    author = _author(doc)
    days = int(doc.get("updated_days_ago", 0))
    owner = f"Owned by {author['name']} in" if author else "Lives in"
    return (f"{expand(doc['title'])} — {expand(lead)} "
            f"{owner} {doc['datasource']}, {ago(days)}.")


def citations(query: str, limit: int = 3) -> List[Dict[str, Any]]:
    return [{"sourceDocument": {"id": d["id"],
                                 "title": expand(d["title"]),
                                 "url": d["url"],
                                 "datasource": d["datasource"]}}
            for d in rank(query)[:limit]]


def people(limit: int = 10) -> List[Dict[str, Any]]:
    out = []
    for email, person in list(roster().items())[:limit]:
        out.append({"name": person.get("name", email),
                    "email": email,
                    "title": person.get("title", ""),
                    "department": person.get("department", "")})
    return out


def person(email: Optional[str]) -> Dict[str, Any]:
    entry = roster().get(email or "")
    if entry:
        return {"name": entry.get("name", email), "email": email,
                "title": entry.get("title", ""), "department": entry.get("department", "")}
    first = people(1)[0] if roster() else {"name": "Unknown", "title": "", "department": ""}
    return {"name": first["name"], "email": email,
            "title": first["title"], "department": first["department"]}


def suggestions(query: str, limit: int = 3) -> List[str]:
    """Autocomplete completions that always contain the typed query."""
    query = (query or "").strip()
    tags: List[str] = []
    for doc in rank(query)[:6]:
        for tag in doc.get("tags", []):
            tag = tag.lower()
            if tag not in tags and tag != query.lower() and query.lower() not in tag:
                tags.append(tag)
    for fallback in ("report", "owner", "policy", "status", "notes", "metrics", "template"):
        if len(tags) >= limit:
            break
        if fallback not in tags:
            tags.append(fallback)
    return [f"{query} {tag}".strip() for tag in tags[:limit]]
