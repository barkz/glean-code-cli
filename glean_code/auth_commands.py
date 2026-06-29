"""`/auth` slash command: browser-based Glean SSO sign-in for the CLI.

Importing this module registers the `/auth` command on the existing handler
registry, so the only wiring needed elsewhere is a single import (see cli.py).

Subcommands:
    /auth login    start the browser OAuth (SSO) flow
    /auth status   show whether you're logged in, the instance, and expiry
    /auth logout   delete local OAuth tokens
A bare `/auth` is treated as `/auth status`.
"""
from __future__ import annotations

from . import ui
from .commands import register
from .auth import AuthManager, AuthError

try:
    # Make `/help auth` and tab-completion aware of the new command.
    from .help_docs import DOCS
    DOCS["auth"] = {
        "summary": "Sign in to Glean via your browser/SSO using OAuth (Authorization Code + PKCE).",
        "usage": "/auth <login|status|logout> [--instance <host>] [--client-id <id>] [--port <n>] [--no-browser]",
        "params": [
            ("login", "Open the browser and sign in through Glean -> your company SSO."),
            ("status", "Show authentication state, instance, and token expiry."),
            ("logout", "Delete the locally stored OAuth tokens."),
            ("--instance", "Glean backend host, e.g. acme-be.glean.com (stored in config)."),
            ("--client-id", "Static OAuth client id (optional if the tenant supports DCR)."),
            ("--port", "Fixed localhost callback port (for redirect-URI allowlisting)."),
            ("--no-browser", "Print the authorize URL instead of opening a browser."),
        ],
        "examples": [
            "/auth login --instance acme-be.glean.com",
            "/auth login --instance acme-be.glean.com --client-id glean-code-cli --port 33389",
            "/auth status",
            "/auth logout",
        ],
        "endpoint": "Glean OAuth Authorization Server (/.well-known/oauth-authorization-server)",
    }
except Exception:
    pass


def _apply_login_flags(s, flags) -> None:
    """Persist any connection settings passed on the /auth login line."""
    instance = flags.get("instance")
    client_id = flags.get("client-id") or flags.get("client_id")
    port = flags.get("port")
    changed = False
    if instance:
        raw = str(instance).strip().rstrip("/")
        if "://" in raw:
            raw = raw.split("://", 1)[1]
        raw = raw.split("/", 1)[0]
        s.config.instance = raw
        changed = True
    if client_id and client_id is not True:
        s.config.oauth_client_id = str(client_id)
        changed = True
    if port and port is not True:
        try:
            s.config.redirect_port = int(port)
            changed = True
        except (TypeError, ValueError):
            ui.print_err("--port must be an integer")
    if changed:
        s.config.save()


def _print_status(s) -> None:
    status = AuthManager(s.config).get_status()
    print(ui.rule("auth status"))
    if status.authenticated:
        rows = [
            ("state", ui.style("Authenticated", ui.C.GREEN)),
            ("instance", status.server_url or ui.style("(unset)", ui.C.GREY)),
            ("token expires", status.expires_at or ui.style("(no expiry recorded)", ui.C.GREY)),
        ]
        if status.scope:
            rows.append(("scope", status.scope))
    else:
        rows = [
            ("state", ui.style("Not logged in", ui.C.YELLOW)),
            ("instance", status.server_url or ui.style("(unset)", ui.C.GREY)),
            ("hint", "Run /auth login --instance <host>"),
        ]
    print(ui.kv_table(rows))
    print(ui.rule())


@register("auth")
def cmd_auth(s, pos, flags):
    sub = (pos[0].lower() if pos else "status")

    if sub == "status":
        _print_status(s)
        return

    if sub == "logout":
        AuthManager(s.config).logout()
        s.refresh_client()
        ui.print_ok("Logged out. Local OAuth tokens deleted.")
        return

    if sub == "login":
        _apply_login_flags(s, flags)
        if not s.config.instance:
            ui.print_err("No instance set. Run: /auth login --instance <host>")
            ui.print_info("Example: /auth login --instance acme-be.glean.com")
            return
        manager = AuthManager(s.config)
        nb = bool(flags.get("no-browser") or flags.get("no_browser"))

        def _print_authorize_url(u: str) -> None:
            ui.print_info("Open this URL in your browser to sign in:")
            print("  " + ui.style(u, ui.C.GREY, ui.C.UNDER))

        ui.print_info(
            "Starting Glean sign-in (no browser)…" if nb else "Opening browser for Glean sign-in…"
        )
        ui.print_info("Waiting for login to complete…")
        try:
            if nb:
                status = manager.login(
                    open_browser=False,
                    on_authorize_url=_print_authorize_url,
                )
            else:
                status = manager.login(open_browser=True)
                url = getattr(manager, "_last_authorize_url", None)
                if url:
                    ui.print_info("If the browser did not open, visit this URL:")
                    print("  " + ui.style(url, ui.C.GREY, ui.C.UNDER))
        except AuthError as e:
            ui.print_err(f"Login failed: {e}")
            return
        except Exception as e:  # defensive: keep the REPL alive
            ui.print_err(f"Login failed: {e}")
            return

        # Tokens are stored; rebuild the client so it picks up live mode.
        s.refresh_client()
        ui.print_ok(f"Logged in to {status.server_url}")
        if status.expires_at:
            ui.print_info(f"Token expires: {status.expires_at}")
        ui.print_info(f"Mode is now {s.config.effective_mode}.")
        return

    ui.print_err("Usage: /auth <login|status|logout>")
