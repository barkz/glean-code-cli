"""Slash command parser and handlers.

The parser supports positional args, --flags with values and bare --flags.
Quoted strings are preserved. JSON arguments can be passed as a single token.
"""
from __future__ import annotations

import csv
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
from .config import Config, SECURE_REFS, is_secure_ref, resolve_secure
from .help_docs import DOCS, COMMAND_GROUPS
from .scaffold import TEMPLATES, write_scaffold, default_dir as _scaffold_default_dir


# -------------------- token display + sanitization --------------------

def _display_token(value: Optional[str]) -> str:
    """Render a stored token for display.

    - Secure refs are shown verbatim with an env-var-set indicator.
    - Literal tokens are masked to last 4 chars.
    - None / empty renders as a dim placeholder.
    """
    if not value:
        return ui.style("(unset)", ui.C.YELLOW)
    if is_secure_ref(value):
        env_var = SECURE_REFS[value]
        if resolve_secure(value):
            return f"{value} {ui.style(f'(${env_var} set)', ui.C.GREEN)}"
        return f"{value} {ui.style(f'(${env_var} not set)', ui.C.RED)}"
    return ui.style("***" + str(value)[-4:], ui.C.GREEN)


def _sanitize_for_history(line: str) -> str:
    """Strip secret-looking values from a command line before storing it.

    Masks:
      - the value after --token / --indexing-token / --indexing_token
      - the value after `/config set api_token` and `/config set indexing_token`
    Secure-ref pointers (e.g. `token.secure.client`) are kept verbatim — they
    are not secrets.
    """
    try:
        toks = shlex.split(line)
    except ValueError:
        return line
    out: List[str] = []
    i = 0
    sensitive_flags = {"--token", "--indexing-token", "--indexing_token"}
    sensitive_keys  = {"api_token", "indexing_token"}
    while i < len(toks):
        cur = toks[i]
        out.append(cur)
        # `--token <value>` style
        if cur in sensitive_flags and i + 1 < len(toks):
            nxt = toks[i + 1]
            out.append(nxt if is_secure_ref(nxt) else "***")
            i += 2
            continue
        # `/config set <key> <value>` style
        if (cur == "set"
                and i >= 1 and toks[i - 1].lstrip("/") == "config"
                and i + 2 < len(toks)
                and toks[i + 1] in sensitive_keys):
            out.append(toks[i + 1])
            val = toks[i + 2]
            out.append(val if is_secure_ref(val) else "***")
            i += 3
            continue
        i += 1
    return " ".join(shlex.quote(t) for t in out)


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
    print(ui.style(
        "Thank you for using Glean Code. If you have any issues or questions DM me, @barkz.",
        ui.C.CYAN,
    ))


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
        ("api_token",     _display_token(cfg.api_token)),
        ("indexing_token", _display_token(cfg.indexing_token)),
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
        ui.print_info("Enter the full host, e.g. instance_name-be.glean.com or "
                      "https://instance_name-be.glean.com. No auto-append.")
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
        ui.print_info("Expected something like instance_name-be.glean.com")
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
        for key in ("api_token", "indexing_token"):
            v = data.get(key)
            if not v:
                continue
            if is_secure_ref(v):
                continue  # ref names are not secrets — leave verbatim
            data[key] = "***" + str(v)[-4:]
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
        if is_secure_ref(cfg.api_token):
            env_var = SECURE_REFS[cfg.api_token]
            if resolve_secure(cfg.api_token):
                line("token", "OK", f"{cfg.api_token} (${env_var} set)")
            else:
                line("token", "FAIL", f"{cfg.api_token} but ${env_var} is not set", ui.C.RED)
        else:
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
    with_status = bool(flags.get("with-status") or flags.get("with_status"))
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
    if with_status:
        if not s.config.indexing_token:
            ui.print_err("--with-status requires an indexing token. Set one with: /config set indexing_token <token>")
            return
        for d in sources:
            name = d["name"]
            count = d.get("count", 0)
            print(ui.style(f"  {name}", ui.C.CYAN, ui.C.BOLD) +
                  ui.style(f"  ({count} docs visible)", ui.C.GREY))
            try:
                st = s.client.datasource_status(name)
                _print_datasource_status(st, indent="    ")
            except GleanError as e:
                print(ui.style(f"    status unavailable: {e}", ui.C.GREY))
            print()
    elif with_counts:
        rows = [(d["name"], str(d.get("count", 0))) for d in sources]
        print(ui.kv_table(rows))
    else:
        print(ui.bullet_list([d["name"] for d in sources]))
    print(ui.rule())


