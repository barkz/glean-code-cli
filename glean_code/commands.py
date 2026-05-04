"""Slash command parser and handlers.

The parser supports positional args, --flags with values and bare --flags.
Quoted strings are preserved. JSON arguments can be passed as a single token.
"""
from __future__ import annotations

import json
import shlex
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable, Dict, List, Optional, Tuple  # noqa: F401

from . import ui
from .client import GleanClient, GleanError
from .config import Config
from .help_docs import DOCS, COMMAND_GROUPS


# -------------------- arg parsing --------------------

def parse_args(tokens: List[str]) -> Tuple[List[str], Dict[str, Any]]:
    positional: List[str] = []
    flags: Dict[str, Any] = {}
    i = 0
    while i < len(tokens):
        t = tokens[i]
        if t.startswith("--"):
            key = t[2:]
            if i + 1 < len(tokens) and not tokens[i + 1].startswith("--"):
                flags[key] = tokens[i + 1]
                i += 2
            else:
                flags[key] = True
                i += 1
        else:
            positional.append(t)
            i += 1
    return positional, flags


# -------------------- rendering helpers --------------------

def _render_chat_response(resp: Dict[str, Any]) -> str:
    msgs = resp.get("messages", [])
    out = []
    for m in msgs:
        frags = m.get("fragments", [])
        text = "".join(f.get("text", "") for f in frags)
        out.append(text)
        cites = m.get("citations") or []
        if cites:
            lines = []
            for c in cites:
                d = c.get("sourceDocument", {})
                lines.append(f"{d.get('title','(untitled)')}  {ui.style(d.get('url',''), ui.C.GREY, ui.C.UNDER)}")
            out.append("\n" + ui.style("Citations", ui.C.CYAN, ui.C.BOLD) + "\n" + ui.bullet_list(lines))
    return "\n\n".join(out).strip() or "(no content)"


def _render_search(resp: Dict[str, Any]) -> str:
    results = resp.get("results", [])
    if not results:
        return ui.style("No results.", ui.C.GREY)
    lines = []
    for i, r in enumerate(results, 1):
        title = r.get("title", "(untitled)")
        url   = r.get("url", "")
        ds    = r.get("datasource", "")
        snip  = ""
        snips = r.get("snippets") or []
        if snips:
            snip = snips[0].get("text", "")
        header = f"{ui.style(str(i)+'.', ui.C.BLUE, ui.C.BOLD)} {ui.style(title, ui.C.WHITE, ui.C.BOLD)}"
        meta = ui.style(f"   {ds}  {url}", ui.C.GREY)
        body = ui.style(f"   {snip}", ui.C.WHITE) if snip else ""
        lines.append("\n".join(x for x in [header, meta, body] if x))
    return "\n\n".join(lines)


def _render_json(data: Any) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False)


# -------------------- registry --------------------

Handler = Callable[["Session", List[str], Dict[str, Any]], None]


class Session:
    """Per-run state shared across commands."""
    def __init__(self, config: Config):
        self.config = config
        self.client = GleanClient(config)
        self.current_chat_id: Optional[str] = None
        self.command_history: List[str] = []
        self.running = True

    def refresh_client(self) -> None:
        self.client = GleanClient(self.config)


HANDLERS: Dict[str, Handler] = {}


def register(name: str):
    def deco(fn: Handler) -> Handler:
        HANDLERS[name] = fn
        return fn
    return deco


# -------------------- shell commands --------------------

