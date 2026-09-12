# Architecture

How Glean Code is put together, and where to change things.

## Request flow

```text
cli.py (REPL loop)
  └─ dispatch()               parses /command + args, looks up HANDLERS
       └─ cmd_<name>()        the handler in commands.py
            └─ GleanClient    one thin method per REST endpoint
                 └─ _post / _indexing_post   live HTTP  ── or ──  mock response
```

The mock/live switch is a single chokepoint in [`glean_code/client.py`](../glean_code/client.py):
`_post` and `_indexing_post` check `Config.effective_mode` and answer from the built-in corpus
instead of hitting the network. That is why every command works offline — and why every new
endpoint needs a matching mock branch.

`local` mode routes `/search`, `/chat`, `/autocomplete` and `/getdocuments` through the
personal index instead, reusing the Client API response shapes so every renderer works unchanged.

## Two API surfaces, two tokens

| Surface | Base path | Token | Covers |
| --- | --- | --- | --- |
| Client API | `/rest/api/v1` | `api_token` (or OAuth) | chat, search, agents, tools, docs, people, insights |
| Indexing API | `/api/index/v1` | `indexing_token` | indexing reads, writes, bulk, process-all |

A Client token cannot reach the Indexing API — they have separate headers, base URLs, and mock
dispatchers. Every path this client targets is listed in [REST_PATHS.md](REST_PATHS.md).

## Project layout

```text
glean-code-cli/
  install.py              CLI + macOS app installer (python3 install.py)
  glean_mcp.py            MCP server entry point
  glean_code/
    __main__.py           python -m glean_code
    cli.py                REPL loop and banner
    commands.py           slash command parser and handlers
    client.py             Glean REST wrapper + mock responses
    config.py             config file load and save
    help_docs.py          per-command documentation
    mcp_control.py        /mcp — MCP server diagnostics and process control
    flow.py               /flow — capture, enrich, link, and render investigations
    personal.py           /personal — local content index, search, and graph
    extract.py            text extraction, including Office formats via zipfile
    mock_corpus.py        the fake corpus every mock endpoint reads from
    _indexing_walk.py     --path file walking for indexing commands
    completion.py         readline tab completion
    scaffold.py           project scaffold templates
    ui.py                 ASCII art, colours, boxes
    auth_commands.py      /auth command handlers
    auth/                 OAuth 2.1 + PKCE: oauth, pkce, callback_server,
                          token_store, manager
  tests/                  20 test modules, stdlib unittest only
  docs/                   full reference set — see below
```

## Adding a command

These move in lockstep:

1. `cmd_<name>` in `commands.py`, decorated with `@register("dotted.name")`
2. A `GleanClient` method in `client.py` wrapping `_post` / `_indexing_post`
3. A mock branch in `_mock_response` / `_mock_indexing_response` — required for offline use and tests
4. A `DOCS` entry in `help_docs.py`, or the command is invisible to `/help` and to the planner
5. If it writes, deletes, or changes auth: add the dotted name to `_NL_DESTRUCTIVE`
6. Tests — a mock-mode handler test plus a client/mock test

## Known divergences

Twelve Client API commands currently diverge from Glean's published OpenAPI spec; mock mode
masks all of it. See the [API incompatibility report](../incompat_report.md).

## Tests

See [TESTING.md](TESTING.md).
