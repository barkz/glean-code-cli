# MCP server

`glean_mcp.py` exposes Glean as an MCP server so Claude Code, Claude Desktop,
and Cursor can call Glean search, chat, and agents as native tools.

It reads the same `~/.gleancode/config.json` but forces `mode = "live"` regardless of what
that file says, so MCP tools call the real API by default. Mock mode is available but must be
asked for explicitly — see [Running the MCP server on mock data](#running-the-mcp-server-on-mock-data).

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

---

[← Back to README](../README.md)
