"""AuthManager: the one object that owns the full auth story.

The rest of the CLI only ever needs four things:

    manager.login()              run the interactive browser sign-in
    manager.logout()             delete local tokens
    manager.get_access_token()   a valid bearer token (refreshes if needed)
    manager.get_status()         are we logged in, where, until when

`config.effective_api_token` calls `current_access_token()` so every existing
command transparently uses the OAuth token once the user has run `/auth login`.
"""
from __future__ import annotations

import time
import webbrowser
from dataclasses import dataclass
from typing import Callable, Optional

from . import oauth
from . import pkce as _pkce
from . import token_store
from .callback_server import start_callback_server

# Default scopes for Client API use. `AGENT` is omitted: many OAuth clients are
# not allowed to request it; add it via `oauth_scopes` in config if yours is.
# offline_access asks for a refresh token so the CLI can stay signed in.
DEFAULT_SCOPES = "SEARCH CHAT DOCUMENTS TOOLS ENTITIES offline_access"

# Module-level backoff so a repeatedly-failing refresh (e.g. network down) is not
# retried on every prompt render. We only re-attempt after this many seconds.
_REFRESH_BACKOFF_SECONDS = 30
_last_failed_refresh_at: float = 0.0


class AuthError(Exception):
    pass


@dataclass
class AuthStatus:
    authenticated: bool
    server_url: Optional[str] = None
    expires_at: Optional[str] = None
    scope: Optional[str] = None


def _server_root_from_instance(instance: Optional[str]) -> Optional[str]:
    """Turn a stored instance host into a scheme+host root for OAuth discovery.

    Mirrors Config.effective_base_url's host handling, but returns just the
    root (no /rest/api/v1), since OAuth metadata lives at the host root.
    """
    if not instance:
        return None
    host = instance.strip().rstrip("/")
    if "://" in host:
        host = host.split("://", 1)[1]
    host = host.split("/", 1)[0]
    if not host:
        return None
    return f"https://{host}"


def _iso(ts: Optional[float]) -> Optional[str]:
    if ts is None:
        return None
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts))


