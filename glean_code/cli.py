"""Glean Code REPL entry point."""
from __future__ import annotations

import sys

from . import __version__, ui
from .commands import Session, dispatch
from .completion import setup_readline
from .config import Config
# Importing auth_commands registers the `/auth` command (browser/SSO login).
from . import auth_commands  # noqa: F401


def main() -> None:
    config = Config.load()
    session = Session(config)

    print(ui.render_getting_started(
        __version__,
        config.effective_mode,
        has_token=config.is_live_ready,
        instance=config.instance,
    ))

    # Non-interactive mode: pipe a command in and it runs once
    if not sys.stdin.isatty():
        for line in sys.stdin:
            dispatch(session, line)
        return

    setup_readline()

    # Terminal title tracks mode and instance, so several open windows stay
    # tellable apart. Only rewritten when the state actually changes.
    last_title = None
    try:
        while session.running:
            try:
                title = ui.title_text(
                    mode=config.effective_mode,
                    instance=config.instance,
                    has_token=config.is_live_ready,
                    style_name=config.window_title,
                )
                if title and title != last_title:
                    ui.set_title(title)
                    last_title = title

                bar = ui.status_bar(
                    mode=config.effective_mode,
                    instance=config.instance,
                    has_token=config.is_live_ready,
                    act_as=config.act_as,
                    chat_id=session.current_chat_id,
                )
                if bar:
                    print(bar)
                line = input(ui.prompt_str(config.effective_mode))
            except (EOFError, KeyboardInterrupt):
                print()
                break
            try:
                dispatch(session, line)
            except Exception as e:  # defensive: never crash the REPL
                ui.print_err(f"Unhandled error: {e}")
    finally:
        if last_title:
            ui.clear_title()


if __name__ == "__main__":
    main()
