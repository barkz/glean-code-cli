"""Glean Code REPL entry point."""
from __future__ import annotations

import sys

from . import __version__, ui
from .commands import Session, dispatch
from .config import Config


def main() -> None:
    config = Config.load()
    session = Session(config)

    print(ui.render_banner(__version__, config.effective_mode))

    # Non-interactive mode: pipe a command in and it runs once
    if not sys.stdin.isatty():
        for line in sys.stdin:
            dispatch(session, line)
        return

    while session.running:
        try:
            line = input(ui.prompt_str(config.effective_mode))
        except (EOFError, KeyboardInterrupt):
            print()
            break
        try:
            dispatch(session, line)
        except Exception as e:  # defensive: never crash the REPL
            ui.print_err(f"Unhandled error: {e}")


if __name__ == "__main__":
    main()
