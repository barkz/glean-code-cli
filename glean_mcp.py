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
    GLEAN_MOCK       Set to 1/true/yes to serve the built-in fake corpus

Mock mode — opt in, never automatic:
    The server forces live mode by default, whatever ~/.gleancode/config.json
    says. An agent cannot tell fabricated results from real ones, so silently
    answering it from a fictional corpus would launder made-up documents into
    whatever the agent writes or acts on. Set GLEAN_MOCK to override, and every
    tool response is prefixed with a mock-data banner so the label travels with
    the content into the agent's context:

    {
      "mcpServers": {
        "glean": {
          "command": "python3",
          "args": ["/absolute/path/to/glean-code-cli/glean_mcp.py"],
          "env": {"GLEAN_MOCK": "1"}
        }
      }
    }

    Useful for wiring up and testing the tool loop before you have a token.
    See docs/MOCK_CORPUS.md for what the fake corpus contains.

Requires Python 3.10+ and the v1 line of the mcp package:
    pip install "mcp[cli]>=1,<2"

The pin is deliberate. mcp 2.0.0 (released 2026-07-28) renamed FastMCP to
MCPServer and removed the mcp.server.fastmcp module this server imports;
without an upper bound a fresh install resolves to 2.x and fails on import.
Drop the pin once this file is ported to the v2 API.
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

MCP_REQUIREMENT = 'mcp[cli]>=1,<2'


def _installed_mcp_version() -> Optional[str]:
    """Version of the installed mcp package, or None when it isn't installed."""
    try:
        import mcp  # noqa: F401  (imported for the side effect of finding it)
    except ImportError:
        return None
    try:
        from importlib.metadata import version
        return version("mcp")
    except Exception:
        # Importable but unmeasurable — still installed, which is what matters.
        return "unknown"


try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    # Two very different failures land here, and telling them apart matters:
    # the mcp SDK removed mcp.server.fastmcp in v2.0.0 (FastMCP became
    # MCPServer), so on a v2 install the package IS present and the old
    # "pip install mcp[cli]" advice reinstalls the very thing that broke.
    _found = _installed_mcp_version()
    if _found is None:
        print(
            "The 'mcp' package is required to run the Glean MCP server.\n"
            f'Install it with:  pip install "{MCP_REQUIREMENT}"\n',
            file=sys.stderr,
        )
    else:
        print(
            f"Found the 'mcp' package (version {_found}), but it does not provide\n"
            "mcp.server.fastmcp. That module was removed in mcp 2.0.0, which renamed\n"
            "FastMCP to MCPServer. glean_mcp.py has not been ported to the v2 API yet.\n"
            f'Pin the v1 line:  pip install "{MCP_REQUIREMENT}"\n',
            file=sys.stderr,
        )
    sys.exit(1)

from glean_code.config import Config
from glean_code.client import GleanClient, GleanError
from glean_code import flow as _flow
from glean_code import personal as _personal


MOCK_ENV_VAR = "GLEAN_MOCK"

# Prefixed to every tool response when the server is running on mock data, so
# the warning reaches the agent's context alongside the content itself.
MOCK_BANNER = (
    "[MOCK MODE] Fictional demo data, not your organisation's real content — "
    "do not cite or act on it as real."
)

# Appended to each tool's docstring, which is what the agent sees as the tool
# description before it ever calls anything.
_MOCK_DOC = (
    "When the server is started with GLEAN_MOCK=1 this returns fictional "
    "demo data from a built-in corpus, prefixed with a [MOCK MODE] banner."
)


def _wants_mock() -> bool:
    return os.environ.get(MOCK_ENV_VAR, "").strip().lower() in ("1", "true", "yes", "on")


def _build_client() -> tuple[Config, GleanClient]:
    cfg = Config.load()
    if os.environ.get("GLEAN_INSTANCE"):
        cfg.instance = os.environ["GLEAN_INSTANCE"]
    if os.environ.get("GLEAN_TOKEN"):
        cfg.api_token = os.environ["GLEAN_TOKEN"]
    if os.environ.get("GLEAN_ACT_AS"):
        cfg.act_as = os.environ["GLEAN_ACT_AS"]
    # Live unless mock is explicitly requested. Deliberately ignores whatever
    # mode the config file carries: an inherited "auto" that quietly resolves
    # to mock the day a token expires is exactly the failure to avoid here.
    cfg.mode = "mock" if _wants_mock() else "live"
    return cfg, GleanClient(cfg)


