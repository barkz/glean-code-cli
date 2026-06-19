"""PKCE + state generation (pure utility, no network).

PKCE (Proof Key for Code Exchange) lets a *public* client like a CLI run OAuth
safely without embedding a client secret in source or in the binary. Instead of
a secret, the client invents a random `code_verifier`, sends only its SHA-256
hash (`code_challenge`) when starting the flow, and later proves it owns the
verifier when exchanging the auth code for tokens. An attacker who intercepts
the auth code cannot redeem it without the verifier.

`state` is a separate random value. It is echoed back on the OAuth redirect and
checked on return; this protects against CSRF / cross-session callback mix-ups.
"""
from __future__ import annotations

import base64
import hashlib
import secrets
from dataclasses import dataclass


def _b64url_no_pad(raw: bytes) -> str:
    """Base64url-encode bytes and strip the `=` padding (per RFC 7636)."""
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


@dataclass
class Pkce:
    code_verifier: str
    code_challenge: str
    method: str = "S256"


def create_pkce_pair() -> Pkce:
    """Create a fresh PKCE verifier/challenge pair.

    The verifier is 43-128 chars of unreserved characters; `token_urlsafe(64)`
    yields ~86 url-safe chars, comfortably inside that range.
    """
    code_verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    code_challenge = _b64url_no_pad(digest)
    return Pkce(code_verifier=code_verifier, code_challenge=code_challenge, method="S256")


def generate_state() -> str:
    """Random, unguessable value used to tie the callback to this login attempt."""
    return secrets.token_urlsafe(32)
