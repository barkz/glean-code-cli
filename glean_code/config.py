"""Config management for Glean Code.

Stores credentials and preferences in ~/.gleancode/config.json.
"""
from __future__ import annotations

import json
import os
import re
import urllib.parse
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any, Dict, Optional

CONFIG_DIR = Path.home() / ".gleancode"
CONFIG_PATH = CONFIG_DIR / "config.json"

# Secure-token references. Stored verbatim in config; resolved to the value of
# the matching env var at request time. The token itself never lands in
# config.json or the command history.
SECURE_REFS: Dict[str, str] = {
    "token.secure.client":   "GLEAN_CLIENT_TOKEN",
    "token.secure.indexing": "GLEAN_INDEXING_TOKEN",
}

_INSTANCE_ID_SUFFIX = "-be.glean.com"


def normalize_instance_host(value: Optional[str]) -> Optional[str]:
    """Return a backend hostname from a hostname, URL, or Glean instance ID.

    Glean instance IDs such as ``acme`` map to ``acme-be.glean.com``. Full
    hostnames and URLs are preserved as hostnames, which keeps existing custom
    tenant and development configurations working.
    """
    if not value:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    try:
        parsed = urllib.parse.urlsplit(raw if "://" in raw else f"//{raw}")
    except ValueError:
        return None
    host = parsed.hostname
    if not host or any(char.isspace() for char in host):
        return None
    if "." not in host:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]*", host):
            return None
        suffix = ".glean.com" if host.endswith("-be") else _INSTANCE_ID_SUFFIX
        host = f"{host}{suffix}"
    return host


def is_secure_ref(value: Optional[str]) -> bool:
    return isinstance(value, str) and value in SECURE_REFS


def resolve_secure(value: Optional[str]) -> Optional[str]:
    """Return the env-resolved token if value is a secure ref, else value."""
    if not value:
        return value
    if value in SECURE_REFS:
        return os.environ.get(SECURE_REFS[value]) or None
    return value


@dataclass
class Config:
    instance: Optional[str] = None            # e.g. "acme-be.glean.com"
    api_token: Optional[str] = None           # Glean Client API token (literal or secure ref)
    indexing_token: Optional[str] = None      # Glean Indexing API token (literal or secure ref)
    act_as: Optional[str] = None              # Optional email to impersonate
    base_url: Optional[str] = None            # Overrides the computed base URL
    mode: str = "auto"                        # auto | live | mock
    theme: str = "glean"                      # glean | mono | neon
    default_page_size: int = 10
    mock_corpus_path: Optional[str] = None    # JSON file backing mock mode; falls back to the built-in corpus
    window_title: str = "full"                # full | plain (no hostname) | off
    history: list = field(default_factory=list)

    # ---- Interactive OAuth (SSO) settings ----
    # client_id is optional: if the tenant supports Dynamic Client Registration
    # it is filled in automatically on first `/auth login`. The tokens
    # themselves are NEVER stored here; they live in ~/.gleancode/auth.json.
    oauth_client_id: Optional[str] = None
    oauth_client_instance: Optional[str] = None  # instance bound to a dynamically registered client
    oauth_scopes: Optional[str] = None            # space-separated; falls back to a default set
    redirect_port: Optional[int] = None           # fixed localhost callback port (optional)
    oauth_authorize_url: Optional[str] = None      # override; else discovered from the tenant
    oauth_token_url: Optional[str] = None          # override; else discovered from the tenant
    oauth_registration_url: Optional[str] = None   # override; else discovered from the tenant

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def load(cls) -> "Config":
        if not CONFIG_PATH.exists():
            return cls()
        try:
            data = json.loads(CONFIG_PATH.read_text())
            return cls(**{k: v for k, v in data.items() if k in cls.__annotations__})
        except Exception:
            return cls()

    def save(self) -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(json.dumps(self.to_dict(), indent=2))
        try:
            os.chmod(CONFIG_PATH, 0o600)
        except Exception:
            pass

    @property
    def effective_base_url(self) -> Optional[str]:
        if self.base_url:
            return self.base_url.rstrip("/")
        if host := normalize_instance_host(self.instance):
            return f"https://{host}/rest/api/v1"
        return None

    @property
    def effective_indexing_base_url(self) -> Optional[str]:
        if host := normalize_instance_host(self.instance):
            return f"https://{host}/api/index/v1"
        return None

    @property
    def effective_metadata_base_url(self) -> Optional[str]:
        if host := normalize_instance_host(self.instance):
            return f"https://{host}/rest/api/index"
        return None

    @property
    def effective_api_token(self) -> Optional[str]:
        # Prefer interactive OAuth (SSO) tokens when the user has signed in via
        # `/auth login`. These live in auth.json and are refreshed on demand.
        # This single hook is why every existing command works against live
        # Glean after OAuth login with no other code changes.
        try:
            from .auth.manager import AuthManager
            token = AuthManager(self).current_access_token()
            if token:
                return token
        except Exception:
            # Never let an auth issue break basic config behaviour.
            pass
        return resolve_secure(self.api_token)

    @property
    def effective_indexing_token(self) -> Optional[str]:
        # Indexing API does not accept OAuth; it always uses a Glean-issued token.
        return resolve_secure(self.indexing_token)

    @property
    def is_live_ready(self) -> bool:
        return bool(self.effective_api_token and self.effective_base_url)

    @property
    def effective_mode(self) -> str:
        if self.mode == "live":
            return "live"
        if self.mode == "mock":
            return "mock"
        return "live" if self.is_live_ready else "mock"