def _print_datasource_status(st: dict, indent: str = "  ") -> None:
    visibility = st.get("datasourceVisibility", "")
    if visibility:
        colour = ui.C.GREEN if visibility == "ENABLED_FOR_ALL" else ui.C.YELLOW
        print(f"{indent}{ui.style('visibility', ui.C.CYAN)}  {ui.style(visibility, colour)}")

    docs = st.get("documents") or {}
    counts = docs.get("counts") or {}

    def _sum_counts(entries) -> int:
        return sum(e.get("count", 0) for e in (entries or []))

    uploaded = _sum_counts(counts.get("uploaded"))
    indexed  = _sum_counts(counts.get("indexed"))
    if uploaded or indexed:
        print(f"{indent}{ui.style('uploaded', ui.C.CYAN)}  {uploaded:,}")
        print(f"{indent}{ui.style('indexed ', ui.C.CYAN)}  {indexed:,}")
        if uploaded:
            pct = indexed / uploaded * 100
            bar_colour = ui.C.GREEN if pct >= 95 else ui.C.YELLOW if pct >= 80 else ui.C.RED
            print(f"{indent}{ui.style('coverage', ui.C.CYAN)}  {ui.style(f'{pct:.1f}%', bar_colour)}")

    history = docs.get("processing_history") or []
    if history:
        last = history[-1]
        event = last.get("eventType") or last.get("status") or ""
        ts    = last.get("timestamp") or last.get("time") or ""
        if event or ts:
            print(f"{indent}{ui.style('last event', ui.C.CYAN)}  {event}  {ui.style(str(ts), ui.C.GREY)}")


@register("datasources.status")
def cmd_datasources_status(s: Session, pos, flags):
    if not pos:
        ui.print_err("Usage: /datasources.status <datasource>")
        return
    if not s.config.indexing_token:
        ui.print_err("Requires an indexing token. Set one with: /config set indexing_token <token>")
        return
    datasource = pos[0]
    try:
        st = s.client.datasource_status(datasource)
    except GleanError as e:
        ui.print_err(str(e))
        return

    print(ui.rule(f"datasource: {datasource}"))
    _print_datasource_status(st, indent="  ")

    # Full processing history
    docs = st.get("documents") or {}
    history = docs.get("processing_history") or []
    if len(history) > 1:
        print()
        print(f"  {ui.style('Processing history', ui.C.CYAN, ui.C.BOLD)}")
        for ev in history[-5:]:
            event = ev.get("eventType") or ev.get("status") or "?"
            ts    = ev.get("timestamp") or ev.get("time") or ""
            print(f"    {ui.style(str(ts), ui.C.GREY)}  {event}")

    # Identity counts
    identity = st.get("identity") or {}
    for kind in ("users", "groups", "memberships"):
        section = identity.get(kind) or {}
        if section:
            print(f"  {ui.style(kind, ui.C.CYAN)}  {section}")

    print(ui.rule())


@register("indexing.rotate-token")
def cmd_indexing_rotate_token(s: Session, pos, flags):
    if not s.config.indexing_token:
        ui.print_err("No indexing token configured. Set one with: /config set indexing_token <token>")
        return
    try:
        resp = s.client.rotate_indexing_token()
    except GleanError as e:
        ui.print_err(str(e))
        return
    new_secret = resp.get("rawSecret", "")
    created_at = resp.get("createdAt", "")
    rotation_period = resp.get("rotationPeriodMinutes", "")
    ui.print_ok("Indexing token rotated.")
    print(ui.kv_table([
        ("new secret",       new_secret),
        ("created_at",       str(created_at)),
        ("rotation_period",  f"{rotation_period} min" if rotation_period else ""),
    ]))
    ui.print_info("Update your stored token with: /config set indexing_token <new_secret>")


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


@register("pins.delete")
def cmd_pins_delete(s: Session, pos, flags):
    if not pos:
        ui.print_err("Usage: /pins.delete <id>")
        return
    try:
        print(_render_json(s.client.pin_delete(pos[0])))
    except GleanError as e:
        ui.print_err(str(e))


# -------------------- collections delete --------------------

