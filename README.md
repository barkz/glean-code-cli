# Glean Code

A local, terminal-first client for the Glean Client REST API. Inspired by Claude Code. Built in Python with zero runtime dependencies.

![Glean Code terminal screenshot](assets/glean_code_cli_example.png)

## Contents

- [What you get](#what-you-get)
- [Coming soon](#coming-soon)
- [Getting Started](#getting-started-with-glean-code) — install, alias, first run
- [Commands at a glance](#commands-at-a-glance)
- [Command Reference](docs/COMMANDS.md) ← full per-command docs
- [Insights](#insights)
- [Indexing API](#indexing-api)
- [Scaffold](#scaffold)
- [Secure tokens](#secure-tokens)
- [Config keys](#config-keys)
- [Project layout](#project-layout)
- [MCP server](#mcp-server)
- [Running tests](#running-tests) · [Test Harness notes](docs/TESTING.md)
- [Notes on the REST paths](#notes-on-the-rest-paths)
- [JSON arguments in /tools.call](#json-arguments-in-toolscall)
- [License](#license)

## What you get

- Slash commands covering every major Glean Client API surface: chat, search, agents, tools, docs, people, shortcuts (Go Links), answers, summarize, verification, messages, activity, announcements, collections, pins, and insights
- **Near-complete Indexing API coverage** — 32 of 37 endpoints exposed as commands across read/debug, single-record write, bulk, and process-all tiers
- Full in-terminal documentation for every command via `/help <command>`
- Tab completion that cycles through matches as you type — press Tab to step forward, Shift+Tab to step back
- Powerline-style status bar showing mode, connected instance, auth state, and active chat thread
- Datasource status enrichment via the Indexing API — uploaded/indexed counts, coverage %, and processing history
- Indexing **debug toolkit** — `/debug.document`, `/debug.documents`, `/debug.user`, and `/documents.access` answer "is this doc uploaded?", "why can't user X see doc Y?", and "what groups did we upload for this user?" without leaving the REPL
- Indexing **observability counters** — `/datasources.config`, `/documents.count`, `/documents.status`, and `/users.count` for quick health checks of any custom datasource
- Indexing **write surface** — single-record `/index.document`, `/index.user`, `/index.group`, `/index.membership` (plus their `/index.delete-*` partners) and `/index.permissions`, all driven by `--from-file <json>` so request bodies stay auditable
- Indexing **bulk + paged uploads** — `/index.bulk-documents|users|groups|memberships`, `/people.bulk-employees|teams`, `/shortcuts.bulk-index`, `/shortcuts.upload`, plus `/index.process-all-*` and `/people.process-all-employees-teams` to kick off long-running rebuilds
- **`--path` mode for indexing** — `/index.document --path file.md` and `/index.bulk-documents --path ./docs/` walk a local file or folder and synthesize the request body for you (`.txt`, `.md`, `.html`, `.json`). Includes `--include`/`--exclude` globs, `--public`/`--acl-from-file` permissions, and `--dry-run` to inspect the assembled payload without calling the API
- `/scaffold` to generate a self-contained Python starter project for chat, search, or agent use cases
- MCP server (`glean_mcp.py`) for Claude Code, Claude Desktop, and Cursor
- Config stored at `~/.gleancode/config.json` — supports both Client and Indexing API tokens
- Mock mode by default so you can try every command offline (now including the 30 new indexing commands); switches to live the moment you add credentials
- `/insights --export <file>` dumps all returned metrics (overview, assistant, agents, datasource clicks) to a flat CSV — pipe it straight into Slack, Sheets, or any BI tool
- Secure-ref token storage — store `token.secure.client` / `token.secure.indexing` in config and have the actual secret resolved from `$GLEAN_CLIENT_TOKEN` / `$GLEAN_INDEXING_TOKEN` at request time, with masking everywhere tokens are displayed
- Test suite in `tests/` covering the client, config, UI, and indexing-walk layers — run with `python3 -m pytest tests/` (604 tests)

## Coming soon

### Visual Studio Code Extension

A native VS Code extension that brings the full Glean Code REPL — slash commands, status bar, mock/live switching, secure-token storage — into the editor sidebar. Run searches, kick off agents, and pin docs without leaving your code window.

![Glean Code VS Code extension preview](assets/vscode_extension_glean-code-cli.png)

<br>

## Getting Started with Glean Code

## Install and run

```bash
cd glean-code-cli
python3 -m glean_code
# or
./glean-code
```

Python 3.9 or newer. No pip install required. Only the standard library is used.

## Create an alias

After opening up a new terminal just run `glean`.

```bash
alias glean="PYTHONPATH=<YOUR_PATH>/glean-code-cli python3 -m glean_code"
```

## First run

```text
/login --instance acme-be.glean.com --token <bearer_token>
/status
/search "quarterly planning"
/chat "summarise the Q2 plan"
```

Without a token the CLI runs in mock mode and returns realistic fake data. Set a token with `/login` and it switches to live calls against `https://<instance>-be.glean.com/rest/api/v1`.

## Commands at a glance

### Shell

- [`/help`](docs/COMMANDS.md#help)
- [`/status`](docs/COMMANDS.md#status)
- [`/doctor`](docs/COMMANDS.md#doctor)
- [`/login`](docs/COMMANDS.md#login)
- [`/logout`](docs/COMMANDS.md#logout)
- [`/config`](docs/COMMANDS.md#config)
- [`/mode`](docs/COMMANDS.md#mode)
- [`/history`](docs/COMMANDS.md#history)
- [`/clear`](docs/COMMANDS.md#clear)
- [`/exit`](docs/COMMANDS.md#exit)

### Chat and Search

- [`/chat`](docs/COMMANDS.md#chat)
- [`/search`](docs/COMMANDS.md#search)
- [`/datasources.list`](docs/COMMANDS.md#datasourceslist)
- [`/datasources.list --with-status`](docs/COMMANDS.md#datasourceslist)
- [`/autocomplete`](docs/COMMANDS.md#autocomplete)
- [`/recommendations`](docs/COMMANDS.md#recommendations)
- [`/feedback`](docs/COMMANDS.md#feedback)

### Indexing — read & debug

- [`/datasources.status <name>`](docs/COMMANDS.md#datasourcesstatus)
- [`/datasources.config <name>`](docs/COMMANDS.md#datasourcesconfig)
- [`/documents.status`](docs/COMMANDS.md#documentsstatus)
- [`/documents.count`](docs/COMMANDS.md#documentscount)
- [`/users.count`](docs/COMMANDS.md#userscount)
- [`/documents.access`](docs/COMMANDS.md#documentsaccess)
- [`/debug.document`](docs/COMMANDS.md#debugdocument)
- [`/debug.documents`](docs/COMMANDS.md#debugdocuments)
- [`/debug.user`](docs/COMMANDS.md#debuguser)
- [`/indexing.rotate-token`](docs/COMMANDS.md#indexingrotate-token)

### Indexing — single-record write

- [`/index.document`](docs/COMMANDS.md#indexdocument)
- [`/index.delete-document`](docs/COMMANDS.md#indexdelete-document)
- [`/index.permissions`](docs/COMMANDS.md#indexpermissions)
- [`/index.user`](docs/COMMANDS.md#indexuser)
- [`/index.delete-user`](docs/COMMANDS.md#indexdelete-user)
- [`/index.group`](docs/COMMANDS.md#indexgroup)
- [`/index.delete-group`](docs/COMMANDS.md#indexdelete-group)
- [`/index.membership`](docs/COMMANDS.md#indexmembership)
- [`/index.delete-membership`](docs/COMMANDS.md#indexdelete-membership)

### Indexing — bulk & process-all

- [`/index.documents`](docs/COMMANDS.md#indexdocuments)
- [`/index.bulk-documents`](docs/COMMANDS.md#indexbulk-documents)
- [`/index.bulk-users`](docs/COMMANDS.md#indexbulk-users)
- [`/index.bulk-groups`](docs/COMMANDS.md#indexbulk-groups)
- [`/index.bulk-memberships`](docs/COMMANDS.md#indexbulk-memberships)
- [`/shortcuts.bulk-index`](docs/COMMANDS.md#shortcutsbulk-index)
- [`/shortcuts.upload`](docs/COMMANDS.md#shortcutsupload)
- [`/index.process-all-documents`](docs/COMMANDS.md#indexprocess-all-documents)
- [`/index.process-all-memberships`](docs/COMMANDS.md#indexprocess-all-memberships)

### Indexing — people (org chart)

- [`/people.bulk-employees`](docs/COMMANDS.md#peoplebulk-employees)
- [`/people.bulk-teams`](docs/COMMANDS.md#peoplebulk-teams)
- [`/people.index-employee-list`](docs/COMMANDS.md#peopleindex-employee-list)
- [`/people.process-all-employees-teams`](docs/COMMANDS.md#peopleprocess-all-employees-teams)

### Insights & Activity

- [`/insights`](#insights)
- [`/insights --all`](#insights)
- [`/insights --assistant`](#insights)
- [`/insights --agents`](#insights)
- [`/insights --all --export <file>`](#insights)

### Agents and Tools

- [`/agents.list`](docs/COMMANDS.md#agentslist)
- [`/agents.run`](docs/COMMANDS.md#agentsrun)
- [`/tools.list`](docs/COMMANDS.md#toolslist)
- [`/tools.call`](docs/COMMANDS.md#toolscall)

### Docs and People

- [`/docs.get`](docs/COMMANDS.md#docsget)
- [`/docs.permissions`](docs/COMMANDS.md#docspermissions)
- [`/entities.list`](docs/COMMANDS.md#entitieslist)
- [`/people.get`](docs/COMMANDS.md#peopleget)

### Announcements, Collections, Pins

- [`/announcements.list`](docs/COMMANDS.md#announcementslist)
- [`/announcements.create`](docs/COMMANDS.md#announcementscreate)
- [`/announcements.delete`](docs/COMMANDS.md#announcementsdelete)
- [`/collections.list`](docs/COMMANDS.md#collectionslist)
- [`/collections.create`](docs/COMMANDS.md#collectionscreate)
- [`/collections.delete`](docs/COMMANDS.md#collectionsdelete)
- [`/pins.list`](docs/COMMANDS.md#pinslist)
- [`/pins.create`](docs/COMMANDS.md#pinscreate)
- [`/pins.delete`](docs/COMMANDS.md#pinsdelete)

### Shortcuts

- [`/shortcuts.list`](docs/COMMANDS.md#shortcutslist)
- [`/shortcuts.get`](docs/COMMANDS.md#shortcutsget)
- [`/shortcuts.create`](docs/COMMANDS.md#shortcutscreate)
- [`/shortcuts.update`](docs/COMMANDS.md#shortcutsupdate)
- [`/shortcuts.delete`](docs/COMMANDS.md#shortcutsdelete)

### Answers

- [`/answers.list`](docs/COMMANDS.md#answerslist)
- [`/answers.get`](docs/COMMANDS.md#answersget)
- [`/answers.create`](docs/COMMANDS.md#answerscreate)
- [`/answers.update`](docs/COMMANDS.md#answersupdate)
- [`/answers.delete`](docs/COMMANDS.md#answersdelete)

### Summarize

- [`/summarize`](#summarize)

### Verification

- [`/verification.list`](docs/COMMANDS.md#verificationlist)
- [`/verification.verify`](docs/COMMANDS.md#verificationverify)
- [`/verification.remind`](docs/COMMANDS.md#verificationremind)

### Messages

- [`/messages.get`](docs/COMMANDS.md#messagesget)

### Activity

- [`/activity.report`](docs/COMMANDS.md#activityreport)

### Scaffold templates

- [`/scaffold chat`](#scaffold)
- [`/scaffold search`](#scaffold)
- [`/scaffold agent`](#scaffold)

Type `/help <command>` for parameters, examples and the underlying REST endpoint. Bare text with no leading slash is a shortcut for `/chat`.

---

## Command Reference

The full per-command reference (every slash command, with usage, parameters, examples, and the underlying REST endpoint) lives in [docs/COMMANDS.md](docs/COMMANDS.md). It is generated to match what `/help <command>` shows in the REPL.

For a quick scan, see [Commands at a glance](#commands-at-a-glance) above.

---

## Insights

`/insights` retrieves aggregate usage data from the Glean Insights Dashboard — the same data visible in the admin UI. It covers search adoption, active user counts, search session satisfaction, datasource click distribution, and AI assistant activity.

Uses the same Client API token as search and chat — no extra credentials required.

### Flags

| Flag | Description |
| --- | --- |
| _(none)_ | Overview only: MAU, WAU, employee count, sign-ups, search satisfaction, clicks by datasource |
| `--assistant` | Adds Assistant metrics: MAU, WAU, chat messages, AI answers, summarizations |
| `--agents` | Adds Agents metrics: MAU, WAU |
| `--all` | All three surfaces in one call |
| `--no-per-user` | Suppresses the per-user breakdown in the response |
| `--export <file>` | Write all returned metrics to a CSV file (columns: `section`, `metric`, `value`) |

### Examples

```text
/insights
/insights --all
/insights --assistant
/insights --agents --no-per-user
/insights --all --export insights.csv
```

### What the output shows

#### Overview

- Monthly and weekly active users
- Employee count and total sign-ups (from org chart)
- Search session satisfaction rate (%)
- Last updated timestamp
- Search clicks broken down by datasource (gdrive, confluence, slack, jira, etc.)

#### Assistant (with `--assistant` or `--all`)

- Monthly and weekly active users of the Glean Assistant
- Chat message, AI answer, and summarization activity

#### Agents (with `--agents` or `--all`)

- Monthly and weekly active users across agent runs

### Endpoint

```text
POST /rest/api/v1/insights
```

---

## Indexing API

Glean Code exposes 32 of the 37 documented Indexing API endpoints — read/debug, single-record writes, bulk uploads, and long-running process-all triggers. All Indexing-API commands require a separate indexing token (Client API tokens cannot reach `/api/index/v1`):

```text
/config set indexing_token <token-or-secure-ref>
```

The token can be a literal value or the secure reference `token.secure.indexing` (resolved from `$GLEAN_INDEXING_TOKEN` at request time — see [Secure tokens](#secure-tokens)). Get a real token from your Glean admin UI (workspace settings → API tokens → Indexing).

### Read & debug

These are non-destructive lookups — start here when answering questions like "is this doc indexed?", "why can't user X see doc Y?", or "what's the upload count for datasource Z?"

| Command | Purpose |
| --- | --- |
| [`/datasources.status <name>`](docs/COMMANDS.md#datasourcesstatus) | Full status for one datasource: visibility, counts, last 5 processing events |
| [`/datasources.config <name>`](docs/COMMANDS.md#datasourcesconfig) | Live config: object types, ACL settings, trusted domains, icon URL |
| [`/datasources.list --with-status`](docs/COMMANDS.md#datasourceslist) | All datasources with uploaded/indexed counts and coverage |
| [`/documents.status`](docs/COMMANDS.md#documentsstatus) | Upload + indexing status for one document |
| [`/documents.count`](docs/COMMANDS.md#documentscount) | Document count for a custom datasource |
| [`/users.count`](docs/COMMANDS.md#userscount) | User count for a custom datasource |
| [`/documents.access`](docs/COMMANDS.md#documentsaccess) | Whether a specific user has access to a specific document |
| [`/debug.document`](docs/COMMANDS.md#debugdocument) | Per-doc debug payload (status + uploaded permissions) |
| [`/debug.documents`](docs/COMMANDS.md#debugdocuments) | Bulk debug for many documents (`--from-file`) |
| [`/debug.user`](docs/COMMANDS.md#debuguser) | Per-user debug payload (status + uploaded groups) |

```text
/datasources.config gdrive
/documents.access --datasource gdrive --object-type Article --id doc-1 --user alice@example.com
/debug.user gdrive alice@example.com
```

### Single-record write

Each write command takes a JSON request body via `--from-file`. Deletes use convenience flags. All accept `--version <n>` for optimistic concurrency.

| Command | Purpose |
| --- | --- |
| [`/index.document`](docs/COMMANDS.md#indexdocument) | Index one document — supports `--path <file>` mode, see below |
| [`/index.delete-document`](docs/COMMANDS.md#indexdelete-document) | Delete one document by id |
| [`/index.permissions`](docs/COMMANDS.md#indexpermissions) | Update document ACL |
| [`/index.user`](docs/COMMANDS.md#indexuser) | Index one user |
| [`/index.delete-user`](docs/COMMANDS.md#indexdelete-user) | Delete one user |
| [`/index.group`](docs/COMMANDS.md#indexgroup) | Index one group |
| [`/index.delete-group`](docs/COMMANDS.md#indexdelete-group) | Delete one group |
| [`/index.membership`](docs/COMMANDS.md#indexmembership) | Index one group membership |
| [`/index.delete-membership`](docs/COMMANDS.md#indexdelete-membership) | Delete one group membership |

```text
/index.document --from-file ./doc.json
/index.document --path ./README.md --datasource custom1 --object-type Article --public
/index.delete-document --datasource gdrive --object-type Article --id doc-1
/index.permissions --from-file ./perms.json
```

### Indexing from local files (`--path`)

`/index.document` and `/index.bulk-documents` both accept `--path <file-or-dir>` as an alternative to `--from-file`. The CLI walks the path, builds DocumentDefinitions for you, and POSTs them. Pair with `--dry-run` to see exactly what would be sent.

| Flag | Purpose |
| --- | --- |
| `--path` | A file (single mode) or directory (bulk mode) |
| `--datasource` | Required. Datasource name applied to every walked file |
| `--object-type` | Required. e.g. `Article`, `Wiki` |
| `--public` | Make all docs world-readable. Mutually exclusive with `--acl-from-file` |
| `--acl-from-file` | JSON file with a `DocumentPermissionsDefinition` applied to every doc |
| `--include` | Comma-separated globs. Default: `*.txt,*.md,*.markdown,*.html,*.htm,*.json` |
| `--exclude` | Comma-separated globs. Default skips `.git`, `node_modules`, `__pycache__`, `.DS_Store` |
| `--max-bytes` | Skip files larger than this. Default 5 MB |
| `--id-prefix` | Prepended to the path-derived id slug (e.g. `--id-prefix proj` → `proj-team-onboarding`) |
| `--view-url-prefix` | Base URL prepended to relative paths. Defaults to `file://` per file |
| `--dry-run` | Print the assembled request body and exit without calling the API |

**Supported file types:** `.txt`, `.md`, `.markdown`, `.html`, `.htm`, `.json`. Binary formats (PDF, `.docx`, etc.) are out of scope for v1.

**Behaviour:**

- Path-derived ids: `team/onboarding.md` → `team-onboarding`. Stable across re-runs, debuggable, datasource-safe
- HTML files are sent as `htmlContent`; everything else as `textContent`
- Mock mode works for `--path` exactly like every other indexing command (token still required)
- `/index.document --path <dir>` errors and points you at `/index.bulk-documents` — single mode is single-file only
- The bulk command warns when more than 500 files are matched. v1 sends them in one POST; auto-paging across `isFirstPage`/`isLastPage` is planned for v2

```text
# Single Markdown file, public ACL, dry-run first
/index.document --path ./README.md \
                --datasource custom1 --object-type Article \
                --public --dry-run

# Walk a folder, only .md and .txt, with a fixed ACL from disk
/index.bulk-documents --path ./content/ \
                      --datasource custom1 --object-type Article \
                      --acl-from-file ./perms.json \
                      --include "*.md,*.txt" --exclude "**/draft/**"
```

### Bulk + paged uploads

Bulk endpoints use the standard upload-paging contract (`uploadId`, `isFirstPage`, `isLastPage`, optional `forceRestartUpload`). Wrap your full request body in a JSON file and pass it via `--from-file`. The documents-side commands also accept `--path` (see above).

| Command | Endpoint family |
| --- | --- |
| [`/index.documents`](docs/COMMANDS.md#indexdocuments) | Paged document index |
| [`/index.bulk-documents`](docs/COMMANDS.md#indexbulk-documents) | Bulk document index |
| [`/index.bulk-users`](docs/COMMANDS.md#indexbulk-users) | Bulk user index |
| [`/index.bulk-groups`](docs/COMMANDS.md#indexbulk-groups) | Bulk group index |
| [`/index.bulk-memberships`](docs/COMMANDS.md#indexbulk-memberships) | Bulk group memberships |
| [`/people.bulk-employees`](docs/COMMANDS.md#peoplebulk-employees) | Bulk employee records (org chart) |
| [`/people.bulk-teams`](docs/COMMANDS.md#peoplebulk-teams) | Bulk team records (org chart) |
| [`/people.index-employee-list`](docs/COMMANDS.md#peopleindex-employee-list) | Versioned employee list |
| [`/shortcuts.bulk-index`](docs/COMMANDS.md#shortcutsbulk-index) | Bulk shortcuts via Indexing API ⚠ distinct from Client API `/shortcuts.*` |
| [`/shortcuts.upload`](docs/COMMANDS.md#shortcutsupload) | Upload shortcuts via Indexing API |

### Process-all (long-running)

Trigger a tenant-wide reprocess after a bulk upload completes. These commands accept an optional `--datasource` filter where applicable.

| Command | Purpose |
| --- | --- |
| [`/index.process-all-documents`](docs/COMMANDS.md#indexprocess-all-documents) | Reprocess all uploaded documents |
| [`/index.process-all-memberships`](docs/COMMANDS.md#indexprocess-all-memberships) | Reprocess all uploaded memberships |
| [`/people.process-all-employees-teams`](docs/COMMANDS.md#peopleprocess-all-employees-teams) | Reprocess all uploaded employees + teams |

### Token rotation

```text
/indexing.rotate-token
/config set indexing_token <new-raw-secret>
```

`/indexing.rotate-token` prints the new raw secret — store it immediately, the old one is invalidated.

### Mock mode for indexing

All 32 indexing commands work in mock mode as long as an indexing token is set in config — it can be any non-empty string (e.g. `mock_idx_token`). The CLI returns realistic shapes (datasource configs, doc/user counts, debug payloads, accept-style write responses) so you can rehearse a workflow before pointing at a live tenant.

---

## Scaffold

`/scaffold` generates a self-contained Python starter file for a Glean API surface. It reads credentials from your existing `~/.gleancode/config.json` (written by `/login`) so the generated script works immediately.

```text
/scaffold chat              # interactive chat loop + single-turn CLI
/scaffold search            # search with --datasource and --page-size flags
/scaffold agent             # list agents and run them by id
```

Each template accepts an output directory. If omitted you are prompted, and if the directory does not exist you are asked before it is created.

```text
/scaffold chat --output ~/projects/my-chat-app
```

The generated files are stdlib-only — no `pip install` required. They also support `GLEAN_INSTANCE`, `GLEAN_TOKEN`, and `GLEAN_ACT_AS` environment variables as an alternative to the config file.

## Secure tokens

Glean Code never has to store a literal API token on disk. Instead of pasting the real token into config, you can store a **secure reference** — a fixed name like `token.secure.client` — and Glean Code resolves it from an environment variable at the moment a request is made.

### Reference table

| Reference | Resolves from | Used for |
| --- | --- | --- |
| `token.secure.client` | `$GLEAN_CLIENT_TOKEN` | All Client API calls (chat, search, agents, insights, etc.) |
| `token.secure.indexing` | `$GLEAN_INDEXING_TOKEN` | Indexing API calls (`/datasources.status`, `/indexing.rotate-token`) |

### Example — full setup

```bash
# 1. Put the real secrets in your shell environment.
#    Use whatever secret manager you already trust:
#    direnv, 1Password CLI, Doppler, AWS Secrets Manager, plain rc file, etc.
export GLEAN_CLIENT_TOKEN="glean_xxx_real_client_token"
export GLEAN_INDEXING_TOKEN="glean_idx_real_indexing_token"
```

```text
# 2. Tell Glean Code to look the values up by reference.
/login --instance acme-be.glean.com --token token.secure.client
/config set indexing_token token.secure.indexing
```

```text
# 3. Verify
/status
/doctor
```

After this, `~/.gleancode/config.json` contains the harmless string `token.secure.client`, not the real secret:

```json
{
  "instance": "acme-be.glean.com",
  "api_token": "token.secure.client",
  "indexing_token": "token.secure.indexing"
}
```

### What gets masked, where

| Surface | Behaviour |
| --- | --- |
| `/status` | Shows `token.secure.client ($GLEAN_CLIENT_TOKEN set)` for refs, `***1234` for literal tokens, `(unset)` if neither |
| `/config list` | Same — refs verbatim, literal tokens masked to last 4 chars |
| `/doctor` | Verifies the env var actually resolves; reports `FAIL` if a ref is configured but the env var is empty |
| `/history` | Strips secret values from `--token` / `--indexing-token` flags and from `/config set <token-key> <value>` so secrets never enter the in-memory history buffer |
| `config.json` on disk | Contains only the reference name when refs are used; literal tokens are written as-is and protected with `0o600` perms |

### Mixing refs and literals

You can use either form for either token. A literal is fine if you're testing locally and don't want the env-var indirection — Glean Code masks literal tokens on display so they never echo to the screen in full. Switch back and forth at any time with `/config set api_token <new-value-or-ref>`.

### Falling back to mock mode

If a secure ref is configured but the env var is unset, Glean Code's `is_live_ready` check returns false and `/mode auto` resolves to `mock`. You'll see realistic fake data instead of an unauthenticated 401 — handy for demos.

## Config keys

| Key | Description | Values |
| --- | --- | --- |
| `instance` | Glean backend host | e.g. `acme-be.glean.com` |
| `api_token` | Client API bearer token | Glean-issued token, or a secure ref like `token.secure.client` (see [Secure tokens](#secure-tokens)) |
| `indexing_token` | Indexing API token (for datasource status) | Glean-issued token, or `token.secure.indexing` (see [Secure tokens](#secure-tokens)) |
| `act_as` | Impersonate a user via `X-Glean-ActAs` | Email address |
| `base_url` | Override the computed base URL | Full URL |
| `mode` | API mode | `auto` (default), `live`, `mock` |
| `theme` | Terminal colour theme | `glean` (default), `mono`, `neon` |
| `default_page_size` | Default result count for search and entities | Integer, default `10` |

Change any key with `/config set <key> <value>`. Use `/mode live|mock|auto` to force a mode without editing config.

## Project layout

```text
glean-code/
  glean-code              launcher script
  glean_mcp.py            MCP server entry point
  glean_code/
    __init__.py
    __main__.py           python -m glean_code
    cli.py                REPL loop and banner
    ui.py                 ASCII art, colours, boxes
    config.py             config file load and save
    client.py             Glean REST wrapper + mock responses
    commands.py           slash command parser and handlers
    help_docs.py          per-command documentation
    completion.py         readline tab completion
    scaffold.py           project scaffold templates
  tests/
    __init__.py
    test_client.py        GleanClient and mock response tests
    test_config.py        Config load, save and URL property tests
    test_ui.py            ANSI helpers, box renderer and status bar tests
```

## MCP server

`glean_mcp.py` exposes Glean as an MCP server so Claude Code, Claude Desktop,
and Cursor can call Glean search, chat, and agents as native tools.

**Install the MCP package (one-time):**

`pip`

```bash
pip install "mcp[cli]"
```

`brew`

```bash
brew install pipx
pipx install "mcp[cli]"
```

**Claude Code** — add to `.claude/settings.json` in your project, or to
`~/.claude/settings.json` globally:

```json
{
  "mcpServers": {
    "glean": {
      "command": "python3",
      "args": ["/absolute/path/to/glean-code-cli/glean_mcp.py"]
    }
  }
}
```

**Claude Desktop** — add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "glean": {
      "command": "python3",
      "args": ["/absolute/path/to/glean-code-cli/glean_mcp.py"]
    }
  }
}
```

**Cursor** — add to `.cursor/mcp.json` in your project:

```json
{
  "mcpServers": {
    "glean": {
      "command": "python3",
      "args": ["/absolute/path/to/glean-code-cli/glean_mcp.py"]
    }
  }
}
```

Credentials are loaded automatically from `~/.gleancode/config.json` (written
by `/login` in the REPL). You can also pass them as environment variables:

```json
{
  "mcpServers": {
    "glean": {
      "command": "python3",
      "args": ["/absolute/path/to/glean-code-cli/glean_mcp.py"],
      "env": {
        "GLEAN_INSTANCE": "your-instance-be.glean.com",
        "GLEAN_TOKEN": "your-token"
      }
    }
  }
}
```

**Tools exposed:**

| Tool | Description |
| --- | --- |
| `search` | Search the Glean index; optional `datasource` and `page_size` |
| `chat` | Chat with the Glean Assistant; pass `chat_id` to continue a thread |
| `list_agents` | List available agents; optional `query` filter |
| `run_agent` | Run an agent by id and return its output |

Requires Python 3.10+. The REPL itself remains Python 3.9+ and stdlib-only.

## Running tests

The test suite uses only the standard library (no mocking frameworks, no network calls).

```bash
python3 -m pytest tests/
```

Or without pytest:

```bash
python3 -m unittest discover tests/
```

| File | What it covers |
| --- | --- |
| `tests/test_client.py` | All mock responses, GleanClient methods, error handling |
| `tests/test_config.py` | Config load/save, URL property computation, mode resolution |
| `tests/test_ui.py` | ANSI width helpers, box renderer, status bar, hyperlink |

## Notes on the REST paths

The client targets the documented Glean Client REST API at `https://<instance>-be.glean.com/rest/api/v1`. Paths used:

```text
POST /chat
POST /search
POST /autocomplete
POST /recommendations
POST /feedback
POST /agents/search
POST /agents/runs/wait
POST /agents/runs/stream
POST /tools/list
POST /tools/call
POST /getdocuments
POST /getdocumentpermissions
POST /listentities
POST /people
POST /announcements/list
POST /announcements/create
POST /announcements/delete
POST /listcollections
POST /createcollection
POST /listpins
POST /createpin
POST /unpin
POST /deletecollection
POST /listshortcuts
POST /getshortcut
POST /createshortcut
POST /updateshortcut
POST /deleteshortcut
POST /listanswers
POST /getanswer
POST /createanswer
POST /editanswer
POST /deleteanswer
POST /summarize
POST /listverifications
POST /verify
POST /addverificationreminder
POST /messages
POST /activity
POST /insights
```

Indexing API paths (require a separate indexing token, base `https://<instance>-be.glean.com/api/index/v1`):

```text
POST /api/index/v1/rotatetoken

# Read & debug
POST /api/index/v1/getdatasourceconfig
POST /api/index/v1/getdocumentstatus
POST /api/index/v1/getdocumentcount
POST /api/index/v1/getusercount
POST /api/index/v1/checkdocumentaccess
POST /api/index/v1/debug/{datasource}/status
POST /api/index/v1/debug/{datasource}/document
POST /api/index/v1/debug/{datasource}/documents
POST /api/index/v1/debug/{datasource}/user

# Single-record write
POST /api/index/v1/indexdocument
POST /api/index/v1/deletedocument
POST /api/index/v1/updatepermissions
POST /api/index/v1/indexuser
POST /api/index/v1/deleteuser
POST /api/index/v1/indexgroup
POST /api/index/v1/deletegroup
POST /api/index/v1/indexmembership
POST /api/index/v1/deletemembership

# Bulk / paged
POST /api/index/v1/indexdocuments
POST /api/index/v1/bulkindexdocuments
POST /api/index/v1/bulkindexusers
POST /api/index/v1/bulkindexgroups
POST /api/index/v1/bulkindexmemberships
POST /api/index/v1/bulkindexshortcuts
POST /api/index/v1/uploadshortcuts
POST /api/index/v1/bulkindexemployees
POST /api/index/v1/bulkindexteams
POST /api/index/v1/indexemployeelist

# Process-all (long running)
POST /api/index/v1/processalldocuments
POST /api/index/v1/processallmemberships
POST /api/index/v1/processallemployeesandteams
```

If your tenant uses a slightly different path for a given surface, change it in `glean_code/client.py`. Every method is a small wrapper around `self._post(path, body)` so the swap is a one-liner.

## JSON arguments in /tools.call

Wrap the JSON in single quotes so the shell parser leaves the double quotes intact:

```text
/tools.call search '{"query":"pto policy"}'
```

## Test Harness

Development notes on the test suite live in [docs/TESTING.md](docs/TESTING.md). See [Running tests](#running-tests) for how to run them.

---

## License

[MIT](LICENSE) © 2026 barkz
