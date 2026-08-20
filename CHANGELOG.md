# Changelog

All notable changes to Glean Code are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/). This project does not tag
releases, so entries are grouped by date rather than version number.

For what Glean Code is and how to run it, see the [README](README.md).

## Unreleased

### Added

- **Visual Studio Code extension** — a native extension bringing the full REPL (slash
  commands, status bar, mock/live switching, secure-token storage) into the editor
  sidebar. In progress.

## 2026-08-18

### Added

- **`/mcp`** — inspect, configure, and run the bundled MCP server without leaving the REPL.
  `/mcp status` reports the installed `mcp` version, whether it can actually run the server,
  and any running instance's pid, URL, uptime, and mode. `/mcp config [client]` prints the
  paste-ready JSON for Claude Code, Claude Desktop, or Cursor. `/mcp start` runs the server
  detached over HTTP and `/mcp stop` terminates it. Documented in
  [docs/COMMANDS.md](docs/COMMANDS.md) and [docs/MCP.md](docs/MCP.md).
- **`--name` on `/mcp config`** — the emitted block keys the server as `glean` by default,
  the same name Glean's own hosted MCP server would use. `--name glean-cli` keeps both
  registered; the default form warns that pasting replaces an existing entry.
- **Transport flags on `glean_mcp.py`** — `--transport stdio|sse|streamable-http`, `--host`,
  and `--port`. stdio remains the default and is what MCP clients spawn; the HTTP transports
  exist so the server can run detached, since a stdio server started from the REPL would have
  no client on the other end of its pipes.
- **`SUPPORT.md`** — best-effort support expectations, triage order, and what makes a bug
  report actionable. Surfaced by GitHub in the new-issue chooser.

### Changed

- **The macOS app bundle is now `Glean Code.app`**, not `Glean.app` — the latter is Glean's
  own desktop client (`com.glean.desktop`). The installer reads `CFBundleIdentifier` before
  writing and refuses a bundle it did not create; `--uninstall` skips one for the same reason.
  A pre-existing `Glean.app` that we own is replaced on the next install.
- **CI workflow renamed** from `tests.yml` to `release.yml`, and it now publishes the built
  zipapp as a downloadable workflow artifact.

### Fixed

- **`pip install "mcp[cli]"` broke fresh installs.** The MCP SDK's 2.0.0 release renamed
  `FastMCP` to `MCPServer` and removed the `mcp.server.fastmcp` module `glean_mcp.py` imports,
  so an unpinned install resolved to 2.x and failed on import. Install instructions now pin
  `mcp[cli]>=1,<2`, and the import guard distinguishes "not installed" from "installed but
  incompatible" instead of advising a reinstall of the version that just broke.
- **`--uninstall` could delete a user's Glean Desktop installation** — it called `rmtree` on
  the app path with no ownership check.

## 2026-08-14

### Added

- **Mock mode for the MCP server** — `GLEAN_MOCK=1` on the server entry serves the mock
  corpus instead of your tenant, so an agent's tool loop can be wired up and tested before
  a token exists. Accepted values: `1`, `true`, `yes`, `on`.
- **Mock corpus** — seventy interlinked documents belonging to one fictional company,
  spread evenly across five faux datasources (`gdrive`, `confluence`, `jira`, `github`,
  `slack` — fourteen each). Every mock endpoint reads from the same corpus, so a URL from
  `/search` resolves in `/docs.get`, `/summarize`, and `/chat` citations. Search is ranked
  against title, tags, body, and container rather than templated.
- **Bring-your-own corpus** — `mock_corpus_path` config key and `GLEAN_MOCK_CORPUS`
  environment variable point mock mode at a custom JSON file. Documented in
  [docs/MOCK_CORPUS.md](docs/MOCK_CORPUS.md).
- Quarter and fiscal-year placeholders (`{Q+1}`, `Q4 FY26`) computed at request time so the
  corpus never reads as stale.

### Changed

- MCP mock responses are prefixed with an explicit fabricated-data banner, repeated in each
  tool's description so it reaches the model before it calls anything.
- The MCP server ignores `mode` in `~/.gleancode/config.json` entirely, including `auto` —
  mock mode is opt-in and never inherited, so an expiring token cannot silently flip an
  agent onto fake data.

### Fixed

- `.gitignore` now covers common secret-file patterns and `__pycache__`.

## 2026-06-19

### Added

- **Browser SSO** — `/auth login` runs OAuth 2.1 authorization code + PKCE against your
  Glean instance, the same SSO path as the web app. Access tokens are stored in
  `~/.gleancode/auth.json` and used automatically by API calls via `effective_api_token`.
  Indexing continues to use a Glean-issued indexing token. See
  [docs/SSO_OAUTH.md](docs/SSO_OAUTH.md).
