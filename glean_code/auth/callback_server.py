"""Temporary localhost server that catches the OAuth redirect.

Responsibility (and *only* this): start a tiny HTTP server bound to 127.0.0.1,
wait for the browser to hit `/callback?code=...&state=...`, hand back the code
and state, then stop. No token exchange happens here.

Why localhost-only? The OAuth redirect carries the authorization code. Binding
to 127.0.0.1 (never 0.0.0.0) means only processes on this machine can deliver
that code to us - nothing on the local network can reach the callback port.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Optional
from urllib.parse import urlparse, parse_qs


_LOOPBACK_HOST = "127.0.0.1"

_SUCCESS_HTML = (
    "<!doctype html><html><head><meta charset='utf-8'>"
    "<title>Glean Code</title></head>"
    "<body style='font-family:system-ui;margin:48px;color:#1a1a1a'>"
    "<h2>You're signed in to Glean Code.</h2>"
    "<p>You can close this tab and return to your terminal.</p>"
    "</body></html>"
)

_ERROR_HTML = (
    "<!doctype html><html><head><meta charset='utf-8'>"
    "<title>Glean Code</title></head>"
    "<body style='font-family:system-ui;margin:48px;color:#1a1a1a'>"
    "<h2>Sign-in failed.</h2>"
    "<p>Return to your terminal for details.</p>"
    "</body></html>"
)


@dataclass
class CallbackResult:
    code: Optional[str] = None
    state: Optional[str] = None
    error: Optional[str] = None


class _Holder:
    """Mutable box the request handler writes the result into."""

    def __init__(self) -> None:
        self.result: Optional[CallbackResult] = None


def _make_handler(holder: _Holder):
    class _Handler(BaseHTTPRequestHandler):
        # Silence default stderr access logging - we never want token-bearing
        # callback URLs echoed to the console.
        def log_message(self, *args, **kwargs):  # noqa: D401
            return

        def do_GET(self):  # noqa: N802
            parsed = urlparse(self.path)
            if not parsed.path.startswith("/callback"):
                # Ignore stray requests (e.g. /favicon.ico) without finishing.
                self.send_response(404)
                self.end_headers()
                return
            qs = parse_qs(parsed.query)
            error = (qs.get("error") or [None])[0]
            code = (qs.get("code") or [None])[0]
            state = (qs.get("state") or [None])[0]
            holder.result = CallbackResult(code=code, state=state, error=error)
            body = (_ERROR_HTML if error or not code else _SUCCESS_HTML).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return _Handler


class CallbackServer:
    """A one-shot localhost server for the OAuth redirect."""

    def __init__(self, httpd: HTTPServer, holder: _Holder) -> None:
        self._httpd = httpd
        self._holder = holder
        host, port = httpd.server_address[0], httpd.server_address[1]
        self.port = port
        self.redirect_uri = f"http://{host}:{port}/callback"

    def wait_for_code(self, timeout: float = 300.0) -> CallbackResult:
        """Block until the browser hits /callback, or until `timeout` seconds."""
        self._httpd.timeout = 1.0
        deadline = time.time() + timeout
        while self._holder.result is None and time.time() < deadline:
            # handle_request() returns after a single request or after the
            # 1s timeout above, so the loop keeps polling without busy-waiting.
            self._httpd.handle_request()
        if self._holder.result is None:
            return CallbackResult(error="timeout")
        return self._holder.result

    def close(self) -> None:
        try:
            self._httpd.server_close()
        except Exception:
            pass


def start_callback_server(preferred_port: Optional[int] = None) -> CallbackServer:
    """Start (and return) a localhost callback server.

    Pass `preferred_port` to bind a stable port (useful when the Glean admin
    allowlists an exact redirect URI). Omit it to let the OS choose a free port.
    """
    holder = _Holder()
    handler = _make_handler(holder)
    port = int(preferred_port) if preferred_port else 0
    httpd = HTTPServer((_LOOPBACK_HOST, port), handler)
    return CallbackServer(httpd, holder)