@register("help")
def cmd_help(s: Session, pos, flags):
    if pos:
        name = pos[0].lstrip("/")
        doc = DOCS.get(name)
        if not doc:
            ui.print_err(f"Unknown command: {name}")
            return
        print(ui.rule(f"/{name}"))
        print("  " + ui.style(doc["summary"], ui.C.WHITE))
        print()
        print("  " + ui.style("Usage", ui.C.CYAN, ui.C.BOLD))
        print("    " + ui.style(doc["usage"], ui.C.YELLOW))
        if doc["params"]:
            print()
            print("  " + ui.style("Parameters", ui.C.CYAN, ui.C.BOLD))
            print(ui.kv_table([(n, d) for n, d in doc["params"]]))
        if doc["examples"]:
            print()
            print("  " + ui.style("Examples", ui.C.CYAN, ui.C.BOLD))
            for ex in doc["examples"]:
                print("    " + ui.style(ex, ui.C.GREEN))
        print()
        print("  " + ui.style("Endpoint", ui.C.CYAN, ui.C.BOLD) + "  " +
              ui.style(str(doc["endpoint"]), ui.C.PURPLE))
        print(ui.rule())
        return

    print(ui.rule("Glean Code commands"))
    for group, names in COMMAND_GROUPS:
        print("\n  " + ui.style(group, ui.C.CYAN, ui.C.BOLD))
        rows = [("/" + n, DOCS[n]["summary"]) for n in names if n in DOCS]
        print(ui.kv_table(rows, colour=ui.C.BLUE))
    print()
    print("  " + ui.style("Tip:", ui.C.YELLOW, ui.C.BOLD) +
          " type /help <command> for details and examples.")
    print(ui.rule())


@register("exit")
def cmd_exit(s: Session, pos, flags):
    s.running = False
    print(ui.style("Goodbye.", ui.C.CYAN))


@register("quit")
def cmd_quit(s: Session, pos, flags):
    cmd_exit(s, pos, flags)


@register("clear")
def cmd_clear(s: Session, pos, flags):
    print("\033[2J\033[H", end="")


@register("status")
def cmd_status(s: Session, pos, flags):
    cfg = s.config
    rows = [
        ("instance",      cfg.instance or ui.style("(unset)", ui.C.GREY)),
        ("base_url",      cfg.effective_base_url or ui.style("(computed from instance)", ui.C.GREY)),
        ("api_token",     ui.style("set", ui.C.GREEN) if cfg.api_token else ui.style("(unset)", ui.C.YELLOW)),
        ("act_as",        cfg.act_as or ui.style("(none)", ui.C.GREY)),
        ("mode",          ui.style(cfg.effective_mode, ui.C.GREEN if cfg.effective_mode == "live" else ui.C.YELLOW)),
        ("mode setting",  cfg.mode),
        ("default_page_size", str(cfg.default_page_size)),
        ("current_chat_id",   s.current_chat_id or ui.style("(none)", ui.C.GREY)),
        ("config file",   "~/.gleancode/config.json"),
    ]
    print(ui.rule("status"))
    print(ui.kv_table(rows))
    print(ui.rule())


@register("login")
def cmd_login(s: Session, pos, flags):
    instance = flags.get("instance")
    token    = flags.get("token")
    act_as   = flags.get("act-as") or flags.get("act_as")
    if not instance or not token:
        ui.print_err("Usage: /login --instance <host-or-url> --token <token>")
        ui.print_info("Enter the full host, e.g. scio-prod-be.glean.com or "
                      "https://scio-prod-be.glean.com. No auto-append.")
        return

    raw = str(instance).strip().rstrip("/")

    # Accept either a full URL or a bare host. No magic suffixes.
    if "://" in raw:
        scheme_host = raw.split("://", 1)
        scheme = scheme_host[0]
        rest   = scheme_host[1]
    else:
        scheme = "https"
        rest   = raw

    host_and_path = rest.split("/", 1)
    host = host_and_path[0]
    path = host_and_path[1] if len(host_and_path) > 1 else ""

    if not host or "." not in host:
        ui.print_err(f"That does not look like a hostname: '{raw}'")
        ui.print_info("Expected something like scio-prod-be.glean.com")
        return

    if "/rest/api/" in path:
        base_url = f"{scheme}://{host}/{path}".rstrip("/")
    else:
        base_url = f"{scheme}://{host}/rest/api/v1"

    s.config.instance  = host            # store the literal host
    s.config.base_url  = base_url
    s.config.api_token = str(token)
    if act_as:
        s.config.act_as = str(act_as)
    s.config.save()
    s.refresh_client()
    ui.print_ok(f"Logged in to {host}.")
    ui.print_info(f"Base URL: {base_url}")
    ui.print_info(f"Mode is now {s.config.effective_mode}.")
    ui.print_info("Run /doctor to verify DNS and auth.")


