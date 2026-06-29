"""Glean Code interactive auth (SSO via Glean OAuth).

This sub-package gives the CLI the *same sign-in experience* as the Glean web
app, without trying to reuse browser cookies. It implements one interactive
flow only:

    OAuth 2.1 Authorization Code + PKCE against Glean's OAuth Authorization
    Server. Glean delegates the actual user authentication to your company's
    existing SSO IdP (Okta, Entra ID, Google, ...), then issues Glean tokens
    back to this CLI.

One file = one job:

    pkce.py             create the PKCE verifier/challenge and the `state` value
    callback_server.py  run a tiny localhost server to catch the OAuth redirect
    token_store.py      save / load / clear tokens and answer "is it expired?"
    oauth.py            the only file that talks to the OAuth/token endpoints
    manager.py          AuthManager: orchestrates login / logout / get token

The rest of the CLI never has to know any of this. It just reads
`config.effective_api_token`, which transparently returns a valid OAuth access
token (refreshing it when needed) once the user has run `/auth login`.
"""
from __future__ import annotations

from .manager import AuthManager, AuthStatus, AuthError

__all__ = ["AuthManager", "AuthStatus", "AuthError"]