_cfg, _client = _build_client()


def _label(text: str) -> str:
    """Prefix a tool response with the mock banner when serving fake data."""
    if _cfg.effective_mode != "mock":
        return text
    return f"{MOCK_BANNER}\n\n{text}"

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

    When the server is started with GLEAN_MOCK=1 this returns fictional demo
    data from a built-in corpus, prefixed with a [MOCK MODE] banner.
    """
    try:
        resp = _client.search(query, page_size=page_size, datasource=datasource)
    except GleanError as e:
        return f"Error: {e}"

    results = resp.get("results", [])
    if not results:
        return _label("No results found.")

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
    return _label("\n".join(lines).rstrip())


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

    When the server is started with GLEAN_MOCK=1 this returns a fictional
    canned answer with fictional citations, prefixed with a [MOCK MODE] banner.
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

    return _label("\n".join(parts)) if parts else _label("(no response)")


@mcp.tool()
def list_agents(query: str = "") -> str:
    """List Glean agents available to the current token.

    Optionally filter by name or description with the query parameter.
    The id field from each result is what run_agent expects.

    When the server is started with GLEAN_MOCK=1 this returns fictional demo
    agents, prefixed with a [MOCK MODE] banner.
    """
    try:
        resp = _client.agents_search(query=query or None)
    except GleanError as e:
        return f"Error: {e}"

    agents = resp.get("agents", [])
    if not agents:
        return _label("No agents found.")

    lines = ["Available agents:\n"]
    for a in agents:
        lines.append(f"  id:          {a.get('id', '?')}")
        if a.get("name"):
            lines.append(f"  name:        {a['name']}")
        if a.get("description"):
            lines.append(f"  description: {a['description']}")
        lines.append("")
    return _label("\n".join(lines).rstrip())


@mcp.tool()
def run_agent(agent_id: str, input: str) -> str:
    """Run a Glean agent and return its final output.

    Blocks until the agent completes (uses the /agents/runs/wait endpoint).
    Use list_agents to discover available agent IDs.

    When the server is started with GLEAN_MOCK=1 this returns a fictional
    canned run output, prefixed with a [MOCK MODE] banner.
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
    return _label(result)


# ── flow mapper ───────────────────────────────────────────────────────────────


def _flow_scope() -> tuple:
    """Flow data is partitioned; never read across instance or mode."""
    return (_cfg.instance or "local").strip(), _cfg.effective_mode


@mcp.tool()
def get_flow(session_id: Optional[int] = None) -> str:
    """Get the captured investigation graph: sessions, questions, cited documents, and links.

    Call this when the user asks what they looked into previously, whether two
    topics are related, or where a document came up before. Returns every
    session in the current instance and mode, each with its turns and
    citations, plus document-to-document and session-to-session links with the
    evidence for each.

    Pass session_id to narrow to one investigation.

    When the server is started with GLEAN_MOCK=1 this returns fictional demo
    data from a built-in corpus, prefixed with a [MOCK MODE] banner.
    """
    instance, mode = _flow_scope()
    try:
        data = _flow.get_flow(session_id=session_id, instance=instance, mode=mode)
    except Exception as e:  # noqa: BLE001
        return f"Error reading the flow database: {e}"
    if not data["sessions"]:
        return _label(f"No captured sessions for {instance} in {mode} mode.")
    return _label(json.dumps(data, indent=2, default=str))


@mcp.tool()
def get_flow_summary() -> str:
    """Summarise what was investigated and which investigations connect to each other.

    Call this instead of get_flow when the user wants the narrative rather than
    the raw graph — "what have I been looking at", "is this related to anything
    I've seen". Returns one entry per session with its questions and documents,
    then the connections between sessions with a plain-language reason for each.

    Connections are the useful part: two investigations that never shared
    context can be linked because a document cited by one mentions the other's
    subject in passing.

    When the server is started with GLEAN_MOCK=1 this returns fictional demo
    data from a built-in corpus, prefixed with a [MOCK MODE] banner.
    """
    instance, mode = _flow_scope()
    try:
        data = _flow.get_flow_summary(instance=instance, mode=mode)
    except Exception as e:  # noqa: BLE001
        return f"Error reading the flow database: {e}"
    if not data["sessions"]:
        return _label(f"No captured sessions for {instance} in {mode} mode.")

    lines = [f"{len(data['sessions'])} session(s) in {instance} ({mode} mode):", ""]
    for s in data["sessions"]:
        head = s["questions"][0] if s["questions"] else f"session {s['session_id']}"
        lines.append(f"[{s['session_id']}] {head}")
        for q in s["questions"][1:]:
            lines.append(f"      also asked: {q}")
        for d in s["documents"]:
            lines.append(f"      cited: {d['title'] or d['doc_id']}")
        lines.append("")
    if data["connections"]:
        lines.append("Connections between sessions:")
        for c in data["connections"]:
            lines.append(f"  {c['a']}")
            lines.append(f"    <-> {c['b']}")
            lines.append(f"    {c['kind']} (score {c['score']}): {c['why']}")
    else:
        lines.append("No connections found between sessions.")
    return _label("\n".join(lines))