@register("logout")
def cmd_logout(s: Session, pos, flags):
    s.config.api_token = None
    s.config.act_as = None
    s.config.save()
    s.refresh_client()
    ui.print_ok("Credentials cleared. Back to mock mode.")


@register("config")
def cmd_config(s: Session, pos, flags):
    if not pos or pos[0] == "list":
        data = s.config.to_dict()
        if data.get("api_token"):
            data["api_token"] = "***" + str(data["api_token"])[-4:]
        print(ui.rule("config"))
        print(_render_json(data))
        print(ui.rule())
        return
    action = pos[0]
    if action == "get" and len(pos) >= 2:
        print(getattr(s.config, pos[1], None))
        return
    if action == "set" and len(pos) >= 3:
        key, value = pos[1], pos[2]
        if key == "default_page_size":
            try:
                value = int(value)
            except ValueError:
                ui.print_err("default_page_size must be an integer.")
                return
        if not hasattr(s.config, key):
            ui.print_err(f"Unknown config key: {key}")
            return
        setattr(s.config, key, value)
        s.config.save()
        s.refresh_client()
        ui.print_ok(f"{key} updated.")
        return
    ui.print_err("Usage: /config [get <key> | set <key> <value> | list]")


@register("mode")
def cmd_mode(s: Session, pos, flags):
    if not pos or pos[0] not in ("live", "mock", "auto"):
        ui.print_err("Usage: /mode <live|mock|auto>")
        return
    s.config.mode = pos[0]
    s.config.save()
    ui.print_ok(f"Mode set to {pos[0]}. Effective: {s.config.effective_mode}.")


@register("doctor")
def cmd_doctor(s: Session, pos, flags):
    """Run a health check across config, DNS, TCP and a tiny auth probe."""
    def line(label: str, status: str, detail: str = "", colour: str = ui.C.GREEN):
        tag = ui.style(status.ljust(6), colour, ui.C.BOLD)
        print(f"  {tag}  {ui.style(label, ui.C.WHITE, ui.C.BOLD)}  {ui.style(detail, ui.C.GREY)}")

    print(ui.rule("doctor"))

    # 1. config presence
    cfg = s.config
    if cfg.instance:
        line("instance", "OK", cfg.instance)
    else:
        line("instance", "WARN", "not set, will use mock mode", ui.C.YELLOW)

    if cfg.api_token:
        line("token", "OK", "***" + str(cfg.api_token)[-4:])
    else:
        line("token", "WARN", "not set, will use mock mode", ui.C.YELLOW)

    base = cfg.effective_base_url
    if not base:
        line("base url", "FAIL", "no base url; run /login", ui.C.RED)
        print(ui.rule())
        return
    line("base url", "OK", base)

    # 2. URL sanity check
    parsed = urllib.parse.urlparse(base)
    host = parsed.hostname or ""
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    if not host or "://" in host or " " in host:
        line("url shape", "FAIL", f"malformed host: '{host}'", ui.C.RED)
        print(ui.rule())
        return
    if "https" in host.lower():
        line("url shape", "FAIL", "host contains 'https'. base_url is "
                                    "likely double-prefixed. Run /logout "
                                    "then /login again.", ui.C.RED)
        print(ui.rule())
        return
    line("url shape", "OK", f"host={host} port={port}")

    # 3. DNS
    t0 = time.time()
    try:
        addrs = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        ip = addrs[0][4][0]
        line("dns", "OK", f"{host} -> {ip}  ({int((time.time()-t0)*1000)}ms)")
    except socket.gaierror as e:
        line("dns", "FAIL", f"{host} did not resolve ({e})", ui.C.RED)
        ui.print_info("Check you are on the right network and that the "
                      "hostname pattern matches your Glean tenant.")
        print(ui.rule())
        return

    # 4. TCP
    t0 = time.time()
    try:
        with socket.create_connection((host, port), timeout=5):
            line("tcp", "OK", f"connected in {int((time.time()-t0)*1000)}ms")
    except OSError as e:
        line("tcp", "FAIL", f"cannot connect to {host}:{port} ({e})", ui.C.RED)
        print(ui.rule())
        return

    # 5. Lightweight auth probe: tiny search
    if cfg.effective_mode != "live":
        line("auth probe", "SKIP", f"mode is {cfg.effective_mode}", ui.C.YELLOW)
        print(ui.rule())
        return
    probe_body = json.dumps({"query": "doctor", "pageSize": 1}).encode("utf-8")
    req = urllib.request.Request(
        f"{base}/search", data=probe_body, method="POST",
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {cfg.api_token}",
                 "User-Agent": "glean-code/doctor"},
    )
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            ms = int((time.time() - t0) * 1000)
            line("auth probe", "OK", f"POST /search {resp.status} in {ms}ms")
    except urllib.error.HTTPError as e:
        detail = f"HTTP {e.code}"
        colour = ui.C.RED
        if e.code in (401, 403):
            detail += " (token rejected or missing scope)"
        elif e.code == 404:
            detail += " (endpoint not found, tenant path may differ)"
        line("auth probe", "FAIL", detail, colour)
    except urllib.error.URLError as e:
        line("auth probe", "FAIL", f"{e.reason}", ui.C.RED)
    except Exception as e:
        line("auth probe", "FAIL", str(e), ui.C.RED)

    print(ui.rule())


