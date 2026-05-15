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
    "open": {
        "summary": "Open the configured Glean instance in the default web browser.",
        "usage": "/open [path] [--path <path>] [--print]",
        "params": [
            ("path",     "Optional path to append (positional). e.g. 'search' or '/docs/123'."),
            ("--path",   "Same as the positional path. Either form works."),
            ("--print",  "Print the URL instead of launching a browser. Useful over SSH."),
        ],
        "examples": [
            "/open",
            "/open search",
            "/open /docs/123",
            "/open --print",
        ],
        "endpoint": "(local — strips '-be' from instance host and opens https://<host>{path})",
    },
    "ask": {
        "summary": "Translate a natural-language request into a sequence of Glean Code slash commands using Glean's chat as the planner.",
        "usage": '/ask "<natural-language-request>"   (or shorthand: ?<request>)',
        "params": [
            ("<request>", "Plain English describing what you want to do. Multi-step requests work."),
        ],
        "examples": [
            '/ask "login into acme-be.glean.com with the stored token"',
            '?login into acme-be.glean.com, then search for "Q2 plan"',
            '?show me datasource health and start a chat',
        ],
        "endpoint": "POST /chat (Glean Assistant is used as the planner; output is parsed locally)",
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
        "usage": "/datasources.list [--with-counts] [--with-status] [--sample <n>]",
        "params": [
            ("--with-counts", "Show document counts per datasource."),
            ("--with-status", "Fetch full indexing status per datasource (requires indexing_token)."),
            ("--sample", "Sample size for the underlying search. Default 100."),
        ],
        "examples": [
            "/datasources.list",
            "/datasources.list --with-counts",
            "/datasources.list --with-status",
            "/datasources.list --with-counts --sample 200",
        ],
        "endpoint": "POST /rest/api/v1/search (facets=[datasource]) + POST /api/index/v1/debug/{ds}/status",
    },
    "datasources.status": {
        "summary": "Show full indexing status for a single datasource. Requires an indexing token.",
        "usage": "/datasources.status <datasource>",
        "params": [
            ("datasource", "Datasource name, e.g. slack, gdrive, confluence."),
        ],
        "examples": [
            "/datasources.status slack",
            "/datasources.status gdrive",
        ],
        "endpoint": "POST /api/index/v1/debug/{datasource}/status (beta)",
    },
    "indexing.rotate-token": {
        "summary": "Rotate the indexing API token secret and return the new raw secret.",
        "usage": "/indexing.rotate-token",
        "params": [],
        "examples": ["/indexing.rotate-token"],
        "endpoint": "POST /api/index/v1/rotatetoken",
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
    "pins.delete": {
        "summary": "Remove a pinned result by id.",
        "usage": "/pins.delete <id>",
        "params": [("id", "Pin id from /pins.list.")],
        "examples": ["/pins.delete pin_1"],
        "endpoint": "POST /rest/api/v1/unpin",
    },

    # ---------------- collections delete ----------------
    "collections.delete": {
        "summary": "Delete one or more collections by id.",
        "usage": "/collections.delete <id> [<id>...]",
        "params": [("id", "Collection id(s) from /collections.list. Repeatable.")],
        "examples": ["/collections.delete 1", "/collections.delete 1 2 3"],
        "endpoint": "POST /rest/api/v1/deletecollection",
    },

    # ---------------- shortcuts ----------------
    "shortcuts.list": {
        "summary": "List Go Links (shortcuts) owned by the current user.",
        "usage": "/shortcuts.list [--query <text>] [--page-size <n>]",
        "params": [
            ("--query", "Filter shortcuts by alias or description."),
            ("--page-size", "Number of results. Default 20."),
        ],
        "examples": ["/shortcuts.list", "/shortcuts.list --query eng"],
        "endpoint": "POST /rest/api/v1/listshortcuts",
    },
    "shortcuts.get": {
        "summary": "Look up a Go Link by alias.",
        "usage": "/shortcuts.get <alias>",
        "params": [("alias", "The shortcut alias, e.g. pto.")],
        "examples": ["/shortcuts.get pto", "/shortcuts.get oncall"],
        "endpoint": "POST /rest/api/v1/getshortcut",
    },
    "shortcuts.create": {
        "summary": "Create a new Go Link.",
        "usage": "/shortcuts.create --alias <alias> --url <url> [--description <text>] [--unlisted]",
        "params": [
            ("--alias", "Short alias for the link, e.g. pto."),
            ("--url", "Destination URL."),
            ("--description", "Optional description shown in search."),
            ("--unlisted", "Hide from public listing."),
        ],
        "examples": [
            "/shortcuts.create --alias pto --url https://hr.acme.com/pto",
            "/shortcuts.create --alias oncall --url https://wiki.acme.com/oncall --description \"On-call runbook\"",
        ],
        "endpoint": "POST /rest/api/v1/createshortcut",
    },
    "shortcuts.update": {
        "summary": "Update an existing Go Link.",
        "usage": "/shortcuts.update <id> [--alias <alias>] [--url <url>] [--description <text>]",
        "params": [
            ("id", "Shortcut id from /shortcuts.list."),
            ("--alias", "New alias."),
            ("--url", "New destination URL."),
            ("--description", "New description."),
        ],
        "examples": [
            "/shortcuts.update 1 --url https://hr.acme.com/new-pto",
            "/shortcuts.update 1 --alias vacay --description \"Updated vacation policy\"",
        ],
        "endpoint": "POST /rest/api/v1/updateshortcut",
    },
    "shortcuts.delete": {
        "summary": "Delete a Go Link by id.",
        "usage": "/shortcuts.delete <id>",
        "params": [("id", "Shortcut id from /shortcuts.list.")],
        "examples": ["/shortcuts.delete 1"],
        "endpoint": "POST /rest/api/v1/deleteshortcut",
    },

    # ---------------- answers ----------------
    "answers.list": {
        "summary": "List Q&A answers created by the current user.",
        "usage": "/answers.list",
        "params": [],
        "examples": ["/answers.list"],
        "endpoint": "POST /rest/api/v1/listanswers",
    },
    "answers.get": {
        "summary": "Fetch a single answer by id.",
        "usage": "/answers.get <id>",
        "params": [("id", "Answer id from /answers.list.")],
        "examples": ["/answers.get 1"],
        "endpoint": "POST /rest/api/v1/getanswer",
    },
    "answers.create": {
        "summary": "Create a new Q&A answer.",
        "usage": "/answers.create --question <text> --body <text> [--audience <filter>]",
        "params": [
            ("--question", "The question text."),
            ("--body", "The answer body text."),
            ("--audience", "Optional audience filter string."),
        ],
        "examples": [
            "/answers.create --question \"What is our PTO policy?\" --body \"20 days per year.\"",
        ],
        "endpoint": "POST /rest/api/v1/createanswer",
    },
    "answers.update": {
        "summary": "Edit an existing answer.",
        "usage": "/answers.update <id> [--question <text>] [--body <text>]",
        "params": [
            ("id", "Answer id from /answers.list."),
            ("--question", "Updated question text."),
            ("--body", "Updated answer body text."),
        ],
        "examples": ["/answers.update 1 --body \"25 days per year effective Jan 1.\""],
        "endpoint": "POST /rest/api/v1/editanswer",
    },
    "answers.delete": {
        "summary": "Delete an answer by id.",
        "usage": "/answers.delete <id>",
        "params": [("id", "Answer id from /answers.list.")],
        "examples": ["/answers.delete 1"],
        "endpoint": "POST /rest/api/v1/deleteanswer",
    },

    # ---------------- summarize ----------------
    "summarize": {
        "summary": "Ask Glean AI to summarize a document by URL or id.",
        "usage": "/summarize [--url <url>] [--id <doc-id>] [--query <focus>]",
        "params": [
            ("--url", "Document URL to summarize."),
            ("--id", "Glean document id to summarize."),
            ("--query", "Optional focus question to guide the summary."),
        ],
        "examples": [
            "/summarize --url https://docs.acme.com/q2-plan",
            "/summarize --id doc_123 --query \"What are the key risks?\"",
        ],
        "endpoint": "POST /rest/api/v1/summarize",
    },

    # ---------------- verification ----------------
    "verification.list": {
        "summary": "List documents pending or due for verification.",
        "usage": "/verification.list [--count <n>]",
        "params": [("--count", "Max number of items to return. Default 20.")],
        "examples": ["/verification.list", "/verification.list --count 50"],
        "endpoint": "POST /rest/api/v1/listverifications",
    },
    "verification.verify": {
        "summary": "Mark a document as verified (or unverify it).",
        "usage": "/verification.verify <doc-id> [--action VERIFY|UNVERIFY]",
        "params": [
            ("doc-id", "Glean document id."),
            ("--action", "VERIFY (default) or UNVERIFY."),
        ],
        "examples": [
            "/verification.verify doc_123",
            "/verification.verify doc_123 --action UNVERIFY",
        ],
        "endpoint": "POST /rest/api/v1/verify",
    },
    "verification.remind": {
        "summary": "Set a verification reminder for a document.",
        "usage": "/verification.remind <doc-id> [--days <n>] [--assignee <email>] [--reason <text>]",
        "params": [
            ("doc-id", "Glean document id."),
            ("--days", "Remind in this many days. Default 30."),
            ("--assignee", "Email of the person to assign the reminder to."),
            ("--reason", "Optional reason for the reminder."),
        ],
        "examples": [
            "/verification.remind doc_123",
            "/verification.remind doc_123 --days 7 --assignee alice@acme.com",
        ],
        "endpoint": "POST /rest/api/v1/addverificationreminder",
    },

    # ---------------- messages ----------------
    "messages.get": {
        "summary": "Retrieve a message thread from Slack, Teams, or another datasource.",
        "usage": "/messages.get --id <id> --datasource <name> [--id-type <type>] [--direction BEFORE|AFTER]",
        "params": [
            ("--id", "Message id."),
            ("--datasource", "Datasource name, e.g. slack, msteams."),
            ("--id-type", "Id type. Default MESSAGE_ID."),
            ("--direction", "BEFORE or AFTER — fetch surrounding context."),
        ],
        "examples": [
            "/messages.get --id 1234567890.123456 --datasource slack",
            "/messages.get --id 1234567890.123456 --datasource slack --direction AFTER",
        ],
        "endpoint": "POST /rest/api/v1/messages",
    },

    # ---------------- activity ----------------
    "activity.report": {
        "summary": "Report a document view or edit event to improve search quality.",
        "usage": "/activity.report --url <url> [--action VIEW|EDIT]",
        "params": [
            ("--url", "URL of the document the activity occurred on."),
            ("--action", "Activity type: VIEW (default) or EDIT."),
        ],
        "examples": [
            "/activity.report --url https://docs.acme.com/plan",
            "/activity.report --url https://docs.acme.com/plan --action EDIT",
        ],
        "endpoint": "POST /rest/api/v1/activity",
    },

    # ---------------- insights ----------------
    "insights": {
        "summary": "Retrieve aggregate usage insights from the Glean Insights Dashboard.",
        "usage": "/insights [--assistant] [--agents] [--all] [--no-per-user] [--export <file>]",
        "params": [
            ("--assistant", "Include Assistant usage metrics "
                            "(MAU, WAU, chat messages, AI answers)."),
            ("--agents",    "Include Agents usage metrics."),
            ("--all",       "Include Overview, Assistant and Agents in one call."),
            ("--no-per-user", "Suppress per-user breakdown in the response."),
            ("--export",    "Write results to a CSV file. Columns: section, metric, value."),
        ],
        "examples": [
            "/insights",
            "/insights --all",
            "/insights --assistant",
            "/insights --agents --no-per-user",
            "/insights --all --export insights.csv",
        ],
        "endpoint": "POST /rest/api/v1/insights",
    },

    # ---------------- scaffold ----------------
    "scaffold": {
        "summary": "Generate a standalone Python starter project for a Glean API surface.",
        "usage": "/scaffold <chat|search|agent> [--output <dir>]",
        "params": [
            ("template", "Which template to generate: chat, search, or agent."),
            ("--output",  "Output directory. Prompted interactively if omitted."),
        ],
        "examples": [
            "/scaffold chat",
            "/scaffold search --output ~/projects/glean-search",
            "/scaffold agent --output ./my-agent-app",
        ],
        "endpoint": "(local, writes a standalone .py file)",
    },

    # ---------------- Indexing API: Tier 1 (read-only inspection) ----------------
    "datasources.config": {
        "summary": "Get the live configuration for a custom datasource.",
        "usage": "/datasources.config <datasource>",
        "params": [("datasource", "Datasource name (e.g. gdrive, custom1).")],
        "examples": ["/datasources.config gdrive", "/datasources.config custom1"],
        "endpoint": "POST /api/index/v1/getdatasourceconfig",
    },
    "documents.status": {
        "summary": "Get upload + indexing status for a single document.",
        "usage": "/documents.status --datasource <ds> --object-type <type> --id <doc-id>",
        "params": [
            ("--datasource",  "Datasource name."),
            ("--object-type", "Object type (e.g. Article, Case)."),
            ("--id",          "Datasource-specific document id."),
        ],
        "examples": ["/documents.status --datasource gdrive --object-type Article --id doc-1"],
        "endpoint": "POST /api/index/v1/getdocumentstatus",
    },
    "documents.count": {
        "summary": "Count uploaded documents in a custom datasource.",
        "usage": "/documents.count --datasource <ds>",
        "params": [("--datasource", "Datasource name.")],
        "examples": ["/documents.count --datasource custom1", "/documents.count gdrive"],
        "endpoint": "POST /api/index/v1/getdocumentcount",
    },
    "users.count": {
        "summary": "Count users uploaded for a custom datasource.",
        "usage": "/users.count --datasource <ds>",
        "params": [("--datasource", "Datasource name.")],
        "examples": ["/users.count --datasource custom1"],
        "endpoint": "POST /api/index/v1/getusercount",
    },
    "documents.access": {
        "summary": "Check whether a user has access to a specific document.",
        "usage": "/documents.access --datasource <ds> --object-type <type> --id <doc> --user <email>",
        "params": [
            ("--datasource",  "Datasource name."),
            ("--object-type", "Object type."),
            ("--id",          "Document id."),
            ("--user",        "User email to check (alias: --email)."),
        ],
        "examples": [
            "/documents.access --datasource gdrive --object-type Article --id doc-1 --user alice@example.com",
        ],
        "endpoint": "POST /api/index/v1/checkdocumentaccess",
    },
    "debug.document": {
        "summary": "Get debug information (status + uploaded permissions) for a document.",
        "usage": "/debug.document <datasource> <doc-id> [--object-type <type>]",
        "params": [
            ("datasource",    "Datasource name (positional)."),
            ("doc-id",        "Document id (positional)."),
            ("--object-type", "Object type. Defaults to 'Article'."),
        ],
        "examples": ["/debug.document gdrive doc-1 --object-type Article"],
        "endpoint": "POST /api/index/v1/debug/{datasource}/document",
    },
    "debug.documents": {
        "summary": "Bulk debug for multiple documents in a datasource.",
        "usage": "/debug.documents <datasource> --from-file <items.json>",
        "params": [
            ("datasource",  "Datasource name (positional)."),
            ("--from-file", "JSON array of {objectType, docId} entries."),
        ],
        "examples": ["/debug.documents gdrive --from-file ./debug-batch.json"],
        "endpoint": "POST /api/index/v1/debug/{datasource}/documents",
    },
    "debug.user": {
        "summary": "Get debug information for a user in a datasource.",
        "usage": "/debug.user <datasource> <email>",
        "params": [
            ("datasource", "Datasource name."),
            ("email",      "User email."),
        ],
        "examples": ["/debug.user gdrive alice@example.com"],
        "endpoint": "POST /api/index/v1/debug/{datasource}/user",
    },

    # ---------------- Indexing API: Tier 3 (single-record CRUD) ----------------
    "index.document": {
        "summary": "Index a single document — from a JSON body or a local file path.",
        "usage": "/index.document (--from-file <doc.json> | --path <file>) [--datasource <ds>] "
                 "[--object-type <type>] [--public | --acl-from-file <perms.json>] "
                 "[--id-prefix <s>] [--view-url-prefix <url>] [--version <n>] [--dry-run]",
        "params": [
            ("--from-file",       "JSON file containing a full DocumentDefinition request body."),
            ("--path",            "Local file path. Synthesizes a DocumentDefinition from the file."),
            ("--datasource",      "(with --path) Datasource name."),
            ("--object-type",     "(with --path) Object type (e.g. Article)."),
            ("--public",          "(with --path) Make the doc world-readable. Mutually exclusive with --acl-from-file."),
            ("--acl-from-file",   "(with --path) JSON file with a DocumentPermissionsDefinition applied to the doc."),
            ("--id-prefix",       "(with --path) String prepended to the path-derived id slug."),
            ("--view-url-prefix", "(with --path) Base URL prepended to the relative path. Defaults to file://<absolute>."),
            ("--version",         "Optional version int for optimistic concurrency."),
            ("--dry-run",         "Print the assembled request body and exit without calling the API."),
        ],
        "examples": [
            "/index.document --from-file ./doc.json",
            "/index.document --path ./README.md --datasource custom1 --object-type Article --public",
            "/index.document --path ./team/onboarding.md --datasource custom1 --object-type Article "
                "--acl-from-file ./perms.json --dry-run",
        ],
        "endpoint": "POST /api/index/v1/indexdocument",
    },
    "index.delete-document": {
        "summary": "Delete a single document by id.",
        "usage": "/index.delete-document --datasource <ds> --object-type <type> --id <doc-id> [--version <n>]",
        "params": [
            ("--datasource",  "Datasource name."),
            ("--object-type", "Object type."),
            ("--id",          "Document id."),
            ("--version",     "Optional version int."),
        ],
        "examples": ["/index.delete-document --datasource gdrive --object-type Article --id doc-1"],
        "endpoint": "POST /api/index/v1/deletedocument",
    },
    "index.permissions": {
        "summary": "Update document permissions (ACL).",
        "usage": "/index.permissions --from-file <perms.json>",
        "params": [("--from-file", "JSON file containing the UpdatePermissionsRequest body.")],
        "examples": ["/index.permissions --from-file ./perms.json"],
        "endpoint": "POST /api/index/v1/updatepermissions",
    },
    "index.user": {
        "summary": "Index a single user record.",
        "usage": "/index.user --datasource <ds> --from-file <user.json> [--version <n>]",
        "params": [
            ("--datasource", "Datasource name."),
            ("--from-file",  "JSON file containing the user object."),
            ("--version",    "Optional version int."),
        ],
        "examples": ["/index.user --datasource custom1 --from-file ./user.json"],
        "endpoint": "POST /api/index/v1/indexuser",
    },
    "index.delete-user": {
        "summary": "Delete a user from a datasource.",
        "usage": "/index.delete-user --datasource <ds> --email <email> [--version <n>]",
        "params": [
            ("--datasource", "Datasource name."),
            ("--email",      "User email."),
            ("--version",    "Optional version int."),
        ],
        "examples": ["/index.delete-user --datasource custom1 --email alice@example.com"],
        "endpoint": "POST /api/index/v1/deleteuser",
    },
    "index.group": {
        "summary": "Index a single group.",
        "usage": "/index.group --datasource <ds> --from-file <group.json> [--version <n>]",
        "params": [
            ("--datasource", "Datasource name."),
            ("--from-file",  "JSON file containing the group object."),
            ("--version",    "Optional version int."),
        ],
        "examples": ["/index.group --datasource custom1 --from-file ./group.json"],
        "endpoint": "POST /api/index/v1/indexgroup",
    },
    "index.delete-group": {
        "summary": "Delete a group from a datasource.",
        "usage": "/index.delete-group --datasource <ds> --name <group-name> [--version <n>]",
        "params": [
            ("--datasource", "Datasource name."),
            ("--name",       "Group name (alias: --group)."),
            ("--version",    "Optional version int."),
        ],
        "examples": ["/index.delete-group --datasource custom1 --name engineering"],
        "endpoint": "POST /api/index/v1/deletegroup",
    },
    "index.membership": {
        "summary": "Index a single group membership.",
        "usage": "/index.membership --datasource <ds> --from-file <membership.json> [--version <n>]",
        "params": [
            ("--datasource", "Datasource name."),
            ("--from-file",  "JSON file containing the membership object."),
            ("--version",    "Optional version int."),
        ],
        "examples": ["/index.membership --datasource custom1 --from-file ./membership.json"],
        "endpoint": "POST /api/index/v1/indexmembership",
    },
    "index.delete-membership": {
        "summary": "Delete a single group membership.",
        "usage": "/index.delete-membership --datasource <ds> --from-file <membership.json> [--version <n>]",
        "params": [
            ("--datasource", "Datasource name."),
            ("--from-file",  "JSON file describing the membership to delete."),
            ("--version",    "Optional version int."),
        ],
        "examples": ["/index.delete-membership --datasource custom1 --from-file ./membership.json"],
        "endpoint": "POST /api/index/v1/deletemembership",
    },

    # ---------------- Indexing API: Tier 5 (bulk + process-all) ----------------
    "index.documents": {
        "summary": "Index a batch of documents (paged).",
        "usage": "/index.documents --from-file <body.json>",
        "params": [("--from-file", "JSON file containing IndexDocumentsRequest.")],
        "examples": ["/index.documents --from-file ./batch.json"],
        "endpoint": "POST /api/index/v1/indexdocuments",
    },
    "index.bulk-documents": {
        "summary": "Bulk index documents — from a JSON body or by walking a local file/folder.",
        "usage": "/index.bulk-documents (--from-file <body.json> | --path <file-or-dir>) "
                 "[--datasource <ds>] [--object-type <type>] "
                 "[--public | --acl-from-file <perms.json>] "
                 "[--include <globs>] [--exclude <globs>] [--max-bytes <n>] "
                 "[--id-prefix <s>] [--view-url-prefix <url>] [--upload-id <id>] [--dry-run]",
        "params": [
            ("--from-file",       "JSON file containing the BulkIndexDocumentsRequest body."),
            ("--path",            "Local file or directory. Walks recursively for directories."),
            ("--datasource",      "(with --path) Datasource name."),
            ("--object-type",     "(with --path) Object type applied to every walked file."),
            ("--public",          "(with --path) Make all docs world-readable."),
            ("--acl-from-file",   "(with --path) JSON file with a DocumentPermissionsDefinition applied to every doc."),
            ("--include",         "(with --path) Comma-separated globs to include. Default: *.txt,*.md,*.markdown,*.html,*.htm,*.json"),
            ("--exclude",         "(with --path) Comma-separated globs to exclude. Default skips .git, node_modules, __pycache__, .DS_Store"),
            ("--max-bytes",       "(with --path) Skip files larger than this many bytes. Default 5242880 (5MB)."),
            ("--id-prefix",       "(with --path) Prefix added to each path-derived id slug."),
            ("--view-url-prefix", "(with --path) Base URL prepended to each relative path. Defaults to file:// per file."),
            ("--upload-id",       "(with --path) Override the auto-generated upload id."),
            ("--dry-run",         "Print the assembled request body and exit without calling the API."),
        ],
        "examples": [
            "/index.bulk-documents --from-file ./bulk.json",
            "/index.bulk-documents --path ./docs/ --datasource custom1 --object-type Article --public",
            "/index.bulk-documents --path ./docs/ --datasource custom1 --object-type Article "
                "--public --include '*.md,*.txt' --exclude '**/draft/**' --dry-run",
        ],
        "endpoint": "POST /api/index/v1/bulkindexdocuments",
    },
    "index.bulk-users": {
        "summary": "Bulk index users in pages.",
        "usage": "/index.bulk-users --from-file <body.json>",
        "params": [("--from-file", "JSON file containing BulkIndexUsersRequest.")],
        "examples": ["/index.bulk-users --from-file ./users.json"],
        "endpoint": "POST /api/index/v1/bulkindexusers",
    },
    "index.bulk-groups": {
        "summary": "Bulk index groups in pages.",
        "usage": "/index.bulk-groups --from-file <body.json>",
        "params": [("--from-file", "JSON file containing BulkIndexGroupsRequest.")],
        "examples": ["/index.bulk-groups --from-file ./groups.json"],
        "endpoint": "POST /api/index/v1/bulkindexgroups",
    },
    "index.bulk-memberships": {
        "summary": "Bulk index group memberships in pages.",
        "usage": "/index.bulk-memberships --from-file <body.json>",
        "params": [("--from-file", "JSON file containing BulkIndexMembershipsRequest.")],
        "examples": ["/index.bulk-memberships --from-file ./memberships.json"],
        "endpoint": "POST /api/index/v1/bulkindexmemberships",
    },
    "people.bulk-employees": {
        "summary": "Bulk index employee records (org chart).",
        "usage": "/people.bulk-employees --from-file <body.json>",
        "params": [("--from-file", "JSON file containing BulkIndexEmployeesRequest.")],
        "examples": ["/people.bulk-employees --from-file ./employees.json"],
        "endpoint": "POST /api/index/v1/bulkindexemployees",
    },
    "people.bulk-teams": {
        "summary": "Bulk index team records (org chart).",
        "usage": "/people.bulk-teams --from-file <body.json>",
        "params": [("--from-file", "JSON file containing BulkIndexTeamsRequest.")],
        "examples": ["/people.bulk-teams --from-file ./teams.json"],
        "endpoint": "POST /api/index/v1/bulkindexteams",
    },
    "shortcuts.bulk-index": {
        "summary": "Bulk index shortcuts (Indexing API — distinct from /shortcuts.* Client API).",
        "usage": "/shortcuts.bulk-index --from-file <body.json>",
        "params": [("--from-file", "JSON file containing BulkIndexShortcutsRequest.")],
        "examples": ["/shortcuts.bulk-index --from-file ./shortcuts.json"],
        "endpoint": "POST /api/index/v1/bulkindexshortcuts",
    },
    "shortcuts.upload": {
        "summary": "Upload shortcuts (Indexing API).",
        "usage": "/shortcuts.upload --from-file <body.json>",
        "params": [("--from-file", "JSON file containing UploadShortcutsRequest.")],
        "examples": ["/shortcuts.upload --from-file ./shortcuts.json"],
        "endpoint": "POST /api/index/v1/uploadshortcuts",
    },
    "people.index-employee-list": {
        "summary": "Index a list of employees (with optional per-employee versions).",
        "usage": "/people.index-employee-list --from-file <list.json>",
        "params": [("--from-file", "JSON array of employee entries, or {employees: [...]}.")],
        "examples": ["/people.index-employee-list --from-file ./employees.json"],
        "endpoint": "POST /api/index/v1/indexemployeelist",
    },
    "index.process-all-documents": {
        "summary": "Trigger processing of all uploaded documents (long-running).",
        "usage": "/index.process-all-documents [--datasource <ds>]",
        "params": [("--datasource", "Optional datasource filter.")],
        "examples": ["/index.process-all-documents", "/index.process-all-documents --datasource custom1"],
        "endpoint": "POST /api/index/v1/processalldocuments",
    },
    "index.process-all-memberships": {
        "summary": "Trigger processing of all uploaded group memberships.",
        "usage": "/index.process-all-memberships [--datasource <ds>]",
        "params": [("--datasource", "Optional datasource filter.")],
        "examples": ["/index.process-all-memberships --datasource custom1"],
        "endpoint": "POST /api/index/v1/processallmemberships",
    },
    "people.process-all-employees-teams": {
        "summary": "Trigger processing of all uploaded employees and teams.",
        "usage": "/people.process-all-employees-teams",
        "params": [],
        "examples": ["/people.process-all-employees-teams"],
        "endpoint": "POST /api/index/v1/processallemployeesandteams",
    },
}


