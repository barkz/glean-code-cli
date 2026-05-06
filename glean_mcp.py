#!/usr/bin/env python3
"""Glean MCP server.

Exposes Glean's search, chat, and agent surfaces as MCP tools for use with
Claude Code, Claude Desktop, Cursor, and any other MCP-compatible client.

Setup — Claude Code (.claude/settings.json):
    {
      "mcpServers": {
        "glean": {
          "command": "python3",
          "args": ["/absolute/path/to/glean-code-cli/glean_mcp.py"]
        }
      }
    }

Setup — Claude Desktop (~/Library/Application Support/Claude/claude_desktop_config.json):
    {
      "mcpServers": {
        "glean": {
          "command": "python3",
          "args": ["/absolute/path/to/glean-code-cli/glean_mcp.py"]
        }
      }
    }

Credentials are loaded from ~/.gleancode/config.json (written by /login in
the glean-code REPL), or from environment variables:
    GLEAN_INSTANCE   e.g. my-company-be.glean.com
    GLEAN_TOKEN      Glean API bearer token
    GLEAN_ACT_AS     Optional email to impersonate (X-Glean-ActAs)

Requires Python 3.10+ and the mcp package:
    pip install "mcp[cli]"
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Optional

# Allow running directly from the repo root without a package install
_HERE = Path(__file__).parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    print(
        "The 'mcp' package is required to run the Glean MCP server.\n"
        "Install it with:  pip install \"mcp[cli]\"\n",
        file=sys.stderr,
    )
    sys.exit(1)

from glean_code.config import Config
from glean_code.client import GleanClient, GleanError


def _build_client() -> tuple[Config, GleanClient]:
    cfg = Config.load()
    if os.environ.get("GLEAN_INSTANCE"):
        cfg.instance = os.environ["GLEAN_INSTANCE"]
    if os.environ.get("GLEAN_TOKEN"):
        cfg.api_token = os.environ["GLEAN_TOKEN"]
    if os.environ.get("GLEAN_ACT_AS"):
        cfg.act_as = os.environ["GLEAN_ACT_AS"]
    cfg.mode = "live"
    return cfg, GleanClient(cfg)


_cfg, _client = _build_client()

mcp = FastMCP("glean")


# ── tools ────────────────────────────────────────────────────────────────────

@mcp.tool()
def search(
    query: str,
    datasource: Optional[str] = None,
    page_size: int = 10,
) -> str:
    """Search the Glean index across all connected data sources.

    Returns ranked results with titles, URLs, datasource names, and text
    snippets. Use datasource to restrict to a single source (e.g. 'confluence',
    'gdrive', 'slack', 'jira', 'github').
    """
    try:
        resp = _client.search(query, page_size=page_size, datasource=datasource)
    except GleanError as e:
        return f"Error: {e}"

    results = resp.get("results", [])
    if not results:
        return "No results found."

    total = resp.get("totalCount", len(results))
    lines = [f"Search results for '{query}' ({total} total):\n"]
    for i, r in enumerate(results, 1):
        title = r.get("title", "(untitled)")
        url   = r.get("url", "")
        ds    = r.get("datasource", "")
        snip  = ""
        snips = r.get("snippets") or []
        if snips:
            snip = snips[0].get("text", "")
        lines.append(f"{i}. {title}")
        meta = "   " + "  ".join(x for x in [ds, url] if x)
        if meta.strip():
            lines.append(meta)
        if snip:
            lines.append(f"   {snip}")
        lines.append("")
    return "\n".join(lines).rstrip()


@mcp.tool()
def chat(
    message: str,
    chat_id: Optional[str] = None,
    agent: Optional[str] = None,
) -> str:
    """Chat with the Glean Assistant.

    Returns the assistant's response along with any cited sources.
    Pass chat_id to continue an existing conversation thread — the id is
    included in every response and should be forwarded on subsequent turns.
    Use agent to route the message through a named agent configuration.
    """
    try:
        resp = _client.chat(message, chat_id=chat_id, agent=agent)
    except GleanError as e:
        return f"Error: {e}"

    parts: list[str] = []
    thread_id = resp.get("chatId")
    if thread_id:
        parts.append(f"[chat_id: {thread_id}]")

    for msg in resp.get("messages", []):
        text = "".join(f.get("text", "") for f in msg.get("fragments", []))
        if text:
            parts.append(text)
        citations = msg.get("citations", [])
        if citations:
            parts.append("\nSources:")
            for c in citations:
                doc = c.get("sourceDocument", {})
                line = f"  - {doc.get('title', '?')}"
                if doc.get("url"):
                    line += f"  {doc['url']}"
                parts.append(line)

    return "\n".join(parts) if parts else "(no response)"


@mcp.tool()
def list_agents(query: str = "") -> str:
    """List Glean agents available to the current token.

    Optionally filter by name or description with the query parameter.
    The id field from each result is what run_agent expects.
    """
    try:
        resp = _client.agents_search(query=query or None)
    except GleanError as e:
        return f"Error: {e}"

    agents = resp.get("agents", [])
    if not agents:
        return "No agents found."

    lines = ["Available agents:\n"]
    for a in agents:
        lines.append(f"  id:          {a.get('id', '?')}")
        if a.get("name"):
            lines.append(f"  name:        {a['name']}")
        if a.get("description"):
            lines.append(f"  description: {a['description']}")
        lines.append("")
    return "\n".join(lines).rstrip()


@mcp.tool()
def run_agent(agent_id: str, input: str) -> str:
    """Run a Glean agent and return its final output.

    Blocks until the agent completes (uses the /agents/runs/wait endpoint).
    Use list_agents to discover available agent IDs.
    """
    try:
        resp = _client.agent_run(agent_id, input)
    except GleanError as e:
        return f"Error: {e}"

    output = resp.get("output", "")
    run_id = resp.get("runId", "")
    result = output if output else json.dumps(resp, indent=2)
    if run_id:
        result = f"[run_id: {run_id}]\n\n{result}"
    return result


# ── entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if not _cfg.is_live_ready:
        print(
            "Warning: no instance or token configured.\n"
            "Set GLEAN_INSTANCE + GLEAN_TOKEN env vars, "
            "or run /login inside glean-code first.",
            file=sys.stderr,
        )
    mcp.run(transport="stdio")
