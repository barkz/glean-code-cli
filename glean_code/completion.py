"""Tab completion for the Glean Code REPL.

Wires into Python's readline (or libedit on macOS) to provide:
  - Slash command name completion
  - --flag completion per command
  - Enum-value completion for known flags and positional slots
"""
from __future__ import annotations

import shlex
from typing import Dict, List, Optional

from .help_docs import DOCS

try:
    import readline
    _HAS_READLINE = True
except ImportError:
    _HAS_READLINE = False

_FLAG_VALUES: Dict[str, List[str]] = {
    "mode":   ["live", "mock", "auto"],
    "kind":   ["PEOPLE", "TEAM", "GROUP"],
}

_CONFIG_KEYS = [
    "instance", "api_token", "act_as", "base_url",
    "mode", "theme", "default_page_size",
]

_CONFIG_SUBCMDS = ["get", "set", "list"]


class _Completer:
    def __init__(self) -> None:
        self._matches: List[str] = []

    def __call__(self, text: str, state: int) -> Optional[str]:
        if state == 0:
            self._matches = self._complete(text)
        try:
            return self._matches[state]
        except IndexError:
            return None

    def _complete(self, text: str) -> List[str]:
        if not _HAS_READLINE:
            return []

        buf = readline.get_line_buffer()
        lbuf = buf[: readline.get_endidx()]

        try:
            tokens = shlex.split(lbuf)
        except ValueError:
            return []

        ends_with_space = lbuf.endswith(" ") and bool(lbuf)

        # ── command completion ───────────────────────────────────────────
        if not tokens or (len(tokens) == 1 and not ends_with_space):
            word = tokens[0] if tokens else ""
            prefix = word.lstrip("/")
            return sorted("/" + cmd for cmd in DOCS if cmd.startswith(prefix))

        cmd = tokens[0].lstrip("/")
        doc = DOCS.get(cmd)

        # ── --flag name completion ───────────────────────────────────────
        if text.startswith("-"):
            if not doc:
                return []
            flags = [p[0] for p in doc.get("params", []) if p[0].startswith("--")]
            return [f for f in flags if f.startswith(text)]

        # ── figure out which --flag precedes the current position ────────
        search_in = tokens[1:] if ends_with_space else tokens[1:-1]
        last_flag: Optional[str] = None
        for t in reversed(search_in):
            if t.startswith("--"):
                last_flag = t[2:]
                break

        # ── enum value for a known flag ──────────────────────────────────
        if last_flag in _FLAG_VALUES:
            return [v for v in _FLAG_VALUES[last_flag] if v.startswith(text)]

        # ── /mode <value> ────────────────────────────────────────────────
        if cmd == "mode" and (ends_with_space or len(tokens) == 2):
            return [v for v in _FLAG_VALUES["mode"] if v.startswith(text)]

        # ── /config subcommands, key names, and mode values ──────────────
        if cmd == "config":
            # /config <tab>  or  /config s<tab>
            if len(tokens) == 1 or (len(tokens) == 2 and not ends_with_space):
                partial = "" if ends_with_space else tokens[-1]
                return [s for s in _CONFIG_SUBCMDS if s.startswith(partial)]
            sub = tokens[1] if len(tokens) > 1 else ""
            if sub in ("get", "set"):
                # /config set <key-tab>
                if len(tokens) == 2 or (len(tokens) == 3 and not ends_with_space):
                    partial = "" if ends_with_space else tokens[-1]
                    return [k for k in _CONFIG_KEYS if k.startswith(partial)]
                # /config set mode <value-tab>
                if sub == "set" and len(tokens) >= 3 and tokens[2] == "mode":
                    if len(tokens) == 3 or (len(tokens) == 4 and not ends_with_space):
                        partial = "" if ends_with_space else tokens[-1]
                        return [v for v in _FLAG_VALUES["mode"] if v.startswith(partial)]

        # ── /help <command-tab> ──────────────────────────────────────────
        if cmd == "help":
            if ends_with_space or len(tokens) == 2:
                partial = "" if ends_with_space else tokens[-1]
                return sorted(c for c in DOCS if c.startswith(partial))

        # ── /scaffold <template-tab> ─────────────────────────────────────
        if cmd == "scaffold":
            if ends_with_space or len(tokens) == 2:
                partial = "" if ends_with_space else tokens[-1]
                return [t for t in ("chat", "search", "agent") if t.startswith(partial)]

        # ── fallback: show available flags when cursor is at a blank slot ─
        if text == "" and doc:
            return [p[0] for p in doc.get("params", []) if p[0].startswith("--")]

        return []


def setup_readline() -> None:
    if not _HAS_READLINE:
        return
    readline.set_completer(_Completer())
    readline.set_completer_delims(" \t")
    # libedit (macOS default) uses a different binding syntax
    if "libedit" in getattr(readline, "__doc__", ""):
        readline.parse_and_bind("bind ^I rl_complete")
    else:
        readline.parse_and_bind("tab: complete")
