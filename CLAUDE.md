# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Glean Code is a terminal-first REPL client for the Glean REST API (chat, search, agents, tools, insights, and the Indexing API), inspired by Claude Code. It is **Python stdlib-only with zero runtime dependencies** — the REPL targets Python 3.9+. The only exception is `glean_mcp.py`, which needs Python 3.10+ and the `mcp` package.

## Commands

```bash
# Run the REPL
python3 -m glean_code

# Install it (builds a stdlib-only zipapp; adds a macOS Spotlight app bundle)
python3 install.py           # --cli-only, --dev, --prefix, --verify, --uninstall

# Pipe a single command (non-interactive; cli.py detects a non-tty stdin)
echo '/search "q2 plan"' | python3 -m glean_code

# Run the full test suite (721 tests, stdlib unittest — works with or without pytest)
python3 -m pytest tests/
python3 -m unittest discover tests/

# Run one test file / class / method
python3 -m pytest tests/test_commands.py
python3 -m unittest tests.test_commands.TestParseArgs
python3 -m unittest tests.test_commands.TestParseArgs.test_flag_with_value
```

There is no build step, no `pip install`, no linter config, and no `pyproject.toml`/`setup.py`. Tests use only the stdlib (`unittest`, `unittest.mock`) and make no network calls.

`install.py` is the only thing that produces an artifact: it stages the package in a temp
directory and emits a zipapp, so nothing is ever built inside the repo. On macOS set
`PYTHONPYCACHEPREFIX=~/.cache/python` to keep `__pycache__` out of the working tree —
Spotlight indexes stray `.pyc` files and they hijack Cmd+Space searches for "glean".

## Mock vs. live mode (central design idea)

Every command works **offline by default**. `Config.effective_mode` resolves to `live` only when a token + instance are present (`auto` mode), otherwise `mock`. The single chokepoint is in [glean_code/client.py](glean_code/client.py): `_post` / `_indexing_post` check `effective_mode` and return `_mock_response(path, body)` / `_mock_indexing_response(path, body)` instead of hitting the network. This means **mock responses are keyed by REST path**, and every new endpoint needs a matching mock shape or it won't work offline (and tests, which run in mock mode, will fail).

## Architecture

The flow is: `cli.py` (REPL loop) → `dispatch()` → a registered handler → a `GleanClient` method → `_post`/`_indexing_post` (live HTTP or mock).

- **[glean_code/cli.py](glean_code/cli.py)** — REPL loop, banner, status bar, readline setup. Wraps `dispatch` so an exception never crashes the REPL.
- **[glean_code/commands.py](glean_code/commands.py)** — the bulk of the code (~2400 lines). Command parser, the `HANDLERS` registry, every `cmd_*` handler, the natural-language planner, and `dispatch`. See "Adding a command" below.
- **[glean_code/client.py](glean_code/client.py)** — `GleanClient` plus all mock responses. Each API method is a thin wrapper around `self._post(path, body)` or `self._indexing_post(path, body)`; to retarget a REST path for a different tenant, edit it here (one line per method).
- **[glean_code/config.py](glean_code/config.py)** — `Config` dataclass, persisted to `~/.gleancode/config.json` (chmod `0o600`). Computes `effective_base_url`, `effective_indexing_base_url`, `effective_*_token`, and `effective_mode`.
- **[glean_code/help_docs.py](glean_code/help_docs.py)** — the `DOCS` dict. Drives `/help <command>`, the NL planner's command catalogue, and the generated [docs/COMMANDS.md](docs/COMMANDS.md). A command with no `DOCS` entry is invisible to `/help` and to the planner.
- **[glean_code/_indexing_walk.py](glean_code/_indexing_walk.py)** — the `--path` file-walking helpers (`path_to_id`, `walk_files`, `file_to_document`, ...) that synthesize Indexing API request bodies from local `.txt/.md/.html/.json` files.
- **[glean_code/completion.py](glean_code/completion.py)** — readline tab completion (Tab/Shift+Tab cycling).
- **[glean_code/ui.py](glean_code/ui.py)** — ANSI color/box/status-bar rendering. All terminal output goes through here.
- **[glean_code/scaffold.py](glean_code/scaffold.py)** — `/scaffold` templates that emit standalone stdlib-only starter scripts.
- **[glean_mcp.py](glean_mcp.py)** — standalone MCP server (search/chat/list_agents/run_agent). Reuses `~/.gleancode/config.json`. Separate from the REPL; the only file requiring the `mcp` package.

### Dispatch rules (`dispatch` in commands.py)

- `?<text>` → `/ask` (natural-language planner shorthand)
- bare text with no leading `/` → `/chat`
- `/<cmd> ...` → looked up in `HANDLERS`; args parsed by `parse_args` into `(positional, flags)` where `--flag value` → `{flag: value}` and a bare `--flag` → `{flag: True}`.

### Two API surfaces, two tokens

Client API (`/rest/api/v1`, `api_token`) and Indexing API (`/api/index/v1`, `indexing_token`) are distinct — a Client token cannot reach indexing endpoints. They have separate headers, base URLs, and mock dispatchers in the client. Indexing write commands take their request body via `--from-file <json>` (or `--path` for documents).

### Natural-language planner (`/ask`, `?`)

`cmd_ask` builds a command catalogue from `HANDLERS` + `DOCS` (auto-syncs as commands are added), sends it to Glean's `/chat`, parses a JSON command array out of the reply, validates each step against `HANDLERS`, and dispatches them. Destructive steps (anything in `_NL_DESTRUCTIVE`, plus `/config set`) trigger a single `Run all? [y/N]` gate. In mock mode it uses `_nl_mock_plan` (local pattern-matching) instead of calling Glean.

## Conventions when changing code

**Adding a command** touches several places in lockstep:
1. Write `cmd_<name>` in commands.py decorated with `@register("dotted.name")`.
2. Add a `GleanClient` method in client.py (a wrapper around `_post`/`_indexing_post`).
3. Add a mock response branch in `_mock_response` / `_mock_indexing_response` — required for offline use and tests.
4. Add a `DOCS` entry in help_docs.py (summary, usage, params, examples, endpoint) or the command is hidden from `/help` and the planner.
5. If it writes/deletes/changes auth, add the dotted name to `_NL_DESTRUCTIVE` in commands.py.
6. Add tests (mock-mode handler test + client/mock test). Reuse the `_mock_session()` helper pattern in the test files.

**Token safety** — never let real secrets reach disk or the history buffer. Secure refs (`token.secure.client` / `token.secure.indexing`) are stored verbatim and resolved from `$GLEAN_CLIENT_TOKEN` / `$GLEAN_INDEXING_TOKEN` at request time via `resolve_secure`. `_sanitize_for_history` masks `--token`/`--indexing-token` values and `/config set <token-key>` values before they enter `command_history`. `_display_token` masks literals to `***1234`. Preserve all of this when adding any command that handles a token.

## Docs

`docs/COMMANDS.md` (full per-command reference, mirrors `/help`), `docs/NATURAL_LANGUAGE.md` (planner design), and `docs/TESTING.md` (test-suite notes) supplement the README. Keep `docs/COMMANDS.md` and the `DOCS` dict consistent when changing command behavior.
