"""Terminal UI helpers. ASCII art, colours, boxes and formatters.

Uses only the standard library. ANSI escape codes work in any modern terminal
including macOS Terminal, iTerm, Windows Terminal, VS Code and the Cowork
integrated terminal.
"""
from __future__ import annotations

import os
import re
import shutil
import sys
from typing import Iterable, List, Optional

_ANSI_RE = re.compile(r"\033\[[0-9;]*m")


def _vis(s: str) -> int:
    """Visible length of s, ignoring ANSI escape sequences."""
    return len(_ANSI_RE.sub("", s))


def _ljust(s: str, width: int) -> str:
    """Pad s with spaces so its visible width equals width."""
    pad = width - _vis(s)
    return s + " " * max(0, pad)


def _split_at(s: str, n: int) -> tuple:
    """Split s at visible position n, returning (head, tail)."""
    vis, i = 0, 0
    while i < len(s):
        if s[i] == "\033":
            end = s.find("m", i)
            i = end + 1 if end != -1 else len(s)
        else:
            if vis == n:
                break
            vis += 1
            i += 1
    return s[:i], s[i:]

# -------------------- colours --------------------

class C:
    RESET = "\033[0m"
    BOLD  = "\033[1m"
    DIM   = "\033[2m"
    ITALIC = "\033[3m"
    UNDER = "\033[4m"

    # Glean brand-ish palette
    BLUE   = "\033[38;5;33m"   # primary
    CYAN   = "\033[38;5;45m"
    TEAL   = "\033[38;5;44m"
    PURPLE = "\033[38;5;99m"
    GREEN  = "\033[38;5;42m"
    YELLOW = "\033[38;5;220m"
    RED    = "\033[38;5;203m"
    GREY   = "\033[38;5;244m"
    WHITE  = "\033[38;5;255m"


def supports_colour() -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    return sys.stdout.isatty()


def style(text: str, *codes: str) -> str:
    if not supports_colour():
        return text
    return "".join(codes) + text + C.RESET


def hyperlink(url: str, text: str) -> str:
    """OSC 8 terminal hyperlink. Falls back to plain text in non-TTY."""
    if not supports_colour():
        return text
    return f"\033]8;;{url}\033\\{text}\033]8;;\033\\"


def term_width(default: int = 80) -> int:
    try:
        return shutil.get_terminal_size().columns
    except Exception:
        return default


# -------------------- ASCII logo --------------------

GLEAN_WORDMARK = r"""
   ██████╗ ██╗     ███████╗ █████╗ ███╗   ██╗     ██████╗ ██████╗ ██████╗ ███████╗
  ██╔════╝ ██║     ██╔════╝██╔══██╗████╗  ██║    ██╔════╝██╔═══██╗██╔══██╗██╔════╝
  ██║  ███╗██║     █████╗  ███████║██╔██╗ ██║    ██║     ██║   ██║██║  ██║█████╗
  ██║   ██║██║     ██╔══╝  ██╔══██║██║╚██╗██║    ██║     ██║   ██║██║  ██║██╔══╝
  ╚██████╔╝███████╗███████╗██║  ██║██║ ╚████║    ╚██████╗╚██████╔╝██████╔╝███████╗
   ╚═════╝ ╚══════╝╚══════╝╚═╝  ╚═╝╚═╝  ╚═══╝     ╚═════╝ ╚═════╝ ╚═════╝ ╚══════╝
"""


def render_banner(version: str, mode: str) -> str:
    mark = style(GLEAN_WORDMARK, C.CYAN, C.BOLD)
    tag  = style("  Your work knowledge, at the command line.", C.GREY, C.ITALIC)
    meta = style(f"  v{version}  ·  mode: {mode}", C.GREY)
    hint = style("  Type /help for commands  ·  /login to connect  ·  /exit to quit",
                 C.TEAL)
    return f"{mark}\n{tag}\n{meta}\n{hint}\n"


def render_getting_started(version: str, mode: str,
                           has_token: bool, instance: Optional[str] = None) -> str:
    """Welcome panel inspired by Notion's `ntn` CLI splash.

    Logo, version line, two-column 'Get started' command table, and a footer
    pointing at the MCP server install. Shown on every REPL launch.
    """
    mark = style(GLEAN_WORDMARK, C.CYAN, C.BOLD)

    if has_token and instance:
        meta_text = f"  Glean Code v{version}  ·  mode: {mode}  ·  {instance}"
    elif has_token:
        meta_text = f"  Glean Code v{version}  ·  mode: {mode}  ·  token set"
    else:
        meta_text = f"  Glean Code v{version}  ·  mode: {mode}  ·  no token (mock data)"
    meta = style(meta_text, C.GREY)

    rows = [
        ("/login --instance <host> --token <bearer>", "Connect to your Glean instance"),
        ("/search \"...\"",                            "Run a Glean search"),
        ("/chat \"...\"",                              "Ask Glean a question"),
        ("/datasources.list --with-status",            "List datasources with indexing health"),
        ("/index.document --path README.md ...",       "Index a local file or folder"),
        ("/help",                                      "See all available commands"),
    ]
    key_w = max(len(k) for k, _ in rows)

    header = "  " + style("Get started:", C.WHITE, C.BOLD)
    cmd_lines = "\n".join(
        "    " + style(k.ljust(key_w), C.CYAN, C.BOLD)
        + "   " + style(v, C.GREY)
        for k, v in rows
    )

    agents_header = "  " + style("Add Glean to your AI agents:", C.WHITE, C.BOLD)
    agents_body = (
        "    " + style(
            "Wire up the MCP server (glean_mcp.py) for Claude Code, Claude Desktop, or Cursor.",
            C.GREY,
        )
        + "\n    " + style("See docs/COMMANDS.md or run /help mcp.", C.GREY)
    )

    quit_hint = "  " + style("Type /exit to quit.", C.TEAL)

    return (
        f"{mark}\n"
        f"{meta}\n\n"
        f"{header}\n\n"
        f"{cmd_lines}\n\n"
        f"{agents_header}\n\n"
        f"{agents_body}\n\n"
        f"{quit_hint}\n"
    )