@register("history")
def cmd_history(s: Session, pos, flags):
    limit = int(flags.get("limit", 20))
    items = s.command_history[-limit:]
    if not items:
        print(ui.style("(no history yet)", ui.C.GREY))
        return
    for i, line in enumerate(items, 1):
        print(f"  {ui.style(str(i).rjust(3), ui.C.GREY)}  {line}")


# -------------------- chat & search --------------------

@register("chat")
def cmd_chat(s: Session, pos, flags):
    if not pos:
        ui.print_err("Usage: /chat <message>  (use quotes for spaces)")
        return
    message = " ".join(pos)
    chat_id = flags.get("chat-id") or flags.get("chat_id")
    if flags.get("new"):
        chat_id = None
        s.current_chat_id = None
    elif not chat_id:
        chat_id = s.current_chat_id
    agent = flags.get("agent")
    stream = bool(flags.get("stream"))

    try:
        resp = s.client.chat(message, chat_id=chat_id, agent=agent, stream=stream)
    except GleanError as e:
        ui.print_err(str(e))
        return
    if resp.get("chatId"):
        s.current_chat_id = resp["chatId"]
    print(ui.box("Glean Assistant", _render_chat_response(resp)))


@register("search")
def cmd_search(s: Session, pos, flags):
    if not pos:
        ui.print_err("Usage: /search <query>")
        return
    query = " ".join(pos)
    page_size = int(flags.get("page-size") or flags.get("page_size") or s.config.default_page_size)
    datasource = flags.get("datasource")
    try:
        resp = s.client.search(query, page_size=page_size, datasource=datasource)
    except GleanError as e:
        ui.print_err(str(e))
        return
    print(ui.rule(f"search: {query}"))
    print(_render_search(resp))
    print(ui.rule())


@register("datasources.list")
def cmd_datasources_list(s: Session, pos, flags):
    sample = int(flags.get("sample") or 100)
    with_counts = bool(flags.get("with-counts") or flags.get("with_counts"))
    try:
        resp = s.client.list_datasources(sample_size=sample)
    except GleanError as e:
        ui.print_err(str(e))
        return
    sources = resp.get("datasources", [])
    if not sources:
        print(ui.style("(no datasources visible to this token)", ui.C.GREY))
        return
    print(ui.rule("datasources"))
    if with_counts:
        rows = [(d["name"], str(d.get("count", 0))) for d in sources]
        print(ui.kv_table(rows))
    else:
        print(ui.bullet_list([d["name"] for d in sources]))
    print(ui.rule())


