"""Token storage: save / load / clear, and "is this token expired?".

Tokens live in a single small JSON file under the same app dir the rest of the
CLI already uses (~/.gleancode). They are kept separate from config.json so that
config.json never contains a live secret.

v1 deliberately uses one readable file with 0600 permissions. If you later want
OS keychain storage, swap the body of save_tokens/load_tokens/clear_tokens and
nothing else has to change.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional

# Reuse the existing Glean Code app directory so users only have one place to
# look. config.json and auth.json sit side by side; only auth.json holds secrets.
AUTH_DIR = Path.home() / ".gleancode"
AUTH_PATH = AUTH_DIR / "auth.json"

# Treat a token as expired this many seconds early, so we refresh before a call
# rather than getting a surprise 401 mid-request.
_EXPIRY_SKEW_SECONDS = 60


@dataclass
class Tokens:
    access_token: str
    refresh_token: Optional[str] = None
    # Absolute epoch seconds at which the access token stops being valid.
    expires_at: Optional[float] = None
    token_type: str = "Bearer"
    scope: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


def tokens_from_response(payload: dict, prior_refresh_token: Optional[str] = None) -> Tokens:
    """Build a Tokens object from a raw OAuth token-endpoint JSON response.

    Refresh responses sometimes omit a new refresh_token; in that case we keep
    the one we already had (prior_refresh_token).
    """
    expires_in = payload.get("expires_in")
    expires_at = (time.time() + float(expires_in)) if expires_in is not None else None
    return Tokens(
        access_token=payload["access_token"],
        refresh_token=payload.get("refresh_token") or prior_refresh_token,
        expires_at=expires_at,
        token_type=payload.get("token_type", "Bearer"),
        scope=payload.get("scope"),
    )


def save_tokens(tokens: Tokens) -> None:
    """Write tokens atomically with owner-only (0600) permissions."""
    AUTH_DIR.mkdir(parents=True, exist_ok=True)
    tmp = AUTH_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(tokens.to_dict(), indent=2))
    try:
        os.chmod(tmp, 0o600)
    except Exception:
        pass
    # os.replace is atomic on POSIX + Windows: readers never see a half file.
    os.replace(tmp, AUTH_PATH)
    try:
        os.chmod(AUTH_PATH, 0o600)
    except Exception:
        pass


def load_tokens() -> Optional[Tokens]:
    """Return stored tokens, or None if the user has not logged in."""
    if not AUTH_PATH.exists():
        return None
    try:
        data = json.loads(AUTH_PATH.read_text())
        if not data.get("access_token"):
            return None
        allowed = {"access_token", "refresh_token", "expires_at", "token_type", "scope"}
        return Tokens(**{k: v for k, v in data.items() if k in allowed})
    except Exception:
        return None


def clear_tokens() -> None:
    """Delete the local token file (logout)."""
    try:
        AUTH_PATH.unlink()
    except FileNotFoundError:
        pass
    except Exception:
        pass


def is_expired(expires_at: Optional[float]) -> bool:
    """True if there is an expiry and we are within the safety skew of it.

    No expiry recorded -> treat as not expired (some tokens are long-lived).
    """
    if expires_at is None:
        return False
    return time.time() >= (float(expires_at) - _EXPIRY_SKEW_SECONDS)
