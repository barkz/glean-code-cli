"""Scaffold templates for /scaffold command.

Each template is a single self-contained Python file (stdlib only) that
loads credentials from ~/.gleancode/config.json or environment variables
and demonstrates one Glean API surface.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, Optional

# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------

_CHAT = '''#!/usr/bin/env python3
"""Glean chat app — scaffolded by glean-code.

Usage:
    python3 glean_chat.py "your question"   # single turn
    python3 glean_chat.py                   # interactive loop

Config (in priority order):
    Environment variables: GLEAN_INSTANCE, GLEAN_TOKEN, GLEAN_ACT_AS
    ~/.gleancode/config.json  (written by glean-code /login)
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional


def _load_config() -> dict:
    cfg: dict = {"instance": None, "api_token": None, "act_as": None}
    path = Path.home() / ".gleancode" / "config.json"
    if path.exists():
        try:
            saved = json.loads(path.read_text())
            cfg.update({k: v for k, v in saved.items() if k in cfg})
        except Exception:
            pass
    cfg["instance"]  = os.environ.get("GLEAN_INSTANCE")  or cfg["instance"]
    cfg["api_token"] = os.environ.get("GLEAN_TOKEN")     or cfg["api_token"]
    cfg["act_as"]    = os.environ.get("GLEAN_ACT_AS")    or cfg["act_as"]
    return cfg


def _post(url: str, body: dict, token: str, act_as: Optional[str] = None) -> dict:
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if act_as:
        headers["X-Glean-ActAs"] = act_as
    req = urllib.request.Request(
        url, json.dumps(body).encode(), headers, method="POST"
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read())


def chat(
    instance: str,
    token: str,
    message: str,
    chat_id: Optional[str] = None,
    act_as: Optional[str] = None,
) -> dict:
    host = instance.strip().rstrip("/")
    if "://" in host:
        host = host.split("://", 1)[1].split("/")[0]
    url = f"https://{host}/rest/api/v1/chat"
    body: dict = {
        "messages": [
            {"author": "USER", "messageType": "CONTENT",
             "fragments": [{"text": message}]}
        ],
    }
    if chat_id:
        body["chatId"] = chat_id
    return _post(url, body, token, act_as)


def print_response(resp: dict) -> None:
    for msg in resp.get("messages", []):
        text = "".join(f.get("text", "") for f in msg.get("fragments", []))
        print(text)
        citations = msg.get("citations", [])
        if citations:
            print()
            for c in citations:
                doc = c.get("sourceDocument", {})
                print(f"  [{doc.get('title', '?')}]  {doc.get('url', '')}")