@register("autocomplete")
def cmd_autocomplete(s: Session, pos, flags):
    if not pos:
        ui.print_err("Usage: /autocomplete <partial>")
        return
    try:
        resp = s.client.autocomplete(" ".join(pos))
    except GleanError as e:
        ui.print_err(str(e))
        return
    suggestions = [r.get("suggestion", "") for r in resp.get("results", [])]
    if not suggestions:
        print(ui.style("(no suggestions)", ui.C.GREY))
        return
    print(ui.bullet_list(suggestions))


@register("recommendations")
def cmd_recs(s: Session, pos, flags):
    try:
        resp = s.client.recommendations(user=flags.get("user"))
    except GleanError as e:
        ui.print_err(str(e))
        return
    print(_render_search(resp))


@register("feedback")
def cmd_feedback(s: Session, pos, flags):
    if len(pos) < 2:
        ui.print_err("Usage: /feedback <tracking-token> <THUMBS_UP|THUMBS_DOWN> [--comment <text>]")
        return
    try:
        resp = s.client.feedback(pos[0], pos[1], comments=flags.get("comment"))
    except GleanError as e:
        ui.print_err(str(e))
        return
    print(_render_json(resp))


# -------------------- agents & tools --------------------

@register("agents.list")
def cmd_agents_list(s: Session, pos, flags):
    try:
        resp = s.client.agents_search(query=flags.get("query"))
    except GleanError as e:
        ui.print_err(str(e))
        return
    rows = [(a.get("id", ""), a.get("name", "") + " — " + a.get("description", ""))
            for a in resp.get("agents", [])]
    if not rows:
        print(ui.style("(no agents)", ui.C.GREY))
        return
    print(ui.kv_table(rows))


@register("agents.run")
def cmd_agents_run(s: Session, pos, flags):
    if len(pos) < 2:
        ui.print_err("Usage: /agents.run <agent-id> <input>")
        return
    agent_id = pos[0]
    input_text = " ".join(pos[1:])
    try:
        resp = s.client.agent_run(agent_id, input_text, stream=bool(flags.get("stream")))
    except GleanError as e:
        ui.print_err(str(e))
        return
    print(ui.box(f"Agent {agent_id}", resp.get("output", _render_json(resp)), colour=ui.C.PURPLE))


@register("tools.list")
def cmd_tools_list(s: Session, pos, flags):
    try:
        resp = s.client.tools_list()
    except GleanError as e:
        ui.print_err(str(e))
        return
    rows = [(t.get("name", ""), t.get("description", "")) for t in resp.get("tools", [])]
    print(ui.kv_table(rows) if rows else ui.style("(no tools)", ui.C.GREY))


@register("tools.call")
def cmd_tools_call(s: Session, pos, flags):
    if len(pos) < 2:
        ui.print_err("Usage: /tools.call <name> <json-args>")
        return
    name = pos[0]
    try:
        arguments = json.loads(" ".join(pos[1:]))
    except json.JSONDecodeError as e:
        ui.print_err(f"Invalid JSON args: {e}")
        return
    try:
        resp = s.client.tools_call(name, arguments)
    except GleanError as e:
        ui.print_err(str(e))
        return
    print(_render_json(resp))


# -------------------- documents & people --------------------

@register("docs.get")
def cmd_docs_get(s: Session, pos, flags):
    ids  = flags.get("id")
    urls = flags.get("url")
    id_list  = [ids]  if isinstance(ids, str)  else []
    url_list = [urls] if isinstance(urls, str) else []
    if not id_list and not url_list:
        ui.print_err("Usage: /docs.get --id <id> or --url <url>")
        return
    try:
        resp = s.client.get_documents(ids=id_list or None, urls=url_list or None)
    except GleanError as e:
        ui.print_err(str(e))
        return
    print(_render_json(resp))