# -------------------- boxes and tables --------------------

def box(title: str, body: str, colour: str = C.BLUE) -> str:
    width = min(term_width() - 2, 100)
    inner = width - 2
    top = "╭" + "─" * inner + "╮"
    bot = "╰" + "─" * inner + "╯"
    title_line = _ljust("│ " + style(title, C.BOLD), inner + 1) + "│"
    lines = [style(top, colour), style(title_line, colour)]
    lines.append(style("│" + " " * inner + "│", colour))
    for raw in body.splitlines() or [""]:
        while _vis(raw) > inner - 2:
            chunk, raw = _split_at(raw, inner - 2)
            lines.append(style("│ ", colour) + _ljust(chunk, inner - 2) + style(" │", colour))
        lines.append(style("│ ", colour) + _ljust(raw, inner - 2) + style(" │", colour))
    lines.append(style("│" + " " * inner + "│", colour))
    lines.append(style(bot, colour))
    return "\n".join(lines)


def rule(label: str = "", colour: str = C.GREY) -> str:
    w = term_width()
    if label:
        bar = "─" * max(0, w - len(label) - 4)
        return style(f"── {label} {bar}", colour)
    return style("─" * w, colour)


def kv_table(rows: Iterable[tuple], colour: str = C.CYAN) -> str:
    rows = list(rows)
    if not rows:
        return ""
    key_w = max(len(str(k)) for k, _ in rows)
    out: List[str] = []
    for k, v in rows:
        out.append(f"  {style(str(k).ljust(key_w), colour, C.BOLD)}  {v}")
    return "\n".join(out)


def bullet_list(items: Iterable[str], marker: str = "▸", colour: str = C.BLUE) -> str:
    return "\n".join(f"  {style(marker, colour)} {it}" for it in items)


def print_err(msg: str) -> None:
    print(style("✖ " + msg, C.RED, C.BOLD))


def print_info(msg: str) -> None:
    print(style("ℹ " + msg, C.CYAN))


def print_ok(msg: str) -> None:
    print(style("✔ " + msg, C.GREEN))


def prompt_str(mode: str) -> str:
    dot = style("●", C.GREEN if mode == "live" else C.YELLOW)
    label = style("glean", C.BLUE, C.BOLD) + style("-code", C.CYAN, C.BOLD)
    arrow = style("›", C.GREY)
    return f"{dot} {label} {arrow} "


# -------------------- status bar --------------------

def status_bar(
    mode: str,
    instance: Optional[str] = None,
    has_token: bool = False,
    act_as: Optional[str] = None,
    chat_id: Optional[str] = None,
) -> str:
    """Full-width coloured status bar. Returns '' when colour is unsupported."""
    if not supports_colour():
        return ""

    # Each entry: (bg_256, fg_256, visible_text)
    segs: List[tuple] = []

    if mode == "live":
        segs.append(("28",  "255", " ● LIVE "))
    elif mode == "mock":
        segs.append(("136", "0",   " ● MOCK "))
    else:
        segs.append(("241", "255", " ● AUTO "))

    if instance:
        host = instance
        if "://" in host:
            host = host.split("://", 1)[1].split("/")[0]
        segs.append(("24", "255", f"  {host} "))
    else:
        segs.append(("238", "244", "  no instance "))

    if has_token:
        label = f"  {act_as} " if act_as else "  token ✓ "
        segs.append(("23", "255", label))
    else:
        segs.append(("52", "203", "  no token "))

    if chat_id:
        short = (chat_id[:12] + "…") if len(chat_id) > 13 else chat_id
        segs.append(("54", "255", f"  ◉ {short} "))

    parts: List[str] = []
    for i, (bg, fg, text) in enumerate(segs):
        parts.append(f"\033[48;5;{bg}m\033[38;5;{fg}m{text}")
        if i + 1 < len(segs):
            next_bg = segs[i + 1][0]
            # Arrow separator: current bg behind, next bg as fg colour
            parts.append(f"\033[48;5;{bg}m\033[38;5;{next_bg}m▶")

    visible = sum(len(t) for _, _, t in segs) + (len(segs) - 1)
    fill = max(0, term_width() - visible)
    parts.append(f"\033[48;5;235m{' ' * fill}\033[0m")

    return "".join(parts)