@register("collections.delete")
def cmd_col_delete(s: Session, pos, flags):
    if not pos:
        ui.print_err("Usage: /collections.delete <id> [<id>...]")
        return
    try:
        ids = [int(i) for i in pos]
    except ValueError:
        ui.print_err("Collection ids must be integers.")
        return
    try:
        print(_render_json(s.client.collection_delete(ids)))
    except GleanError as e:
        ui.print_err(str(e))


# -------------------- shortcuts --------------------

@register("shortcuts.list")
def cmd_shortcuts_list(s: Session, pos, flags):
    try:
        resp = s.client.shortcuts_list(
            query=flags.get("query"),
            page_size=int(flags.get("page-size") or flags.get("page_size") or 20),
        )
    except GleanError as e:
        ui.print_err(str(e))
        return
    shortcuts = resp.get("shortcuts") or []
    if not shortcuts:
        print(ui.style("(no shortcuts)", ui.C.GREY))
        return
    rows = [(f"[{sc.get('id')}] go/{sc.get('inputAlias', '')}",
             f"{sc.get('destinationUrl', '')}  {ui.style(sc.get('description',''), ui.C.GREY)}")
            for sc in shortcuts]
    print(ui.kv_table(rows))


@register("shortcuts.get")
def cmd_shortcuts_get(s: Session, pos, flags):
    if not pos:
        ui.print_err("Usage: /shortcuts.get <alias>")
        return
    try:
        resp = s.client.shortcut_get(pos[0])
    except GleanError as e:
        ui.print_err(str(e))
        return
    sc = resp.get("shortcut") or resp
    rows = [
        ("ID",          str(sc.get("id", "—"))),
        ("Alias",       f"go/{sc.get('inputAlias', '—')}"),
        ("Destination", sc.get("destinationUrl", "—")),
        ("Description", sc.get("description", "—")),
    ]
    print(ui.kv_table(rows))


@register("shortcuts.create")
def cmd_shortcuts_create(s: Session, pos, flags):
    alias = flags.get("alias")
    url   = flags.get("url")
    if not alias or not url:
        ui.print_err("Usage: /shortcuts.create --alias <alias> --url <url> [--description <text>] [--unlisted]")
        return
    try:
        resp = s.client.shortcut_create(
            alias=str(alias), url=str(url),
            description=flags.get("description"),
            unlisted=bool(flags.get("unlisted")),
        )
    except GleanError as e:
        ui.print_err(str(e))
        return
    print(ui.style(f"Created go/{alias}  (id {resp.get('id')})", ui.C.GREEN))


@register("shortcuts.update")
def cmd_shortcuts_update(s: Session, pos, flags):
    if not pos:
        ui.print_err("Usage: /shortcuts.update <id> [--alias <alias>] [--url <url>] [--description <text>]")
        return
    try:
        sc_id = int(pos[0])
    except ValueError:
        ui.print_err("Shortcut id must be an integer.")
        return
    try:
        print(_render_json(s.client.shortcut_update(
            shortcut_id=sc_id,
            alias=flags.get("alias"),
            url=flags.get("url"),
            description=flags.get("description"),
        )))
    except GleanError as e:
        ui.print_err(str(e))


@register("shortcuts.delete")
def cmd_shortcuts_delete(s: Session, pos, flags):
    if not pos:
        ui.print_err("Usage: /shortcuts.delete <id>")
        return
    try:
        sc_id = int(pos[0])
    except ValueError:
        ui.print_err("Shortcut id must be an integer.")
        return
    try:
        print(_render_json(s.client.shortcut_delete(sc_id)))
    except GleanError as e:
        ui.print_err(str(e))


# -------------------- answers --------------------

@register("answers.list")
def cmd_answers_list(s: Session, pos, flags):
    try:
        resp = s.client.answers_list()
    except GleanError as e:
        ui.print_err(str(e))
        return
    answers = resp.get("answers") or []
    if not answers:
        print(ui.style("(no answers)", ui.C.GREY))
        return
    for a in answers:
        print(ui.style(f"[{a.get('id')}] {a.get('question','')}", ui.C.WHITE, ui.C.BOLD))
        print(f"       {ui.style(a.get('bodyText',''), ui.C.GREY)}")
        print()


