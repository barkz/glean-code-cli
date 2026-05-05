"""In-terminal documentation for every slash command.

Each entry has:
  summary:   one-line description
  usage:     command line signature
  params:    list of (name, description)
  examples:  sample invocations
  endpoint:  the underlying Glean REST path
"""
from __future__ import annotations

from typing import Dict, List, Tuple


CommandDoc = Dict[str, object]

DOCS: Dict[str, CommandDoc] = {

    # ---------------- core shell ----------------
    "help": {
        "summary": "Show help for a command, or list all commands.",
        "usage": "/help [command]",
        "params": [("command", "Optional command name. Omit to list every command.")],
        "examples": ["/help", "/help search", "/help agents.run"],
        "endpoint": "(local)",
    },
    "exit": {
        "summary": "Quit Glean Code.",
        "usage": "/exit",
        "params": [],
        "examples": ["/exit"],
        "endpoint": "(local)",
    },
    "clear": {
        "summary": "Clear the terminal screen.",
        "usage": "/clear",
        "params": [],
        "examples": ["/clear"],
        "endpoint": "(local)",
    },
    "status": {
        "summary": "Show connection status, mode and current config.",
        "usage": "/status",
        "params": [],
        "examples": ["/status"],
        "endpoint": "(local)",
    },
    "login": {
        "summary": "Store a Glean host and API token for live calls.",
        "usage": "/login --instance <host-or-url> --token <token> [--act-as <email>]",
        "params": [
            ("--instance", "The full Glean host, e.g. instance_name-be.glean.com, "
                            "or a full URL like https://instance_name-be.glean.com. "
                            "No suffix is auto-appended. You must include -be "
                            "(or whatever your tenant uses) yourself."),
            ("--token", "A Glean API token with Client scopes."),
            ("--act-as", "Optional user email to impersonate via X-Glean-ActAs."),
        ],
        "examples": [
            "/login --instance instance_name-be.glean.com --token glean_tok_xxx",
            "/login --instance https://instance_name-be.glean.com --token glean_tok_xxx",
            "/login --instance instance_name-be.glean.com --token glean_tok_xxx --act-as jane@example.com",
        ],
        "endpoint": "(local, affects Authorization header)",
    },
    "logout": {
        "summary": "Remove stored credentials. Falls back to mock mode.",
        "usage": "/logout",
        "params": [],
        "examples": ["/logout"],
        "endpoint": "(local)",
    },
    "config": {
        "summary": "View or update configuration keys.",
        "usage": "/config [get <key> | set <key> <value> | list]",
        "params": [
            ("get", "Print the value of a single key."),
            ("set", "Set a key. Valid keys: instance, api_token, act_as, base_url, mode, theme, default_page_size."),
            ("list", "Print the full config."),
        ],
        "examples": [
            "/config list",
            "/config set mode live",
            "/config set default_page_size 20",
        ],
        "endpoint": "(local, ~/.gleancode/config.json)",
    },
    "mode": {
        "summary": "Switch between live, mock and auto mode.",
        "usage": "/mode <live|mock|auto>",
        "params": [("value", "live forces real API calls. mock forces fake data. auto picks based on credentials.")],
        "examples": ["/mode auto", "/mode mock", "/mode live"],
        "endpoint": "(local)",
    },
    "doctor": {
        "summary": "Run a health check on your Glean Code setup. "
                   "Inspects config, URL shape, DNS, TCP and runs a tiny auth probe.",
        "usage": "/doctor",
        "params": [],
        "examples": ["/doctor"],
        "endpoint": "(local checks + POST /rest/api/v1/search probe)",
    },
    "history": {
        "summary": "Show recent commands from this session.",
        "usage": "/history [--limit <n>]",
        "params": [("--limit", "How many entries to show. Default 20.")],
        "examples": ["/history", "/history --limit 5"],
        "endpoint": "(local)",
    },

    # ---------------- chat and search ----------------
    "chat": {
        "summary": "Chat with the Glean Assistant. Continues the active chat by default.",
        "usage": "/chat <message> [--new] [--chat-id <id>] [--agent <name>] [--stream]",
        "params": [
            ("message", "The user message. Wrap in quotes if it has spaces."),
            ("--new", "Start a new chat thread instead of continuing the current one."),
            ("--chat-id", "Continue a specific chat id."),
            ("--agent", "Route the turn through a named agent config."),
            ("--stream", "Request a streaming response."),
        ],
        "examples": [
            "/chat \"what did engineering ship last week?\"",
            "/chat \"summarise the Q2 plan\" --new",
            "/chat \"draft an email to Alice\" --agent sales",
        ],
        "endpoint": "POST /rest/api/v1/chat",
    },
    "search": {
        "summary": "Search the Glean index.",
        "usage": "/search <query> [--page-size <n>] [--datasource <name>]",
        "params": [
            ("query", "Free text query."),
            ("--page-size", "Number of results. Default from config."),
            ("--datasource", "Restrict to a single datasource, e.g. gdrive, slack, jira."),
        ],
        "examples": [
            "/search \"quarterly planning\"",
            "/search \"oncall runbook\" --datasource confluence --page-size 5",
        ],
        "endpoint": "POST /rest/api/v1/search",
    },
    "datasources.list": {
        "summary": "List datasources visible to the current token. "
                   "Derived from a search facet call.",
        "usage": "/datasources.list [--with-counts] [--sample <n>]",
        "params": [
            ("--with-counts", "Show document counts per datasource."),
            ("--sample", "Sample size for the underlying search. Default 100."),
        ],
        "examples": [
            "/datasources.list",
            "/datasources.list --with-counts",
            "/datasources.list --with-counts --sample 200",
        ],
        "endpoint": "POST /rest/api/v1/search (facets=[datasource])",
    },
    "autocomplete": {
        "summary": "Get query suggestions for a partial string.",
        "usage": "/autocomplete <partial>",
        "params": [("partial", "The in-progress query.")],
        "examples": ["/autocomplete \"quart\""],
        "endpoint": "POST /rest/api/v1/autocomplete",
    },
    "recommendations": {
        "summary": "Get recommended documents for a user.",
        "usage": "/recommendations [--user <email>]",
        "params": [("--user", "Target user email. Defaults to the authenticated user.")],
        "examples": ["/recommendations", "/recommendations --user alice@acme.com"],
        "endpoint": "POST /rest/api/v1/recommendations",
    },
    "feedback": {
        "summary": "Send feedback on a result or chat turn.",
        "usage": "/feedback <tracking-token> <rating> [--comment <text>]",
        "params": [
            ("tracking-token", "The trackingToken field from a previous result."),
            ("rating", "THUMBS_UP or THUMBS_DOWN."),
            ("--comment", "Optional free text."),
        ],
        "examples": ["/feedback tok_1 THUMBS_UP --comment \"great answer\""],
        "endpoint": "POST /rest/api/v1/feedback",
    },

    # ---------------- agents and tools ----------------
    "agents.list": {
        "summary": "List agents available to the caller.",
        "usage": "/agents.list [--query <text>]",
        "params": [("--query", "Filter by name or description.")],
        "examples": ["/agents.list", "/agents.list --query sales"],
        "endpoint": "POST /rest/api/v1/agents/search",
    },
    "agents.run": {
        "summary": "Run an agent and wait for the final output.",
        "usage": "/agents.run <agent-id> <input> [--stream]",
        "params": [
            ("agent-id", "The agent id from /agents.list."),
            ("input", "Free text task or prompt."),
            ("--stream", "Use the streaming endpoint."),
        ],
        "examples": ["/agents.run agt_research \"write a market brief on AI in banking\""],
        "endpoint": "POST /rest/api/v1/agents/runs/wait",
    },
    "tools.list": {
        "summary": "List callable tools exposed to agents.",
        "usage": "/tools.list",
        "params": [],
        "examples": ["/tools.list"],
        "endpoint": "POST /rest/api/v1/tools/list",
    },
    "tools.call": {
        "summary": "Invoke a tool with a JSON argument object.",
        "usage": "/tools.call <name> <json-args>",
        "params": [
            ("name", "Tool name from /tools.list."),
            ("json-args", "JSON object of arguments, e.g. {\"query\":\"pto\"}."),
        ],
        "examples": ["/tools.call search '{\"query\":\"pto policy\"}'"],
        "endpoint": "POST /rest/api/v1/tools/call",
    },

    # ---------------- documents and people ----------------
    "docs.get": {
        "summary": "Fetch one or more documents by id or URL.",
        "usage": "/docs.get [--id <id>]... [--url <url>]...",
        "params": [
            ("--id", "Glean document id. Repeatable."),
            ("--url", "Document URL. Repeatable."),
        ],
        "examples": [
            "/docs.get --id doc_123 --id doc_456",
            "/docs.get --url https://docs.acme.com/plan",
        ],
        "endpoint": "POST /rest/api/v1/getdocuments",
    },
    "docs.permissions": {
        "summary": "Fetch the permission list for a document.",
        "usage": "/docs.permissions <doc-id>",
        "params": [("doc-id", "Glean document id.")],
        "examples": ["/docs.permissions doc_123"],
        "endpoint": "POST /rest/api/v1/getdocumentpermissions",
    },
    "entities.list": {
        "summary": "List entities such as people, teams or groups.",
        "usage": "/entities.list [--kind PEOPLE|TEAM|GROUP] [--page-size <n>] [--query <text>]",
        "params": [
            ("--kind", "Entity type. Default PEOPLE."),
            ("--page-size", "Number of results. Default from config."),
            ("--query", "Optional filter string."),
        ],
        "examples": ["/entities.list --kind PEOPLE --query alice"],
        "endpoint": "POST /rest/api/v1/listentities",
    },
    "people.get": {
        "summary": "Look up a person by email.",
        "usage": "/people.get <email>",
        "params": [("email", "The person's email address.")],
        "examples": ["/people.get alice@acme.com"],
        "endpoint": "POST /rest/api/v1/people",
    },

    # ---------------- announcements ----------------
    "announcements.list": {
        "summary": "List current announcements.",
        "usage": "/announcements.list",
        "params": [],
        "examples": ["/announcements.list"],
        "endpoint": "POST /rest/api/v1/announcements/list",
    },
    "announcements.create": {
        "summary": "Create an announcement.",
        "usage": "/announcements.create --title <text> --body <text> [--audience <filter>]",
        "params": [
            ("--title", "Headline for the announcement."),
            ("--body", "Main body text."),
            ("--audience", "Optional audience filter string."),
        ],
        "examples": ["/announcements.create --title \"All hands Friday\" --body \"10am PT\""],
        "endpoint": "POST /rest/api/v1/announcements/create",
    },
    "announcements.delete": {
        "summary": "Delete an announcement by id.",
        "usage": "/announcements.delete <id>",
        "params": [("id", "Announcement id.")],
        "examples": ["/announcements.delete ann_123"],
        "endpoint": "POST /rest/api/v1/announcements/delete",
    },

    # ---------------- collections ----------------
    "collections.list": {
        "summary": "List collections.",
        "usage": "/collections.list",
        "params": [],
        "examples": ["/collections.list"],
        "endpoint": "POST /rest/api/v1/listcollections",
    },
    "collections.create": {
        "summary": "Create a collection.",
        "usage": "/collections.create --name <text> [--description <text>]",
        "params": [
            ("--name", "Collection name."),
            ("--description", "Optional description."),
        ],
        "examples": ["/collections.create --name Onboarding --description \"New hire docs\""],
        "endpoint": "POST /rest/api/v1/createcollection",
    },

    # ---------------- pins ----------------
    "pins.list": {
        "summary": "List pinned results.",
        "usage": "/pins.list",
        "params": [],
        "examples": ["/pins.list"],
        "endpoint": "POST /rest/api/v1/listpins",
    },
    "pins.create": {
        "summary": "Pin a URL to a query.",
        "usage": "/pins.create --query <text> --url <url>",
        "params": [
            ("--query", "Search query to pin the URL to."),
            ("--url", "Target URL."),
        ],
        "examples": ["/pins.create --query pto --url https://hr.acme.com/pto"],
        "endpoint": "POST /rest/api/v1/createpin",
    },
}


COMMAND_GROUPS: List[Tuple[str, List[str]]] = [
    ("Shell",          ["help", "status", "doctor", "login", "logout", "config", "mode", "history", "clear", "exit"]),
    ("Chat & Search",  ["chat", "search", "datasources.list", "autocomplete", "recommendations", "feedback"]),
    ("Agents & Tools", ["agents.list", "agents.run", "tools.list", "tools.call"]),
    ("Docs & People",  ["docs.get", "docs.permissions", "entities.list", "people.get"]),
    ("Announcements",  ["announcements.list", "announcements.create", "announcements.delete"]),
    ("Collections",    ["collections.list", "collections.create"]),
    ("Pins",           ["pins.list", "pins.create"]),
]
