"""Terminal UI helpers. ASCII art, colours, boxes and formatters.

Uses only the standard library. ANSI escape codes work in any modern terminal
including macOS Terminal, iTerm, Windows Terminal, VS Code and the Cowork
integrated terminal.
"""
from __future__ import annotations

import os
import shutil
import sys
from typing import Iterable, List

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


# -------------------- boxes and tables --------------------

def box(title: str, body: str, colour: str = C.BLUE) -> str:
    width = min(term_width() - 2, 100)
    inner = width - 2
    top = "╭" + "─" * inner + "╮"
    bot = "╰" + "─" * inner + "╯"
    title_line = f"│ {style(title, C.BOLD)}".ljust(inner + len(C.BOLD) + len(C.RESET) + 2) + "│"
    lines = [style(top, colour), style(title_line, colour)]
    lines.append(style("│" + " " * inner + "│", colour))
    for raw in body.splitlines() or [""]:
        # crude wrap
        while len(raw) > inner - 2:
            chunk, raw = raw[: inner - 2], raw[inner - 2:]
            lines.append(style("│ ", colour) + chunk.ljust(inner - 2) + style(" │", colour))
        lines.append(style("│ ", colour) + raw.ljust(inner - 2) + style(" │", colour))
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
