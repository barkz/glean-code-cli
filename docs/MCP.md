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