@register("docs.permissions")
def cmd_docs_perms(s: Session, pos, flags):
    if not pos:
        ui.print_err("Usage: /docs.permissions <doc-id>")
        return
    try:
        resp = s.client.document_permissions(pos[0])
    except GleanError as e:
        ui.print_err(str(e))
        return
    print(_render_json(resp))


@register("entities.list")
def cmd_entities_list(s: Session, pos, flags):
    kind = flags.get("kind", "PEOPLE")
    page_size = int(flags.get("page-size") or flags.get("page_size") or s.config.default_page_size)
    try:
        resp = s.client.list_entities(kind=kind, page_size=page_size, query=flags.get("query"))
    except GleanError as e:
        ui.print_err(str(e))
        return
    print(_render_json(resp))


@register("people.get")
def cmd_people_get(s: Session, pos, flags):
    if not pos:
        ui.print_err("Usage: /people.get <email>")
        return
    try:
        resp = s.client.person(pos[0])
    except GleanError as e:
        ui.print_err(str(e))
        return
    print(_render_json(resp))


# -------------------- announcements --------------------

@register("announcements.list")
def cmd_ann_list(s: Session, pos, flags):
    try:
        print(_render_json(s.client.announcements_list()))
    except GleanError as e:
        ui.print_err(str(e))


@register("announcements.create")
def cmd_ann_create(s: Session, pos, flags):
    title = flags.get("title")
    body = flags.get("body")
    if not title or not body:
        ui.print_err("Usage: /announcements.create --title <text> --body <text>")
        return
    try:
        print(_render_json(s.client.announcement_create(str(title), str(body), audience=flags.get("audience"))))
    except GleanError as e:
        ui.print_err(str(e))


@register("announcements.delete")
def cmd_ann_delete(s: Session, pos, flags):
    if not pos:
        ui.print_err("Usage: /announcements.delete <id>")
        return
    try:
        print(_render_json(s.client.announcement_delete(pos[0])))
    except GleanError as e:
        ui.print_err(str(e))


# -------------------- collections --------------------

@register("collections.list")
def cmd_col_list(s: Session, pos, flags):
    try:
        print(_render_json(s.client.collections_list()))
    except GleanError as e:
        ui.print_err(str(e))


@register("collections.create")
def cmd_col_create(s: Session, pos, flags):
    name = flags.get("name")
    if not name:
        ui.print_err("Usage: /collections.create --name <text> [--description <text>]")
        return
    try:
        print(_render_json(s.client.collection_create(str(name), description=flags.get("description"))))
    except GleanError as e:
        ui.print_err(str(e))


# -------------------- pins --------------------

@register("pins.list")
def cmd_pins_list(s: Session, pos, flags):
    try:
        print(_render_json(s.client.pins_list()))
    except GleanError as e:
        ui.print_err(str(e))


@register("pins.create")
def cmd_pins_create(s: Session, pos, flags):
    url = flags.get("url")
    query = flags.get("query")
    if not url or not query:
        ui.print_err("Usage: /pins.create --query <text> --url <url>")
        return
    try:
        print(_render_json(s.client.pin_create(str(url), str(query))))
    except GleanError as e:
        ui.print_err(str(e))


# -------------------- dispatcher --------------------

def dispatch(session: Session, line: str) -> None:
    line = line.strip()
    if not line:
        return
    session.command_history.append(line)

    # bare text = /chat shortcut
    if not line.startswith("/"):
        HANDLERS["chat"](session, [line], {})
        return

    try:
        tokens = shlex.split(line[1:])
    except ValueError as e:
        ui.print_err(f"Parse error: {e}")
        return
    if not tokens:
        return
    name, rest = tokens[0], tokens[1:]
    handler = HANDLERS.get(name)
    if not handler:
        ui.print_err(f"Unknown command: /{name}. Try /help.")
        return
    pos, flags = parse_args(rest)
    handler(session, pos, flags)