@mcp.tool()
def get_flow_collapsed() -> str:
    """Get the compact view: threads folded into single nodes with turn and question counts.

    Call this when the full graph would be too much — a long history, or a
    first look before drilling in with get_flow. Repeated questions collapse
    into one entry with a count, and each thread reports how many turns and
    documents it holds rather than listing them all.

    When the server is started with GLEAN_MOCK=1 this returns fictional demo
    data from a built-in corpus, prefixed with a [MOCK MODE] banner.
    """
    instance, mode = _flow_scope()
    try:
        data = _flow.get_flow_collapsed(instance=instance, mode=mode)
    except Exception as e:  # noqa: BLE001
        return f"Error reading the flow database: {e}"
    if not data["threads"]:
        return _label(f"No captured sessions for {instance} in {mode} mode.")
    return _label(json.dumps(data, indent=2, default=str))


# ── Glean Personal (local index) ──────────────────────────────────────────────
#
# These tools never touch the network or the Glean API. They read the local
# index at ~/.gleancode/personal.db, built by `/personal index <folder>` in the
# REPL, so they work with no token, no instance, and no connection — and they
# are unaffected by GLEAN_MOCK, which governs the Glean-backed tools above.
#
# This is the half of Glean Personal that an external agent consumes: retrieval
# and a content graph, with the agent supplying the model. Nothing here writes
# an answer, because this process has no model and inventing one would launder
# a guess into whatever the agent does next.


def _local(text: str) -> str:
    """Prefix a local-index response so the scope travels with the content."""
    return f"{_personal.LOCAL_BANNER}\n\n{text}"


def _no_index() -> str:
    return _local(
        "The local index is empty. Build one by running `/personal index "
        "<folder>` in the glean-code REPL, then call this tool again."
    )


@mcp.tool()
def local_search(query: str, source: Optional[str] = None, limit: int = 10) -> str:
    """Search the user's own indexed local files: notes, documents, spreadsheets, decks.

    This is separate from Glean's company-wide index — it covers only the
    folders the user chose to index on this machine, and needs no credentials.
    Use it for anything personal or machine-local: "what did I write about X",
    "find my notes on Y", questions about files rather than company knowledge.

    Returns ranked passages with a document id for each. Pass an id to
    local_fetch to read the whole document, or to local_related to see what
    else connects to it. Use source to restrict to one indexed folder
    (local_sources lists them).
    """
    try:
        if _personal.is_empty():
            return _no_index()
        hits = _personal.search(query, limit=limit, source=source)
    except _personal.PersonalError as e:
        return f"Error: {e}"
    except Exception as e:  # noqa: BLE001 - a broken index must not kill the tool loop
        return f"Error reading the local index: {e}"
    if not hits:
        return _local(f"No local documents match '{query}'.")

    lines = [f"{len(hits)} local result(s) for '{query}':", ""]
    for i, hit in enumerate(hits, 1):
        where = f"  \u203a {hit['heading']}" if hit.get("heading") else ""
        lines.append(f"{i}. {hit['title']}{where}")
        lines.append(f"   id: {hit['doc_id']}   folder: {hit['datasource']}   "
                     f"file: {hit['rel_path']}")
        lines.append(f"   {hit['snippet']}")
        lines.append("")
    return _local("\n".join(lines).rstrip())


@mcp.tool()
def local_fetch(doc: str, max_chars: int = 20000) -> str:
    """Read one indexed local document in full.

    Accepts the id from local_search, a file path, or a distinctive fragment of
    the filename or title. Use this after local_search when a snippet is not
    enough to answer.
    """
    try:
        if _personal.is_empty():
            return _no_index()
        found = _personal.fetch(doc, max_chars=max_chars)
    except Exception as e:  # noqa: BLE001
        return f"Error reading the local index: {e}"
    if not found:
        return _local(f"No indexed local document matches '{doc}'.")
    header = [
        f"{found['title']}",
        f"id: {found['doc_id']}   folder: {found['datasource']}",
        f"file: {found['abs_path']}",
        f"modified: {_personal._ago(found['mtime'])}",
        "",
    ]
    body = found["text"]
    if found["truncated"]:
        body += f"\n\n[truncated at {max_chars} characters]"
    return _local("\n".join(header) + body)