def main() -> None:
    cfg = _load_config()
    if not cfg["instance"] or not cfg["api_token"]:
        print(
            "Missing credentials. Either:\\n"
            "  export GLEAN_INSTANCE=your-instance-be.glean.com\\n"
            "  export GLEAN_TOKEN=your-token\\n"
            "or run /login inside glean-code."
        )
        sys.exit(1)

    # Single turn from command line
    if len(sys.argv) > 1:
        message = " ".join(sys.argv[1:])
        try:
            resp = chat(cfg["instance"], cfg["api_token"], message, act_as=cfg["act_as"])
            print_response(resp)
        except urllib.error.HTTPError as e:
            print(f"Error {e.code}: {e.read().decode()}", file=sys.stderr)
            sys.exit(1)
        return

    # Interactive loop
    chat_id: Optional[str] = None
    print("Glean Chat  (Ctrl-C or Ctrl-D to quit)\\n")
    while True:
        try:
            message = input("you › ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not message:
            continue
        try:
            resp = chat(
                cfg["instance"], cfg["api_token"], message,
                chat_id=chat_id, act_as=cfg["act_as"],
            )
            chat_id = resp.get("chatId")
            print("\\nglean › ", end="")
            print_response(resp)
            print()
        except urllib.error.HTTPError as e:
            print(f"Error {e.code}: {e.read().decode()}", file=sys.stderr)


if __name__ == "__main__":
    main()
'''

_SEARCH = '''#!/usr/bin/env python3
"""Glean search app — scaffolded by glean-code.

Usage:
    python3 glean_search.py "quarterly planning"
    python3 glean_search.py "oncall runbook" --datasource confluence
    python3 glean_search.py "eng roadmap" --page-size 5

Config (in priority order):
    Environment variables: GLEAN_INSTANCE, GLEAN_TOKEN, GLEAN_ACT_AS
    ~/.gleancode/config.json  (written by glean-code /login)
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional


def _load_config() -> dict:
    cfg: dict = {"instance": None, "api_token": None, "act_as": None}
    path = Path.home() / ".gleancode" / "config.json"
    if path.exists():
        try:
            saved = json.loads(path.read_text())
            cfg.update({k: v for k, v in saved.items() if k in cfg})
        except Exception:
            pass
    cfg["instance"]  = os.environ.get("GLEAN_INSTANCE")  or cfg["instance"]
    cfg["api_token"] = os.environ.get("GLEAN_TOKEN")     or cfg["api_token"]
    cfg["act_as"]    = os.environ.get("GLEAN_ACT_AS")    or cfg["act_as"]
    return cfg


def search(
    instance: str,
    token: str,
    query: str,
    page_size: int = 10,
    datasource: Optional[str] = None,
    act_as: Optional[str] = None,
) -> dict:
    host = instance.strip().rstrip("/")
    if "://" in host:
        host = host.split("://", 1)[1].split("/")[0]
    url = f"https://{host}/rest/api/v1/search"
    body: dict = {"query": query, "pageSize": page_size}
    if datasource:
        body["requestOptions"] = {"datasourceFilter": datasource}
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if act_as:
        headers["X-Glean-ActAs"] = act_as
    req = urllib.request.Request(
        url, json.dumps(body).encode(), headers, method="POST"
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read())


def print_results(resp: dict) -> None:
    results = resp.get("results", [])
    if not results:
        print("No results.")
        return
    for i, r in enumerate(results, 1):
        title = r.get("title", "(untitled)")
        url   = r.get("url", "")
        ds    = r.get("datasource", "")
        snip  = ""
        snips = r.get("snippets") or []
        if snips:
            snip = snips[0].get("text", "")
        print(f"\\n{i}.  {title}")
        print(f"    {ds}  {url}")
        if snip:
            print(f"    {snip}")


def main() -> None:
    cfg = _load_config()
    if not cfg["instance"] or not cfg["api_token"]:
        print(
            "Missing credentials. Either:\\n"
            "  export GLEAN_INSTANCE=your-instance-be.glean.com\\n"
            "  export GLEAN_TOKEN=your-token\\n"
            "or run /login inside glean-code."
        )
        sys.exit(1)

    args = sys.argv[1:]
    if not args:
        print("Usage: python3 glean_search.py <query> [--datasource <name>] [--page-size <n>]")
        sys.exit(1)

    query_parts: list = []
    datasource: Optional[str] = None
    page_size = 10
    i = 0
    while i < len(args):
        if args[i] == "--datasource" and i + 1 < len(args):
            datasource = args[i + 1]; i += 2
        elif args[i] == "--page-size" and i + 1 < len(args):
            page_size = int(args[i + 1]); i += 2
        else:
            query_parts.append(args[i]); i += 1
    query = " ".join(query_parts)

    try:
        resp = search(
            cfg["instance"], cfg["api_token"], query,
            page_size=page_size, datasource=datasource, act_as=cfg["act_as"],
        )
        total = resp.get("totalCount", "?")
        print(f"Results for \\"{query}\\" ({total} total):")
        print_results(resp)
    except urllib.error.HTTPError as e:
        print(f"Error {e.code}: {e.read().decode()}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
'''

_AGENT = '''#!/usr/bin/env python3
"""Glean agent runner — scaffolded by glean-code.

Usage:
    python3 glean_agent.py list                          # list available agents
    python3 glean_agent.py list "sales"                  # filter by name/description
    python3 glean_agent.py run <agent-id> "your prompt"  # run an agent

Config (in priority order):
    Environment variables: GLEAN_INSTANCE, GLEAN_TOKEN, GLEAN_ACT_AS
    ~/.gleancode/config.json  (written by glean-code /login)
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional


def _load_config() -> dict:
    cfg: dict = {"instance": None, "api_token": None, "act_as": None}
    path = Path.home() / ".gleancode" / "config.json"
    if path.exists():
        try:
            saved = json.loads(path.read_text())
            cfg.update({k: v for k, v in saved.items() if k in cfg})
        except Exception:
            pass
    cfg["instance"]  = os.environ.get("GLEAN_INSTANCE")  or cfg["instance"]
    cfg["api_token"] = os.environ.get("GLEAN_TOKEN")     or cfg["api_token"]
    cfg["act_as"]    = os.environ.get("GLEAN_ACT_AS")    or cfg["act_as"]
    return cfg


def _post(url: str, body: dict, token: str, act_as: Optional[str] = None) -> dict:
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if act_as:
        headers["X-Glean-ActAs"] = act_as
    req = urllib.request.Request(
        url, json.dumps(body).encode(), headers, method="POST"
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read())


def list_agents(instance: str, token: str, query: str = "", act_as: Optional[str] = None) -> dict:
    host = instance.strip().rstrip("/")
    if "://" in host:
        host = host.split("://", 1)[1].split("/")[0]
    return _post(f"https://{host}/rest/api/v1/agents/search", {"query": query}, token, act_as)


def run_agent(
    instance: str,
    token: str,
    agent_id: str,
    prompt: str,
    act_as: Optional[str] = None,
) -> dict:
    host = instance.strip().rstrip("/")
    if "://" in host:
        host = host.split("://", 1)[1].split("/")[0]
    return _post(
        f"https://{host}/rest/api/v1/agents/runs/wait",
        {"agentId": agent_id, "input": prompt},
        token, act_as,
    )


def main() -> None:
    cfg = _load_config()
    if not cfg["instance"] or not cfg["api_token"]:
        print(
            "Missing credentials. Either:\\n"
            "  export GLEAN_INSTANCE=your-instance-be.glean.com\\n"
            "  export GLEAN_TOKEN=your-token\\n"
            "or run /login inside glean-code."
        )
        sys.exit(1)

    args = sys.argv[1:]
    subcmd = args[0] if args else "list"

    if subcmd == "list":
        query = args[1] if len(args) > 1 else ""
        try:
            resp = list_agents(cfg["instance"], cfg["api_token"], query=query, act_as=cfg["act_as"])
        except urllib.error.HTTPError as e:
            print(f"Error {e.code}: {e.read().decode()}", file=sys.stderr)
            sys.exit(1)
        agents = resp.get("agents", [])
        if not agents:
            print("No agents found.")
            return
        print(f"{'ID':<30}  {'Name':<24}  Description")
        print("-" * 80)
        for a in agents:
            print(f"{a.get('id','?'):<30}  {a.get('name',''):<24}  {a.get('description','')}")
        return

    if subcmd == "run":
        if len(args) < 3:
            print("Usage: python3 glean_agent.py run <agent-id> <prompt>")
            sys.exit(1)
        agent_id = args[1]
        prompt   = " ".join(args[2:])
        try:
            resp = run_agent(cfg["instance"], cfg["api_token"], agent_id, prompt, act_as=cfg["act_as"])
        except urllib.error.HTTPError as e:
            print(f"Error {e.code}: {e.read().decode()}", file=sys.stderr)
            sys.exit(1)
        output = resp.get("output", "")
        print(output)
        return

    print("Usage:")
    print("  python3 glean_agent.py list [query]")
    print("  python3 glean_agent.py run <agent-id> <prompt>")
    sys.exit(1)


if __name__ == "__main__":
    main()
'''

TEMPLATES: Dict[str, str] = {
    "chat":   _CHAT,
    "search": _SEARCH,
    "agent":  _AGENT,
}

_OUTPUT_FILES: Dict[str, str] = {
    "chat":   "glean_chat.py",
    "search": "glean_search.py",
    "agent":  "glean_agent.py",
}


def write_scaffold(template: str, output_dir: str) -> str:
    """Write the template file into output_dir. Returns the written file path."""
    content = TEMPLATES[template]
    filename = _OUTPUT_FILES[template]
    dest = Path(output_dir).expanduser().resolve()
    dest.mkdir(parents=True, exist_ok=True)
    out = dest / filename
    out.write_text(content, encoding="utf-8")
    try:
        out.chmod(0o755)
    except Exception:
        pass
    return str(out)


def default_dir(template: str) -> str:
    return f"./glean-{template}"