COMMAND_GROUPS: List[Tuple[str, List[str]]] = [
    ("Shell",          ["help", "status", "doctor", "login", "logout", "open", "ask", "config", "mode", "history", "clear", "exit"]),
    ("Chat & Search",  ["chat", "search", "datasources.list", "datasources.status", "autocomplete", "recommendations", "feedback"]),
    ("Agents & Tools", ["agents.list", "agents.run", "tools.list", "tools.call"]),
    ("Docs & People",  ["docs.get", "docs.permissions", "entities.list", "people.get"]),
    ("Shortcuts",      ["shortcuts.list", "shortcuts.get", "shortcuts.create", "shortcuts.update", "shortcuts.delete"]),
    ("Answers",        ["answers.list", "answers.get", "answers.create", "answers.update", "answers.delete"]),
    ("Summarize",      ["summarize"]),
    ("Verification",   ["verification.list", "verification.verify", "verification.remind"]),
    ("Messages",       ["messages.get"]),
    ("Activity",       ["activity.report"]),
    ("Announcements",  ["announcements.list", "announcements.create", "announcements.delete"]),
    ("Collections",    ["collections.list", "collections.create", "collections.delete"]),
    ("Pins",           ["pins.list", "pins.create", "pins.delete"]),
    ("Indexing",       ["datasources.status", "datasources.config", "indexing.rotate-token",
                        "documents.status", "documents.count", "documents.access",
                        "users.count",
                        "debug.document", "debug.documents", "debug.user"]),
    ("Indexing — write", ["index.document", "index.delete-document", "index.permissions",
                           "index.user", "index.delete-user",
                           "index.group", "index.delete-group",
                           "index.membership", "index.delete-membership"]),
    ("Indexing — bulk",  ["index.documents", "index.bulk-documents", "index.bulk-users",
                           "index.bulk-groups", "index.bulk-memberships",
                           "shortcuts.bulk-index", "shortcuts.upload",
                           "index.process-all-documents", "index.process-all-memberships"]),
    ("Indexing — people", ["people.bulk-employees", "people.bulk-teams",
                            "people.index-employee-list",
                            "people.process-all-employees-teams"]),
    ("Insights",       ["insights"]),
    ("Scaffold",       ["scaffold"]),
]
