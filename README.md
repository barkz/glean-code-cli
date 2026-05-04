# Glean Code

A local, terminal-first client for the Glean Client REST API. Inspired by Claude Code. Built in Python with zero runtime dependencies.

## What you get

- A Claude Code style REPL with an ASCII wordmark
- Slash commands for every major Glean Client API surface
- Full in-terminal documentation for every command via `/help <command>`
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

## First run

```text
/login --instance acme-be.glean.com --token <bearer_token>
/status
/search "quarterly planning"
/chat "summarise the Q2 plan"
```

Without a token the CLI runs in mock mode and returns realistic fake data. Set a token with `/login` and it switches to live calls against `https://<instance>-be.glean.com/rest/api/v1`.

## Commands at a glance

Shell
  /help /status /login /logout /config /mode /history /clear /exit

Chat and Search
  /chat /search /autocomplete /recommendations /feedback

Agents and Tools
  /agents.list /agents.run /tools.list /tools.call

Docs and People
  /docs.get /docs.permissions /entities.list /people.get

Announcements, Collections, Pins
  /announcements.list /announcements.create /announcements.delete
  /collections.list /collections.create
  /pins.list /pins.create

Type `/help <command>` for parameters, examples and the underlying REST endpoint. Bare text with no leading slash is a shortcut for `/chat`.

## Config keys

instance, api_token, act_as, base_url, mode, theme, default_page_size

Change any of them with `/config set <key> <value>`. Use `/mode live|mock|auto` to force a mode.

## Project layout

```text
glean-code/
  glean-code              launcher script
  glean_code/
    __init__.py
    __main__.py           python -m glean_code
    cli.py                REPL loop and banner
    ui.py                 ASCII art, colours, boxes
    config.py             config file load and save
    client.py             Glean REST wrapper + mock responses
    commands.py           slash command parser and handlers
    help_docs.py          per-command documentation
```

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