@register("answers.get")
def cmd_answers_get(s: Session, pos, flags):
    if not pos:
        ui.print_err("Usage: /answers.get <id>")
        return
    try:
        answer_id = int(pos[0])
    except ValueError:
        ui.print_err("Answer id must be an integer.")
        return
    try:
        resp = s.client.answer_get(answer_id)
    except GleanError as e:
        ui.print_err(str(e))
        return
    a = resp.get("answer") or resp
    print(ui.rule(f"Answer {a.get('id', '')}"))
    print(ui.style(a.get("question", ""), ui.C.WHITE, ui.C.BOLD))
    print(ui.style(a.get("bodyText", ""), ui.C.WHITE))
    print(ui.rule())


@register("answers.create")
def cmd_answers_create(s: Session, pos, flags):
    question = flags.get("question")
    body_text = flags.get("body")
    if not question or not body_text:
        ui.print_err("Usage: /answers.create --question <text> --body <text> [--audience <filter>]")
        return
    try:
        resp = s.client.answer_create(str(question), str(body_text),
                                      audience=flags.get("audience"))
    except GleanError as e:
        ui.print_err(str(e))
        return
    print(ui.style(f"Created answer id {resp.get('id')}", ui.C.GREEN))


@register("answers.update")
def cmd_answers_update(s: Session, pos, flags):
    if not pos:
        ui.print_err("Usage: /answers.update <id> [--question <text>] [--body <text>]")
        return
    try:
        answer_id = int(pos[0])
    except ValueError:
        ui.print_err("Answer id must be an integer.")
        return
    try:
        print(_render_json(s.client.answer_update(
            answer_id,
            question=flags.get("question"),
            body_text=flags.get("body"),
        )))
    except GleanError as e:
        ui.print_err(str(e))


@register("answers.delete")
def cmd_answers_delete(s: Session, pos, flags):
    if not pos:
        ui.print_err("Usage: /answers.delete <id>")
        return
    try:
        answer_id = int(pos[0])
    except ValueError:
        ui.print_err("Answer id must be an integer.")
        return
    try:
        print(_render_json(s.client.answer_delete(answer_id)))
    except GleanError as e:
        ui.print_err(str(e))


# -------------------- summarize --------------------

@register("summarize")
def cmd_summarize(s: Session, pos, flags):
    url    = flags.get("url")
    doc_id = flags.get("id")
    query  = flags.get("query") or (" ".join(pos) if pos else None)
    if not url and not doc_id:
        ui.print_err("Usage: /summarize [--url <url>] [--id <doc-id>] [--query <focus>]")
        return
    try:
        resp = s.client.summarize(url=url, doc_id=doc_id, query=query)
    except GleanError as e:
        ui.print_err(str(e))
        return
    summary = resp.get("summary") or resp.get("text") or _render_json(resp)
    label = url or doc_id or "document"
    print(ui.box(f"Summary: {label}", summary))


# -------------------- verification --------------------

@register("verification.list")
def cmd_verification_list(s: Session, pos, flags):
    count = int(flags.get("count") or flags.get("limit") or 20)
    try:
        resp = s.client.verification_list(count=count)
    except GleanError as e:
        ui.print_err(str(e))
        return
    items = resp.get("verifications") or []
    if not items:
        print(ui.style("(no documents pending verification)", ui.C.GREY))
        return
    print(ui.rule("Verification queue"))
    for v in items:
        status = v.get("status", "UNKNOWN")
        colour = ui.C.GREEN if status == "VERIFIED" else ui.C.YELLOW
        ts = _fmt_ts(v.get("lastVerifiedTs"))
        print(f"  {ui.style(status.ljust(12), colour)}  "
              f"{ui.style(v.get('title',''), ui.C.WHITE)}  "
              f"{ui.style(v.get('documentId',''), ui.C.GREY)}")
        if ts != "—":
            print(f"  {'':12}  last verified {ts}")
    print(ui.rule())


@register("verification.verify")
def cmd_verification_verify(s: Session, pos, flags):
    if not pos:
        ui.print_err("Usage: /verification.verify <doc-id> [--action VERIFY|UNVERIFY]")
        return
    try:
        resp = s.client.verification_verify(pos[0], action=flags.get("action"))
    except GleanError as e:
        ui.print_err(str(e))
        return
    print(ui.style(f"Marked {pos[0]} as {resp.get('status','verified')}", ui.C.GREEN))


