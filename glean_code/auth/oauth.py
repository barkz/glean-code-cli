"""The only file that talks to Glean's OAuth / token endpoints.

It builds the browser authorize URL, exchanges the auth code for tokens, and
refreshes tokens. It also discovers the per-tenant endpoint URLs from Glean's
OAuth Authorization Server metadata (RFC 8414), falling back to the standard
default paths when discovery is unavailable.

Glean acts as the OAuth 2.1 Authorization Server and delegates the actual user
sign-in to your company SSO IdP (Okta, Entra ID, Google, ...). We therefore get
the real SSO experience while receiving Glean-issued tokens for API calls.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Dict, Optional

_USER_AGENT = "glean-code/0.1 (auth)"
_TIMEOUT = 30


class OAuthError(Exception):
    pass


@dataclass
class Endpoints:
    authorization_endpoint: str
    token_endpoint: str
    registration_endpoint: Optional[str] = None


def _http_get_json(url: str) -> Optional[Dict]:
    req = urllib.request.Request(
        url, headers={"Accept": "application/json", "User-Agent": _USER_AGENT}
    )
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else None
    except (urllib.error.HTTPError, urllib.error.URLError, ValueError):
        return None


def _http_post_form(url: str, form: Dict[str, str]) -> Dict:
    data = urllib.parse.urlencode(form).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "User-Agent": _USER_AGENT,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")
        raise OAuthError(f"HTTP {e.code} from token endpoint: {detail}") from None
    except urllib.error.URLError as e:
        raise OAuthError(f"Network error reaching {url}: {e.reason}") from None


def _http_post_json(url: str, payload: Dict) -> Dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": _USER_AGENT,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")
        raise OAuthError(f"HTTP {e.code} from {url}: {detail}") from None
    except urllib.error.URLError as e:
        raise OAuthError(f"Network error reaching {url}: {e.reason}") from None


def discover_endpoints(server_root: str) -> Endpoints:
    """Discover authorize/token (and registration) endpoints for the tenant.

    server_root is the scheme+host of the Glean backend, e.g.
    "https://acme-be.glean.com". We try the RFC 8414 metadata document first,
    then OpenID config, then fall back to the conventional default paths.
    """
    root = server_root.rstrip("/")
    for path in ("/.well-known/oauth-authorization-server",
                 "/.well-known/openid-configuration"):
        meta = _http_get_json(root + path)
        if meta and meta.get("authorization_endpoint") and meta.get("token_endpoint"):
            return Endpoints(
                authorization_endpoint=meta["authorization_endpoint"],
                token_endpoint=meta["token_endpoint"],
                registration_endpoint=meta.get("registration_endpoint"),
            )
    # Fallback to the standard default endpoint paths.
    return Endpoints(
        authorization_endpoint=f"{root}/authorize",
        token_endpoint=f"{root}/token",
        registration_endpoint=f"{root}/register",
    )


def register_dynamic_client(
    registration_endpoint: str, redirect_uri: str, scopes: str
) -> str:
    """Register a public OAuth client via Dynamic Client Registration (RFC 7591).

    Used only when no static client_id is configured. Returns the new client_id.
    Glean supports DCR for MCP/OAuth clients; the client is public (no secret)
    and uses PKCE, so token_endpoint_auth_method is "none".
    """
    payload = {
        "client_name": "Glean Code CLI",
        "redirect_uris": [redirect_uri],
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "none",
        "scope": scopes,
    }
    resp = _http_post_json(registration_endpoint, payload)
    client_id = resp.get("client_id")
    if not client_id:
        raise OAuthError("Dynamic client registration did not return a client_id.")
    return client_id


def build_authorize_url(
    authorization_endpoint: str,
    client_id: str,
    redirect_uri: str,
    code_challenge: str,
    state: str,
    scopes: str,
) -> str:
    """Assemble the browser URL that kicks off the Authorization Code + PKCE flow."""
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": scopes,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    return authorization_endpoint + "?" + urllib.parse.urlencode(params)


def exchange_code_for_tokens(
    token_endpoint: str,
    client_id: str,
    redirect_uri: str,
    code: str,
    code_verifier: str,
) -> Dict:
    """Trade the one-time auth code (+ PKCE verifier) for access/refresh tokens."""
    form = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": client_id,
        "code_verifier": code_verifier,
    }
    return _http_post_form(token_endpoint, form)


def refresh_tokens(
    token_endpoint: str,
    client_id: str,
    refresh_token: str,
    scopes: Optional[str] = None,
) -> Dict:
    """Use a refresh token to get a fresh access token without user interaction."""
    form = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": client_id,
    }
    if scopes:
        form["scope"] = scopes
    return _http_post_form(token_endpoint, form)
