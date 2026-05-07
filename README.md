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
- `/scaffold` to generate a self-contained Python starter project for chat, search, or agent use cases
- MCP server (`glean_mcp.py`) for Claude Code, Claude Desktop, and Cursor
- Config stored at `~/.gleancode/config.json` — supports both Client and Indexing API tokens
- Mock mode by default so you can try every command offline (now including the 30 new indexing commands); switches to live the moment you add credentials
- `/insights --export <file>` dumps all returned metrics (overview, assistant, agents, datasource clicks) to a flat CSV — pipe it straight into Slack, Sheets, or any BI tool
- Secure-ref token storage — store `token.secure.client` / `token.secure.indexing` in config and have the actual secret resolved from `$GLEAN_CLIENT_TOKEN` / `$GLEAN_INDEXING_TOKEN` at request time, with masking everywhere tokens are displayed
- Test suite in `tests/` covering the client, config, and UI layers — run with `python3 -m pytest tests/` (579 tests)

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

- [`/help`](#help)
- [`/status`](#status)
- [`/doctor`](#doctor)
- [`/login`](#login)
- [`/logout`](#logout)
- [`/config`](#config)
- [`/mode`](#mode)
- [`/history`](#history)
- [`/clear`](#clear)
- [`/exit`](#exit)

### Chat and Search

- [`/chat`](#chat)
- [`/search`](#search)
- [`/datasources.list`](#datasourceslist)
- [`/datasources.list --with-status`](#datasourceslist)
- [`/autocomplete`](#autocomplete)
- [`/recommendations`](#recommendations)
- [`/feedback`](#feedback)

### Indexing — read & debug

- [`/datasources.status <name>`](#datasourcesstatus)
- [`/datasources.config <name>`](#datasourcesconfig)
- [`/documents.status`](#documentsstatus)
- [`/documents.count`](#documentscount)
- [`/users.count`](#userscount)
- [`/documents.access`](#documentsaccess)
- [`/debug.document`](#debugdocument)
- [`/debug.documents`](#debugdocuments)
- [`/debug.user`](#debuguser)
- [`/indexing.rotate-token`](#indexingrotate-token)

### Indexing — single-record write

- [`/index.document`](#indexdocument)
- [`/index.delete-document`](#indexdelete-document)
- [`/index.permissions`](#indexpermissions)
- [`/index.user`](#indexuser)
- [`/index.delete-user`](#indexdelete-user)
- [`/index.group`](#indexgroup)
- [`/index.delete-group`](#indexdelete-group)
- [`/index.membership`](#indexmembership)
- [`/index.delete-membership`](#indexdelete-membership)

### Indexing — bulk & process-all

- [`/index.documents`](#indexdocuments)
- [`/index.bulk-documents`](#indexbulk-documents)
- [`/index.bulk-users`](#indexbulk-users)
- [`/index.bulk-groups`](#indexbulk-groups)
- [`/index.bulk-memberships`](#indexbulk-memberships)
- [`/shortcuts.bulk-index`](#shortcutsbulk-index)
- [`/shortcuts.upload`](#shortcutsupload)
- [`/index.process-all-documents`](#indexprocess-all-documents)
- [`/index.process-all-memberships`](#indexprocess-all-memberships)

### Indexing — people (org chart)

- [`/people.bulk-employees`](#peoplebulk-employees)
- [`/people.bulk-teams`](#peoplebulk-teams)
- [`/people.index-employee-list`](#peopleindex-employee-list)
- [`/people.process-all-employees-teams`](#peopleprocess-all-employees-teams)

### Insights & Activity

- [`/insights`](#insights)
- [`/insights --all`](#insights)
- [`/insights --assistant`](#insights)
- [`/insights --agents`](#insights)
- [`/insights --all --export <file>`](#insights)

### Agents and Tools

- [`/agents.list`](#agentslist)
- [`/agents.run`](#agentsrun)
- [`/tools.list`](#toolslist)
- [`/tools.call`](#toolscall)

### Docs and People

- [`/docs.get`](#docsget)
- [`/docs.permissions`](#docspermissions)
- [`/entities.list`](#entitieslist)
- [`/people.get`](#peopleget)

### Announcements, Collections, Pins

- [`/announcements.list`](#announcementslist)
- [`/announcements.create`](#announcementscreate)
- [`/announcements.delete`](#announcementsdelete)
- [`/collections.list`](#collectionslist)
- [`/collections.create`](#collectionscreate)
- [`/collections.delete`](#collectionsdelete)
- [`/pins.list`](#pinslist)
- [`/pins.create`](#pinscreate)
- [`/pins.delete`](#pinsdelete)

### Shortcuts

- [`/shortcuts.list`](#shortcutslist)
- [`/shortcuts.get`](#shortcutsget)
- [`/shortcuts.create`](#shortcutscreate)
- [`/shortcuts.update`](#shortcutsupdate)
- [`/shortcuts.delete`](#shortcutsdelete)

### Answers

- [`/answers.list`](#answerslist)
- [`/answers.get`](#answersget)
- [`/answers.create`](#answerscreate)
- [`/answers.update`](#answersupdate)
- [`/answers.delete`](#answersdelete)

### Summarize

- [`/summarize`](#summarize)

### Verification

- [`/verification.list`](#verificationlist)
- [`/verification.verify`](#verificationverify)
- [`/verification.remind`](#verificationremind)

### Messages

- [`/messages.get`](#messagesget)

### Activity

- [`/activity.report`](#activityreport)

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
| [`/datasources.status <name>`](#datasourcesstatus) | Full status for one datasource: visibility, counts, last 5 processing events |
| [`/datasources.config <name>`](#datasourcesconfig) | Live config: object types, ACL settings, trusted domains, icon URL |
| [`/datasources.list --with-status`](#datasourceslist) | All datasources with uploaded/indexed counts and coverage |
| [`/documents.status`](#documentsstatus) | Upload + indexing status for one document |
| [`/documents.count`](#documentscount) | Document count for a custom datasource |
| [`/users.count`](#userscount) | User count for a custom datasource |
| [`/documents.access`](#documentsaccess) | Whether a specific user has access to a specific document |
| [`/debug.document`](#debugdocument) | Per-doc debug payload (status + uploaded permissions) |
| [`/debug.documents`](#debugdocuments) | Bulk debug for many documents (`--from-file`) |
| [`/debug.user`](#debuguser) | Per-user debug payload (status + uploaded groups) |

```text
/datasources.config gdrive
/documents.access --datasource gdrive --object-type Article --id doc-1 --user alice@example.com
/debug.user gdrive alice@example.com
```

### Single-record write

Each write command takes a JSON request body via `--from-file`. Deletes use convenience flags. All accept `--version <n>` for optimistic concurrency.

| Command | Purpose |
| --- | --- |
| [`/index.document`](#indexdocument) | Index one document |
| [`/index.delete-document`](#indexdelete-document) | Delete one document by id |
| [`/index.permissions`](#indexpermissions) | Update document ACL |
| [`/index.user`](#indexuser) | Index one user |
| [`/index.delete-user`](#indexdelete-user) | Delete one user |
| [`/index.group`](#indexgroup) | Index one group |
| [`/index.delete-group`](#indexdelete-group) | Delete one group |
| [`/index.membership`](#indexmembership) | Index one group membership |
| [`/index.delete-membership`](#indexdelete-membership) | Delete one group membership |

```text
/index.document --from-file ./doc.json
/index.delete-document --datasource gdrive --object-type Article --id doc-1
/index.permissions --from-file ./perms.json
```

### Bulk + paged uploads

Bulk endpoints use the standard upload-paging contract (`uploadId`, `isFirstPage`, `isLastPage`, optional `forceRestartUpload`). Wrap your full request body in a JSON file and pass it via `--from-file`.

| Command | Endpoint family |
| --- | --- |
| [`/index.documents`](#indexdocuments) | Paged document index |
| [`/index.bulk-documents`](#indexbulk-documents) | Bulk document index |
| [`/index.bulk-users`](#indexbulk-users) | Bulk user index |
| [`/index.bulk-groups`](#indexbulk-groups) | Bulk group index |
| [`/index.bulk-memberships`](#indexbulk-memberships) | Bulk group memberships |
| [`/people.bulk-employees`](#peoplebulk-employees) | Bulk employee records (org chart) |
| [`/people.bulk-teams`](#peoplebulk-teams) | Bulk team records (org chart) |
| [`/people.index-employee-list`](#peopleindex-employee-list) | Versioned employee list |
| [`/shortcuts.bulk-index`](#shortcutsbulk-index) | Bulk shortcuts via Indexing API ⚠ distinct from Client API `/shortcuts.*` |
| [`/shortcuts.upload`](#shortcutsupload) | Upload shortcuts via Indexing API |

### Process-all (long-running)

Trigger a tenant-wide reprocess after a bulk upload completes. These commands accept an optional `--datasource` filter where applicable.

| Command | Purpose |
| --- | --- |
| [`/index.process-all-documents`](#indexprocess-all-documents) | Reprocess all uploaded documents |
| [`/index.process-all-memberships`](#indexprocess-all-memberships) | Reprocess all uploaded memberships |
| [`/people.process-all-employees-teams`](#peopleprocess-all-employees-teams) | Reprocess all uploaded employees + teams |

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
