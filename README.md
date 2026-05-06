# Glean Code

A local, terminal-first client for the Glean Client REST API. Inspired by Claude Code. Built in Python with zero runtime dependencies.

![Glean Code terminal screenshot](assets/glean_code_cli_example.png)

## What you get

- Slash commands for every major Glean Client API surface
- Full in-terminal documentation for every command via `/help <command>`
- Tab completion for command names, `--flags`, and known enum values
- Live status bar showing mode, connected instance, auth state, and active chat thread
- MCP server (`glean_mcp.py`) for Claude Code, Claude Desktop, and Cursor
- Config stored at `~/.gleancode/config.json`
- Mock mode by default, so you can try every command offline
- Live mode the moment you add an instance and token

## Install and run

```bash
cd glean-code
python3 -m glean_code
# or
./glean-code
```

Python 3.9 or newer. No pip install required. Only the standard library is used.

## Create an alias

After opening up a new terminal just run `glean`.

```bash
alias glean="PYTHONPATH=<YOUR_PATH>>/glean-code-cli python3 -m glean_code"
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

```text
/help
/status
/login
/logout
/config
/mode
/history
/clear
/exit
```

### Chat and Search

```text
/chat
/search
/autocomplete
/recommendations
/feedback
```

### Agents and Tools

```text
/agents.list
/agents.run
/tools.list
/tools.call
```

### Docs and People

```text
/docs.get
/docs.permissions
/entities.list
/people.get
```

### Announcements, Collections, Pins

```text
/announcements.list
/announcements.create
/announcements.delete
/collections.list
/collections.create
/pins.list
/pins.create
```

### Scaffold templates

```text
/scaffold chat
/scaffold search
/scaffold agent
```

Type `/help <command>` for parameters, examples and the underlying REST endpoint. Bare text with no leading slash is a shortcut for `/chat`.

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

## Config keys

instance, api_token, act_as, base_url, mode, theme, default_page_size

Change any of them with `/config set <key> <value>`. Use `/mode live|mock|auto` to force a mode.

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
```

If your tenant uses a slightly different path for a given surface, change it in `glean_code/client.py`. Every method is a small wrapper around `self._post(path, body)` so the swap is a one-liner.

## JSON arguments in /tools.call

Wrap the JSON in single quotes so the shell parser leaves the double quotes intact:

```text
/tools.call search '{"query":"pto policy"}'
```