@register("verification.remind")
def cmd_verification_remind(s: Session, pos, flags):
    if not pos:
        ui.print_err("Usage: /verification.remind <doc-id> [--days <n>] [--assignee <email>] [--reason <text>]")
        return
    days = int(flags.get("days") or 30)
    try:
        resp = s.client.verification_remind(
            pos[0],
            remind_in_days=days,
            assignee=flags.get("assignee"),
            reason=flags.get("reason"),
        )
    except GleanError as e:
        ui.print_err(str(e))
        return
    print(ui.style(f"Reminder set for {pos[0]} in {days} day(s).", ui.C.GREEN))


# -------------------- messages --------------------

@register("messages.get")
def cmd_messages_get(s: Session, pos, flags):
    msg_id     = flags.get("id") or (pos[0] if pos else None)
    id_type    = flags.get("id-type") or flags.get("id_type") or "MESSAGE_ID"
    datasource = flags.get("datasource")
    if not msg_id or not datasource:
        ui.print_err("Usage: /messages.get --id <id> --datasource <name> [--id-type <type>] [--direction BEFORE|AFTER]")
        return
    try:
        resp = s.client.messages_get(
            msg_id=str(msg_id),
            id_type=str(id_type),
            datasource=str(datasource),
            direction=flags.get("direction"),
        )
    except GleanError as e:
        ui.print_err(str(e))
        return
    messages = resp.get("messages") or []
    if not messages:
        print(ui.style("(no messages found)", ui.C.GREY))
        return
    for m in messages:
        author = ui.style(m.get("author", ""), ui.C.CYAN, ui.C.BOLD)
        text   = m.get("text", "")
        print(f"  {author}  {text}")


# -------------------- activity --------------------

@register("activity.report")
def cmd_activity_report(s: Session, pos, flags):
    url    = flags.get("url") or (pos[0] if pos else None)
    action = (flags.get("action") or "VIEW").upper()
    if not url:
        ui.print_err("Usage: /activity.report --url <url> [--action VIEW|EDIT]")
        return
    try:
        resp = s.client.activity_report(str(url), action=action)
    except GleanError as e:
        ui.print_err(str(e))
        return
    processed = resp.get("processed", 1)
    print(ui.style(f"Reported {processed} activity event(s).", ui.C.GREEN))


# -------------------- insights --------------------

def _fmt_ts(ts: Optional[int]) -> str:
    if not ts:
        return "—"
    import datetime
    return datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")


def _render_insights(resp: Dict[str, Any]) -> None:
    overview = resp.get("overviewResponse")
    assistant = resp.get("assistantResponse")
    agents = resp.get("agentsResponse")

    if overview:
        print(ui.rule("Overview"))
        mau = overview.get("monthlyActiveUsers", "—")
        wau = overview.get("weeklyActiveUsers", "—")
        emp = overview.get("employeeCount", "—")
        sigs = overview.get("totalSignups", "—")
        sat  = overview.get("searchSessionSatisfaction")
        sat_s = f"{sat*100:.1f}%" if sat is not None else "—"
        rows = [
            ("Monthly active users", str(mau)),
            ("Weekly active users",  str(wau)),
            ("Employee count",       str(emp)),
            ("Total sign-ups",       str(sigs)),
            ("Search satisfaction",  sat_s),
            ("Last updated",         _fmt_ts(overview.get("lastUpdatedTs"))),
        ]
        print(ui.kv_table(rows))
        ds_counts = overview.get("searchDatasourceCounts") or {}
        if ds_counts:
            print()
            print("  " + ui.style("Search clicks by datasource", ui.C.CYAN, ui.C.BOLD))
            ds_rows = sorted(ds_counts.items(), key=lambda x: -x[1])
            print(ui.kv_table([(k, f"{v:,}") for k, v in ds_rows]))

    if assistant:
        print(ui.rule("Assistant"))
        rows = [
            ("Monthly active users", str(assistant.get("monthlyActiveUsers", "—"))),
            ("Weekly active users",  str(assistant.get("weeklyActiveUsers", "—"))),
            ("Last updated",         _fmt_ts(assistant.get("lastUpdatedTs"))),
        ]
        print(ui.kv_table(rows))

    if agents:
        print(ui.rule("Agents"))
        rows = [
            ("Monthly active users", str(agents.get("monthlyActiveUsers", "—"))),
            ("Weekly active users",  str(agents.get("weeklyActiveUsers", "—"))),
            ("Last updated",         _fmt_ts(agents.get("lastUpdatedTs"))),
        ]
        print(ui.kv_table(rows))

    if not overview and not assistant and not agents:
        print(ui.style("(no insights data returned)", ui.C.GREY))

    print(ui.rule())


