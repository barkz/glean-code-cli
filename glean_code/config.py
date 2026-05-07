"""Config management for Glean Code.

Stores credentials and preferences in ~/.gleancode/config.json.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any, Dict, Optional

CONFIG_DIR = Path.home() / ".gleancode"
CONFIG_PATH = CONFIG_DIR / "config.json"


@dataclass
class Config:
    instance: Optional[str] = None            # e.g. "acme-be.glean.com"
    api_token: Optional[str] = None           # Glean Client API token
    indexing_token: Optional[str] = None      # Glean Indexing API token
    act_as: Optional[str] = None              # Optional email to impersonate
    base_url: Optional[str] = None            # Overrides the computed base URL
    mode: str = "auto"                        # auto | live | mock
    theme: str = "glean"                      # glean | mono | neon
    default_page_size: int = 10
    history: list = field(default_factory=list)

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
        if self.instance:
            # instance is now stored as a full host, never a bare subdomain
            host = self.instance.strip().rstrip("/")
            if "://" in host:
                host = host.split("://", 1)[1]
            host = host.split("/", 1)[0]
            return f"https://{host}/rest/api/v1"
        return None

    @property
    def effective_indexing_base_url(self) -> Optional[str]:
        if self.instance:
            host = self.instance.strip().rstrip("/")
            if "://" in host:
                host = host.split("://", 1)[1]
            host = host.split("/", 1)[0]
            return f"https://{host}/api/index/v1"
        return None

    @property
    def is_live_ready(self) -> bool:
        return bool(self.api_token and self.effective_base_url)

    @property
    def effective_mode(self) -> str:
        if self.mode == "live":
            return "live"
        if self.mode == "mock":
            return "mock"
        return "live" if self.is_live_ready else "mock"