- `glean_code/auth/` package: `oauth`, `pkce`, `callback_server`, `token_store`, `manager`.

## 2026-06-04

### Added

- **Custom Metadata API** — `/metadata.set-schema`, `/metadata.get-schema`,
  `/metadata.delete-schema`, `/metadata.attach`, and `/metadata.detach` for enriching
  already-indexed documents without re-uploading them. Supports `TEXT`, `PICKLIST`,
  `TEXTLIST`, and `MULTIPICKLIST` key types, inline `--keys`/`--values` or `--from-file`,
  and `--dry-run`. All five work in mock mode. See [docs/METADATA.md](docs/METADATA.md).

## 2026-05-14

### Added

- **Natural-language planner** — `?<request>` and `/ask "..."` build a catalogue of every
  registered command, send it to Glean Assistant with your request, validate each returned
  step against the live command set, and dispatch the plan. Destructive steps are gated
  behind a single `Run all? [y/N]` confirm. Works offline via local pattern-matching.
  Tokens never leave the local process — the planner sees only the placeholder `<stored>`.
  See [docs/NATURAL_LANGUAGE.md](docs/NATURAL_LANGUAGE.md).

## 2026-05-11

### Added

- **Indexing from local files** — `--path <file-or-dir>` on `/index.document` and
  `/index.bulk-documents` walks a file or folder and synthesizes the request body.
  Supports `.txt`, `.md`, `.markdown`, `.html`, `.htm`, `.json`, with `--include`/`--exclude`
  globs, `--public`/`--acl-from-file` permissions, `--max-bytes`, `--id-prefix`,
  `--view-url-prefix`, and `--dry-run`. Path-derived ids are stable across re-runs
  (`team/onboarding.md` → `team-onboarding`).

## 2026-05-07

### Added

- **Indexing API coverage** — 32 of the 37 documented endpoints exposed as commands across
  four tiers: read/debug, single-record write, bulk/paged upload, and process-all.
- **Debug toolkit** — `/debug.document`, `/debug.documents`, `/debug.user`, and
  `/documents.access` answer "is this doc uploaded?", "why can't user X see doc Y?", and
  "what groups did we upload for this user?" without leaving the REPL.
- **Observability counters** — `/datasources.config`, `/documents.count`,
  `/documents.status`, and `/users.count` for health checks on any custom datasource.
- **Bulk and process-all commands** — `/index.bulk-documents|users|groups|memberships`,
  `/people.bulk-employees|teams`, `/shortcuts.bulk-index`, `/shortcuts.upload`,
  `/index.process-all-*`, and `/people.process-all-employees-teams`.
- **Secure token storage** — `token.secure.client` and `token.secure.indexing` references
  are stored in config verbatim and resolved from `$GLEAN_CLIENT_TOKEN` /
  `$GLEAN_INDEXING_TOKEN` at request time. Literal tokens are masked to `***1234` on
  display and stripped from the history buffer. See
  [docs/SECURE_TOKENS.md](docs/SECURE_TOKENS.md).
- MIT license.

### Changed

- All indexing write commands take their request body via `--from-file <json>` so payloads
  stay auditable.
- Every indexing command works in mock mode with any non-empty indexing token.

## 2026-05-06

### Added

- **Insights** — `/insights` with `--assistant`, `--agents`, `--all`, and `--no-per-user`
  flags, plus `--export <file>` to dump all returned metrics to a flat CSV. See
  [docs/INSIGHTS.md](docs/INSIGHTS.md).
- **Client API command surface** — shortcuts (Go Links), answers, summarize, verification,
  messages, activity, announcements, collections, and pins.
- **MCP server** (`glean_mcp.py`) exposing `search`, `chat`, `list_agents`, and `run_agent`
  as native tools for Claude Code, Claude Desktop, and Cursor. Requires Python 3.10+ and
  the `mcp` package; the REPL itself stays Python 3.9+ and stdlib-only. See
  [docs/MCP.md](docs/MCP.md).
- **Tab completion** that cycles through matches — Tab steps forward, Shift+Tab steps back.
- **Powerline-style status bar** showing mode, connected instance, auth state, and active
  chat thread.
- **Test suite** — stdlib `unittest` only, no mocking frameworks and no network calls.
- Per-command in-terminal documentation via `/help <command>`.

## 2026-05-04

### Added

- Initial release — terminal-first REPL client for the Glean Client REST API, Python
  stdlib-only with zero runtime dependencies.
- `/chat`, `/search`, agents, tools, docs, people, and datasource commands.
- `/scaffold chat|search|agent` to generate self-contained stdlib-only starter projects.
- Mock mode by default; live mode the moment credentials are configured.
- Config at `~/.gleancode/config.json`, written with `0o600` permissions.