def _export_insights_csv(resp: Dict[str, Any], path: str) -> None:
    """Write insights data to a CSV file with columns: section, metric, value."""
    rows: List[Tuple[str, str, str]] = []

    overview = resp.get("overviewResponse")
    if overview:
        sat = overview.get("searchSessionSatisfaction")
        rows += [
            ("overview", "monthly_active_users",  str(overview.get("monthlyActiveUsers", ""))),
            ("overview", "weekly_active_users",   str(overview.get("weeklyActiveUsers", ""))),
            ("overview", "employee_count",        str(overview.get("employeeCount", ""))),
            ("overview", "total_signups",         str(overview.get("totalSignups", ""))),
            ("overview", "search_satisfaction",   f"{sat:.4f}" if sat is not None else ""),
            ("overview", "last_updated",          _fmt_ts(overview.get("lastUpdatedTs"))),
        ]
        for ds, count in sorted((overview.get("searchDatasourceCounts") or {}).items()):
            rows.append(("datasource_clicks", ds, str(count)))

    assistant = resp.get("assistantResponse")
    if assistant:
        rows += [
            ("assistant", "monthly_active_users", str(assistant.get("monthlyActiveUsers", ""))),
            ("assistant", "weekly_active_users",  str(assistant.get("weeklyActiveUsers", ""))),
            ("assistant", "last_updated",         _fmt_ts(assistant.get("lastUpdatedTs"))),
        ]

    agents = resp.get("agentsResponse")
    if agents:
        rows += [
            ("agents", "monthly_active_users", str(agents.get("monthlyActiveUsers", ""))),
            ("agents", "weekly_active_users",  str(agents.get("weeklyActiveUsers", ""))),
            ("agents", "last_updated",         _fmt_ts(agents.get("lastUpdatedTs"))),
        ]

    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["section", "metric", "value"])
        writer.writerows(rows)


@register("insights")
def cmd_insights(s: Session, pos, flags):
    show_assistant = bool(flags.get("assistant"))
    show_agents    = bool(flags.get("agents"))
    show_all       = bool(flags.get("all"))
    no_per_user    = bool(flags.get("no-per-user") or flags.get("no_per_user"))
    export_path    = flags.get("export")
    # default: overview always on; --all enables assistant + agents too
    try:
        resp = s.client.insights(
            overview=True,
            assistant=show_assistant or show_all,
            agents=show_agents or show_all,
            disable_per_user=no_per_user,
        )
    except GleanError as e:
        ui.print_err(str(e))
        return
    _render_insights(resp)
    if export_path:
        try:
            _export_insights_csv(resp, export_path)
            ui.print_ok(f"Exported to {export_path}")
        except OSError as e:
            ui.print_err(f"Could not write CSV: {e}")



# -------------------- scaffold --------------------

@register("scaffold")
def cmd_scaffold(s: Session, pos, flags):
    valid = sorted(TEMPLATES)
    if not pos or pos[0] not in TEMPLATES:
        ui.print_err(f"Usage: /scaffold <template>  — templates: {', '.join(valid)}")
        return
    template = pos[0]

    output_dir = flags.get("output") or flags.get("o")
    if not output_dir:
        default = _scaffold_default_dir(template)
        try:
            output_dir = input(
                ui.style(f"Output directory [{default}]: ", ui.C.CYAN)
            ).strip() or default
        except (EOFError, KeyboardInterrupt):
            print()
            ui.print_info("Cancelled.")
            return

    from pathlib import Path
    dest = Path(output_dir).expanduser().resolve()
    if not dest.exists():
        try:
            confirm = input(
                ui.style(f"Directory '{dest}' does not exist. Create it? [Y/n]: ", ui.C.CYAN)
            ).strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            ui.print_info("Cancelled.")
            return
        if confirm not in ("", "y", "yes"):
            ui.print_info("Cancelled.")
            return

    try:
        out_path = write_scaffold(template, output_dir)
    except Exception as e:
        ui.print_err(f"Could not write scaffold: {e}")
        return

    ui.print_ok(f"Created {out_path}")
    ui.print_info(f"Run with:  python3 {out_path}")


# -------------------- dispatcher --------------------

def dispatch(session: Session, line: str) -> None:
    line = line.strip()
    if not line:
        return
    session.command_history.append(_sanitize_for_history(line))

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
