# MCP server

`glean_mcp.py` exposes Glean as an MCP server so Claude Code, Claude Desktop,
and Cursor can call Glean search, chat, and agents as native tools.

It reads the same `~/.gleancode/config.json` but forces `mode = "live"` regardless of what
that file says, so MCP tools call the real API by default. Mock mode is available but must be
asked for explicitly — see [Running the MCP server on mock data](#running-the-mcp-server-on-mock-data).

**Install the MCP package (one-time):**

`pip`

```bash
pip install "mcp[cli]>=1,<2"
```

`brew`

```bash
brew install pipx
pipx install "mcp[cli]>=1,<2"
```

The `<2` bound is required — see [MCP SDK v2](#mcp-sdk-v2) below.

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
| `get_flow` | The captured investigation graph — sessions, citations, links. See [docs/FLOW_MAPPER.md](FLOW_MAPPER.md) |
| `get_flow_summary` | What was investigated and what connected to what, in prose |
| `get_flow_collapsed` | The compact view — threads folded into counted nodes |

## Running the MCP server on mock data

Set `GLEAN_MOCK` on the server entry to serve the [mock corpus](MOCK_CORPUS.md) instead of
your tenant — handy for wiring up an agent and testing the tool loop before you have a token:

```json
{
  "mcpServers": {
    "glean": {
      "command": "python3",
      "args": ["/absolute/path/to/glean-code-cli/glean_mcp.py"],
      "env": {"GLEAN_MOCK": "1"}
    }
  }
}
```

Accepted values are `1`, `true`, `yes`, and `on`. Every tool response is then prefixed with:

```text
[MOCK MODE] Fictional demo data, not your organisation's real content — do not cite or act on it as real.
```

The banner is deliberate. An agent cannot tell fabricated results from real ones, and the
corpus returns confident-looking documents with plausible URLs — without a label, made-up
content launders straight into whatever the agent writes or acts on. The same warning is in
each tool's description, so it reaches the model before it calls anything.

For the same reason mock mode is opt-in and never inherited: `mode` in
`~/.gleancode/config.json` is ignored by the server, including `auto`, which would otherwise
flip an agent onto fake data the day a token expires.

Requires Python 3.10+. The REPL itself remains Python 3.9+ and stdlib-only.

## Starting a server from the REPL

The setups above are the normal ones: the client owns the server's lifecycle, spawning
`glean_mcp.py` over **stdio** whenever it needs it. Nothing to start by hand.

When you do want a server running independently — to point several clients at one process, to
watch its log while you work, or to check the thing comes up at all — `/mcp` handles it from
inside `glean`:

```text
/mcp status                 # mcp version, compatibility, and any running server
/mcp config claude-code     # the JSON block to paste, per client
/mcp start --port 9000      # run it detached over HTTP
/mcp config --url           # the JSON block pointing at that running server
/mcp stop
```

```text
── mcp ─────────────────────────────────────────────────────────────
  mcp package    1.29.0  (v1 line, compatible)
  server script  glean_mcp.py
  server         running  pid 73343, up 4m
  endpoint       http://127.0.0.1:8791/mcp
  would serve    mock  [MOCK MODE banner active]
  tools          search, chat, list_agents, run_agent, get_flow,
                 get_flow_summary, get_flow_collapsed
  log            ~/.gleancode/mcp.log
────────────────────────────────────────────────────────────────────
```

**`/mcp start` never uses stdio.** stdio is a pipe pair between a client and the server it
spawned; started from the REPL there would be no client on the other end, and the REPL already
owns its own stdin and stdout. `start` therefore runs `streamable-http` (default) or `sse`,
which a client attaches to by URL — `/mcp config --url` prints that form. This only helps if
your client supports URL-based servers; for a client that spawns commands, use the stdio form.

Details worth knowing:

- **Binds `127.0.0.1` by default.** A live server holds whatever credentials your config has.
  `--host` can widen that; think before it does.
- **The server outlives the REPL.** It is started in its own session, so `/exit` leaves it
  running. State lives in `~/.gleancode/mcp.json`, which is how a later `glean` session still
  finds it, and stale entries are cleared automatically when the process is gone.
- **Mock mode is inherited.** Start it while the REPL is in mock mode (or pass `--mock`) and
  the server serves the built-in corpus with the `[MOCK MODE]` banner on every response.
- **Logs go to `~/.gleancode/mcp.log`.** A server that dies on startup — a port already in
  use, most often — is reported immediately, with the log path for the detail.

### Sitting alongside Glean's own MCP server

Glean ships its own hosted MCP server. It is a different thing from this one: it talks to your
tenant directly, while `glean_mcp.py` wraps the Client REST API and adds mock mode. `/mcp` only
manages this repo's server — it never detects, starts, or talks to Glean's.

They collide in exactly one place. Both would naturally be registered under the key `glean`:

```json
{ "mcpServers": { "glean": { ... } } }
```

Pasting one over the other **silently replaces it** — no error, you simply end up with a
different set of tools than you expected. Use a distinct key to keep both:

```text
/mcp config --name glean-cli
```

```json
{ "mcpServers": { "glean-cli": { "command": "python3", "args": ["…/glean_mcp.py"] } } }
```

`/mcp config` warns about this whenever it emits the default name.

## MCP SDK v2

`glean_mcp.py` targets the **v1 line** of the `mcp` SDK. Install it with an upper bound:

```bash
pip install "mcp[cli]>=1,<2"
```

mcp **2.0.0** (released 2026-07-28) renamed `FastMCP` to `MCPServer` and removed the
`mcp.server.fastmcp` module this server imports. Without the bound, a fresh
`pip install "mcp[cli]"` resolves to 2.x and the server dies on import:

```text
ModuleNotFoundError: No module named 'mcp.server.fastmcp'
```

The server detects that case specifically and says so, rather than telling you to reinstall
the package that just broke it:

```text
Found the 'mcp' package (version 2.0.0), but it does not provide
mcp.server.fastmcp. That module was removed in mcp 2.0.0, which renamed
FastMCP to MCPServer. glean_mcp.py has not been ported to the v2 API yet.
Pin the v1 line:  pip install "mcp[cli]>=1,<2"
```

An existing 1.x install is unaffected — nothing needs to change until you upgrade.

**Outstanding work:** port `glean_mcp.py` to the v2 API (`from mcp.server import MCPServer`;
the decorator API is unchanged, so the four `@mcp.tool()` handlers should carry over largely
as-is). Once ported, drop the `<2` bound here and in the module docstring.

---

[← Back to README](../README.md)