class AuthManager:
    """Orchestrates the OAuth flow. Holds no secrets itself."""

    def __init__(self, config) -> None:
        # `config` is the CLI's Config dataclass instance. We read a few fields
        # off it and may write oauth_client_id back after dynamic registration.
        self.config = config

    # ---------------- public API ----------------

    def login(
        self,
        open_browser: bool = True,
        on_authorize_url: Optional[Callable[[str], None]] = None,
    ) -> AuthStatus:
        """Run the interactive Authorization Code + PKCE login.

        If ``on_authorize_url`` is set, it is called with the authorize URL after
        it is built and before waiting for the callback (needed for ``--no-browser``).
        """
        server_root = _server_root_from_instance(self.config.instance)
        if not server_root:
            raise AuthError(
                "No instance configured. Run: /auth login --instance <host>"
            )

        scopes = getattr(self.config, "oauth_scopes", None) or DEFAULT_SCOPES
        endpoints = self._resolve_endpoints(server_root)

        # 1. Crypto material (pure, no network).
        pkce = _pkce.create_pkce_pair()
        state = _pkce.generate_state()

        # 2. Start the localhost callback server BEFORE opening the browser, so
        #    we never miss the redirect.
        redirect_port = getattr(self.config, "redirect_port", None)
        server = start_callback_server(redirect_port)
        try:
            redirect_uri = server.redirect_uri

            # 3. Resolve a client_id: configured static client, or register one
            #    dynamically if the tenant supports DCR.
            client_id = self._resolve_client_id(endpoints, redirect_uri, scopes)

            authorize_url = oauth.build_authorize_url(
                authorization_endpoint=endpoints.authorization_endpoint,
                client_id=client_id,
                redirect_uri=redirect_uri,
                code_challenge=pkce.code_challenge,
                state=state,
                scopes=scopes,
            )

            self._last_authorize_url = authorize_url  # for the command to print
            if open_browser:
                try:
                    webbrowser.open(authorize_url, new=2)
                except Exception:
                    pass  # Fall through; caller prints the URL as a fallback.
            if on_authorize_url:
                on_authorize_url(authorize_url)

            # 4. Wait for the browser to come back to /callback.
            result = server.wait_for_code(timeout=300)
        finally:
            server.close()

        if result.error == "timeout":
            raise AuthError("browser callback was not received")
        if result.error:
            raise AuthError(f"authorization failed: {result.error}")
        if not result.code:
            raise AuthError("browser callback did not include an authorization code")
        # 5. Verify state to defend against CSRF / mixed-up callbacks.
        if result.state != state:
            raise AuthError("OAuth state mismatch")

        # 6. Exchange the code for tokens.
        try:
            payload = oauth.exchange_code_for_tokens(
                token_endpoint=endpoints.token_endpoint,
                client_id=client_id,
                redirect_uri=redirect_uri,
                code=result.code,
                code_verifier=pkce.code_verifier,
            )
        except oauth.OAuthError:
            raise AuthError("token exchange failed")

        tokens = token_store.tokens_from_response(payload)
        token_store.save_tokens(tokens)
        return self.get_status()

    def logout(self) -> None:
        token_store.clear_tokens()

    def get_access_token(self) -> str:
        """Return a valid access token, refreshing if needed. Raises if not logged in."""
        token = self.current_access_token(allow_refresh=True)
        if not token:
            if token_store.load_tokens() is None:
                raise AuthError("Not logged in. Run: /auth login")
            raise AuthError("Session expired and refresh failed. Run: /auth login")
        return token

    def current_access_token(self, allow_refresh: bool = True) -> Optional[str]:
        """Best-effort access token for header building. Returns None if unavailable.

        Cheap when the token is valid (a file read + an expiry compare, no
        network). Refreshes at most once per expiry window, with a short backoff
        if a refresh keeps failing, so this is safe to call on every prompt.
        """
        tokens = token_store.load_tokens()
        if tokens is None:
            return None
        if not token_store.is_expired(tokens.expires_at):
            return tokens.access_token
        if not allow_refresh or not tokens.refresh_token:
            return None

        global _last_failed_refresh_at
        if (time.time() - _last_failed_refresh_at) < _REFRESH_BACKOFF_SECONDS:
            return None  # backing off after a recent failure

        server_root = _server_root_from_instance(self.config.instance)
        if not server_root:
            return None
        try:
            endpoints = self._resolve_endpoints(server_root)
            client_id = getattr(self.config, "oauth_client_id", None)
            if not client_id:
                return None
            scopes = getattr(self.config, "oauth_scopes", None) or DEFAULT_SCOPES
            payload = oauth.refresh_tokens(
                token_endpoint=endpoints.token_endpoint,
                client_id=client_id,
                refresh_token=tokens.refresh_token,
                scopes=scopes,
            )
            new_tokens = token_store.tokens_from_response(
                payload, prior_refresh_token=tokens.refresh_token
            )
            token_store.save_tokens(new_tokens)
            return new_tokens.access_token
        except Exception:
            _last_failed_refresh_at = time.time()
            return None

    def get_status(self) -> AuthStatus:
        tokens = token_store.load_tokens()
        if tokens is None:
            return AuthStatus(authenticated=False, server_url=_server_root_from_instance(self.config.instance))
        return AuthStatus(
            authenticated=True,
            server_url=_server_root_from_instance(self.config.instance),
            expires_at=_iso(tokens.expires_at),
            scope=tokens.scope,
        )

    # ---------------- internals ----------------

    def _resolve_endpoints(self, server_root: str) -> oauth.Endpoints:
        """Honour explicit overrides in config, else discover from the tenant."""
        a = getattr(self.config, "oauth_authorize_url", None)
        t = getattr(self.config, "oauth_token_url", None)
        r = getattr(self.config, "oauth_registration_url", None)
        if a and t:
            return oauth.Endpoints(
                authorization_endpoint=a, token_endpoint=t, registration_endpoint=r
            )
        discovered = oauth.discover_endpoints(server_root)
        # Per-field overrides still win if only some are set.
        return oauth.Endpoints(
            authorization_endpoint=a or discovered.authorization_endpoint,
            token_endpoint=t or discovered.token_endpoint,
            registration_endpoint=r or discovered.registration_endpoint,
        )

    def _resolve_client_id(self, endpoints: oauth.Endpoints, redirect_uri: str, scopes: str) -> str:
        client_id = getattr(self.config, "oauth_client_id", None)
        if client_id:
            return client_id
        if not endpoints.registration_endpoint:
            raise AuthError(
                "No oauth_client_id configured and the tenant did not advertise a "
                "registration endpoint. Set one with: "
                "/config set oauth_client_id <client id>"
            )
        client_id = oauth.register_dynamic_client(
            endpoints.registration_endpoint, redirect_uri, scopes
        )
        # Persist the dynamically registered client so future logins reuse it.
        try:
            self.config.oauth_client_id = client_id
            self.config.save()
        except Exception:
            pass
        return client_id