@mcp.tool()
def local_sources() -> str:
    """List the local folders the user has indexed, with document counts.

    Call this to find out what local content is available at all, or to get the
    folder labels that local_search accepts as its source argument.
    """
    try:
        if _personal.is_empty():
            return _no_index()
        srcs = _personal.sources()
    except Exception as e:  # noqa: BLE001
        return f"Error reading the local index: {e}"
    lines = ["Indexed local folders:", ""]
    for src in srcs:
        lines.append(f"  {src['label']}  \u2014 {src['documents']} documents, "
                     f"{src['chunks']} passages")
        lines.append(f"    path: {src['root']}")
        lines.append(f"    last indexed: {_personal._ago(src['last_indexed']) or 'never'}")
        lines.append("")
    return _local("\n".join(lines).rstrip())


@mcp.tool()
def local_related(doc: str, limit: int = 8) -> str:
    """Find local documents connected to this one, with the shared phrases as evidence.

    The connections come from a phrase graph built over the indexed content, so
    two files link because they discuss the same things, not because they sit
    in the same folder. Use it to widen a search that found one relevant
    document, or to answer "what else covers this".
    """
    try:
        if _personal.is_empty():
            return _no_index()
        links = _personal.related(doc, limit=limit)
    except _personal.PersonalError as e:
        return _local(str(e))
    except Exception as e:  # noqa: BLE001
        return f"Error reading the local index: {e}"
    if not links:
        return _local(
            f"Nothing is linked to '{doc}'. The graph may not be built yet \u2014 "
            f"`/personal link` in the glean-code REPL builds it."
        )
    lines = [f"{len(links)} document(s) related to '{doc}':", ""]
    for link in links:
        lines.append(f"  {link['title'] or link['doc_id']}  (score {link['score']})")
        lines.append(f"    id: {link['doc_id']}   folder: {link['label']}")
        if link["evidence"]:
            lines.append(f"    shares: {', '.join(link['evidence'][:6])}")
        lines.append("")
    return _local("\n".join(lines).rstrip())


# ── entry point ───────────────────────────────────────────────────────────────

def _parse_args(argv: Optional[list] = None) -> "argparse.Namespace":
    """Transport selection. stdio is the default and what MCP clients spawn.

    The HTTP transports exist so the server can be started detached — from the
    glean REPL's `/mcp start`, or by hand — since a stdio server needs a client
    on the other end of its pipes to be useful at all.
    """
    import argparse
    parser = argparse.ArgumentParser(
        prog="glean_mcp.py",
        description="Glean MCP server. Defaults to stdio, which is what MCP clients spawn.",
    )
    parser.add_argument("--transport", default="stdio",
                        choices=["stdio", "sse", "streamable-http"],
                        help="wire transport (default: stdio)")
    parser.add_argument("--host", default="127.0.0.1",
                        help="bind address for the HTTP transports (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8787,
                        help="bind port for the HTTP transports (default: 8787)")
    return parser.parse_args(argv)


if __name__ == "__main__":
    _args = _parse_args()
    if _args.transport != "stdio":
        # FastMCP reads host/port off its settings object, not run().
        mcp.settings.host = _args.host
        mcp.settings.port = _args.port

    if _cfg.effective_mode == "mock":
        print(
            f"{MOCK_ENV_VAR} is set: serving the built-in fictional corpus. "
            "Every tool response carries a [MOCK MODE] banner.\n"
            f"Unset {MOCK_ENV_VAR} to talk to your real Glean instance.",
            file=sys.stderr,
        )
    elif not _cfg.is_live_ready:
        print(
            "Warning: no instance or token configured.\n"
            "Set GLEAN_INSTANCE + GLEAN_TOKEN env vars, "
            "or run /login inside glean-code first.",
            file=sys.stderr,
        )
    if _args.transport != "stdio":
        print(f"serving MCP over {_args.transport} on "
              f"http://{_args.host}:{_args.port}", file=sys.stderr)
    mcp.run(transport=_args.transport)
