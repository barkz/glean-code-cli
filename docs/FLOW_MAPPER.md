# Flow mapper

`/flow` records the investigations you run through Glean Code, enriches the documents they
cite with real text, and finds the connections between them — including between conversations
that never shared any context.

Everything is local: one SQLite file at `~/.gleancode/flow.db`, no dependencies beyond the
standard library, no network beyond the calls you were making anyway.

## Contents

- [The five-minute tour](#the-five-minute-tour)
- [What gets captured, and when](#what-gets-captured-and-when)
- [The commands](#the-commands)
- [How linking works](#how-linking-works)
- [The timeline](#the-timeline)
- [MCP tools](#mcp-tools)
- [Mock mode and live mode](#mock-mode-and-live-mode)
- [Privacy, retention, and the parts to think about](#privacy-retention-and-the-parts-to-think-about)
- [Troubleshooting](#troubleshooting)

## The five-minute tour

Run this in mock mode and you'll see the whole feature work against the built-in corpus, with
no credentials and no network.

```text
/mode mock
/config set instance acme-be.glean.com
/config set flow_capture on

/chat "what happened in the checkout incident?"
/chat "who owned the fix?"
/chat "what are the risks going into the Northwind renewal?" --new

/flow enrich
/flow link
/flow show
```

The last command draws the two investigations and the connection between them:

```text
── flow: acme-be.glean.com · mock ────────────────────────────────────────────

  ●─ 1  what happened in the checkout incident?
  │     Tue 18 Aug 2026, 22:05  ·  4 turns  ·  6 sources
  │     ↳ who owned the fix?
  │
  │     ▪ confluence Postmortem: Checkout Latency Incident (INC-1183)
  │     ▪ slack      War room thread: checkout 5xx spike
  │     ▪ jira       INC-1183 — Elevated 5xx on checkout API
  │     … 3 more documents
  │
  ├──◆ linked-document  0.60  →  2 ───────────────────────────────────────────
  │    Postmortem: Checkout Latency Incident (INC-1183)
  │      ↓  shares: incident, checkout
  │    Customer QBR — Northwind Retail
  │
  ●─ 2  what are the risks going into the Northwind renewal?
  │     Tue 18 Aug 2026, 22:05  ·  2 turns  ·  3 sources
  │
  │     ▪ gdrive     Customer QBR — Northwind Retail
  │     ▪ jira       SUP-882 — Northwind: search results missing Confluence…
  │     ▪ slack      Northwind attachment issue — need connector eyes
  │
──────────────────────────────────────────────────────────────────────────────
```

Nothing in those two conversations shares a word. They connect because the Northwind QBR
mentions *"the checkout incident in June"* in passing — no ticket number, no shared vocabulary,
just a document referring to the other investigation's subject.

> **`--new` goes after the message.** `/chat --new "…"` makes the parser read your message as
> the flag's value. Write `/chat "…" --new`. Without it, `/chat` continues the current thread —
> which is usually what you want, and is exactly why the two questions above stay in one session
> while the third starts its own.

Then look at it:

```text
/flow timeline
```

## What gets captured, and when

Capture is governed by one config key:

| `flow_capture` | Behaviour |
| --- | --- |
| `mock` | **Default.** Records only mock-mode traffic. Real tenant content never touches the database. |
| `on` | Records both modes. |
| `off` | Records nothing. |

```text
/config set flow_capture on
```

Two endpoints are recorded:

- **`/chat`** — your question, the answer, and every cited document. Turns are grouped by the
  `chatId` the API returns, so a conversation is one session with no guessing involved.
- **`/search`** — the query and its results. A search runs within the proximity window (10
  minutes) of a session's last activity attaches to that session, because a search you run
  mid-investigation is part of it.

Capture happens inside `GleanClient._post`, the single funnel every Client API call passes
through, so it covers the REPL and the MCP server alike. **A capture failure can never break a
command** — errors there are swallowed by design.

Every row is tagged with the instance, the mode, and the `act_as` value in force. Nothing is
ever queried or linked across those boundaries.

## The commands

```text
/flow <status|enrich|link|show|timeline|purge>
```

### `/flow status`

Capture setting, database path and size, and what's been recorded.

```text
  capture         on  →  recording in mock mode
  database        ~/.gleancode/flow.db  (64 KB)
  scope           acme-be.glean.com · mock
  sessions        2
  turns           6
  documents       9  (9 enriched)
  document links  14
  session links   1
```

### `/flow enrich`

Citations arrive as metadata — title, URL, datasource — with no text. Enrichment fetches the
content, trying `/getdocuments` first and falling back to `/summarize`. **Linking needs this;
run it before `/flow link`.**

`--limit <n>` caps how many documents are fetched in one go (default 50). Documents that return
nothing stay in the graph as metadata rather than disappearing.

### `/flow link`

Finds document-to-document and session-to-session links. Re-runs cleanly — links are rebuilt,
not appended.

`--min-score <0-1>` sets the phrase-link threshold (default `0.45`). Raise it if you see links
you disagree with; identifier links are unaffected because they're exact.

### `/flow show`

The terminal view. Sessions run down a vertical rail in the order they happened; connections
branch off it.

`--docs <n>` sets how many documents are listed per session before the rest are counted
(default `6`). `--links <n>` does the same for connections (default `3`).

**What leads the list**

Documents a thread kept returning to come first; everything else holds the order it was cited
in. Sorting by the citation rank instead would interleave the turns, because every turn's
citations restart at rank 0 — a tangential follow-up's top hit would land level with the
document the thread is actually about.

Connections are ordered by how much they tell you, not by score. A `shared-citation` link is
trivially certain — two sessions cited the same document — and scores `1.00`; a
`linked-document` link is the one that found something and typically scores lower. Ordering by
score would bury the discovery, which matters as soon as you run the same investigation twice:
each re-run adds a `1.00` link to every earlier identical session.

**Reading the rail**

| | |
| --- | --- |
| `●─ 1` | A session. The number is its position on the rail, and it's what a connection points at. |
| `│` | The rail itself — everything indented off it belongs to the session above. |
| `↳` | A follow-up question in the same thread. Four are shown, then a count. |
| `▪ jira` | A cited document, tagged with its datasource. Each source keeps the same colour everywhere. |
| `├──◆` | A connection leaving this session, drawn in yellow so it reads as a departure from the rail. |
| `→ 2` | Which session the connection reaches. It is not always the next one down. |
| `↓` | The direction of the link, with the shared evidence beside it. |

The bridge is the part worth reading closely. It names the document in *this* session, the
document in the *other* one, and what they share:

```text
  ├──◆ linked-document  0.60  →  2 ───────────────────────────────────────────
  │    Postmortem: Checkout Latency Incident (INC-1183)
  │      ↓  shares: incident, checkout
  │    Customer QBR — Northwind Retail
```

A `shared-citation` link collapses to one line, because both ends are the same document:

```text
  ├──◆ shared-citation  1.00  →  3 ────────────────────────────────────────────
  │    both cited: Postmortem: Checkout Latency Incident (INC-1183)
```

**Colour is decoration, never the message.** Piped, redirected, or with `NO_COLOR` set, every
line still carries its glyph, so the rail and the branch survive `\| less` and `> flow.txt`.
The block also fits whatever width it's given, capped at 100 columns so long lines stay
readable on a wide screen, and truncates titles with `…` rather than wrapping them.

### `/flow timeline`

Writes a self-contained HTML file and opens it. `--output <file>` chooses where; `--print`
writes without opening, which is what you want over SSH.

### `/flow purge`

Deletes captured data, after confirming. Scoped to the current instance and mode by default.

```text
/flow purge                      # this instance and mode
/flow purge --older-than 30      # …and only sessions older than 30 days
/flow purge --all                # everything in the database
```

## How linking works

Three tiers. Each stores its evidence, so every link can be explained rather than asserted — a
graph you can't interrogate is worse than no graph.

**1. Identifier — exact, score 1.0.** A shared ticket key or repo reference: `INC-1183`,
`SUP-882`, `acme/payments#1841`. No false positives; a shared identifier is a real relationship.

**2. Phrase — scored, this is the one that finds the interesting links.** Two signals combine:

- a **shared bigram** — the same two-word phrase in both documents
- a **title anchor** — a word from one document's *title* appearing in the other's text

The title anchor is what makes this precise, and it's worth understanding why. Rarity alone
doesn't work: in a small set, a word used once anywhere scores higher than a meaningful word
used four times, so ranking by rarity surfaces accidents like "across" and "percent". A title is
a curated human label, so prose echoing one is a genuine reference. That's what connects a QBR
saying *"the checkout incident in June"* to a postmortem titled *"Checkout Latency Incident"* —
the two share no bigram at all, but `checkout` and `incident` both sit in the postmortem's title.

**3. Session links.** Two sessions connect when they cite the same document
(`shared-citation`), or when a document cited by one links to a document cited by the other
(`linked-document`). The second is the indirect case — the one where neither conversation knew
about the other.

## The timeline

`/flow timeline` writes a single HTML file with no external references: no CDN, no framework,
no fonts, nothing that phones home. It follows your system light/dark preference.

- Sessions run down a timeline with real dates.
- Multi-turn threads collapse into one box with a turn count; click to expand.
- Repeated questions fold into a single row with a `×n` badge.
- Questions appear in the session header rather than inside the document graph, so the graph
  stays about content.
- Connections render between sessions with their evidence line visible.
- Mock-captured data carries a banner saying so.

## MCP tools

Three tools expose the graph to an agent, alongside the existing four:

| Tool | Returns |
| --- | --- |
| `get_flow` | The full graph as JSON — sessions, turns, citations, and every link. Optional `session_id` narrows it. |
| `get_flow_summary` | The narrative: what was investigated, what connected, and why, in prose |
| `get_flow_collapsed` | The compact view — threads folded into counted nodes |

They read the same partition rules as the REPL, so an agent sees one instance and one mode. When
the server runs with `GLEAN_MOCK=1`, every response carries the `[MOCK MODE]` banner.

Setup is unchanged — see [docs/MCP.md](MCP.md).

## Mock mode and live mode

**Mock mode is where this feature is at its best**, and not as a consolation. The corpus is
seventy interlinked documents with known relationships: seven identifier clusters, and the
QBR-to-postmortem reference that has no identifier at all. That makes link quality *testable* —
the test suite asserts the checkout connection is found and that its evidence is specific rather
than generic — which is otherwise very hard to pin down.

**Live mode works, and is off by default.** `flow_capture` must be set to `on` explicitly. The
mechanics are identical; what changes is what's in the file.

## Privacy, retention, and the parts to think about

Read this before turning capture on against a real tenant.

**A local cache has no permission model.** Glean filters what you can see at query time. Once a
document's text is in `flow.db`, that filtering is gone. The copy survives you losing access to
the document, the token being revoked, and the document being deleted or restricted at source.

What the implementation does about it:

- The database is created `0600`, matching `config.json` and `auth.json`.
- Capture defaults to mock, so real content is never recorded by accident.
- Rows are partitioned by instance, mode, and `act_as`. An impersonated view is someone else's
  view of the tenant; linking across those would build connections no single person is entitled
  to see, so it can't happen.
- `/flow purge --older-than <days>` exists for retention.

What it does **not** do, and you should decide about:

- There is no automatic expiry. Retention is a command you run, not a policy that enforces itself.
- The file is not encrypted. It's as exposed as anything else in your home directory — which is
  fine until it's copied, backed up, or synced to a cloud drive.
- Nothing re-checks permissions. There is no mechanism to notice that a captured document is no
  longer one you can see.

If that's more than you want, `flow_capture` stays on `mock` and the feature remains a genuinely
useful offline tool.

## Troubleshooting

**`/flow link` finds nothing.** Run `/flow enrich` first — linking needs document text, and
citations arrive without it. `/flow status` shows how many documents are still unenriched.

**Links look wrong.** Raise the threshold: `/flow link --min-score 0.65`. Identifier links are
exact and unaffected. Every link carries its evidence in `/flow show`, so you can see what
triggered it.

**Two conversations that should be separate are one session.** `/chat` continues the current
thread by default. Use `/chat "…" --new`, with the flag *after* the message.

**Nothing is being captured.** Check `/flow status`: capture defaults to `mock`, so live traffic
is ignored until you set `/config set flow_capture on`.

**The timeline won't open.** Use `--print` and open the file yourself; a headless or remote shell
has no browser to hand off to.
