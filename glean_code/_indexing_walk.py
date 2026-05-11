"""Helpers for building Indexing API request bodies from local file paths.

Used by /index.document --path and /index.bulk-documents --path. Only
plain-text formats are handled here: .txt, .md, .markdown, .html, .htm, .json.
Binary formats (PDF, .docx, etc.) are intentionally out of scope for v1.
"""
from __future__ import annotations

import fnmatch
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


DEFAULT_INCLUDE = ("*.txt", "*.md", "*.markdown", "*.html", "*.htm", "*.json")
DEFAULT_EXCLUDE = (".git", "node_modules", "__pycache__", ".DS_Store")
DEFAULT_MAX_BYTES = 5 * 1024 * 1024  # 5 MB


_MIME_BY_EXT: Dict[str, Tuple[str, str]] = {
    ".txt":      ("text/plain",       "textContent"),
    ".md":       ("text/markdown",    "textContent"),
    ".markdown": ("text/markdown",    "textContent"),
    ".html":     ("text/html",        "htmlContent"),
    ".htm":      ("text/html",        "htmlContent"),
    ".json":     ("application/json", "textContent"),
}


def supported_extensions() -> List[str]:
    return list(_MIME_BY_EXT.keys())


def mime_for_path(path: Path) -> Optional[Tuple[str, str]]:
    """Return (mimeType, body-key) for a supported extension, or None."""
    return _MIME_BY_EXT.get(path.suffix.lower())


_SLUG_RE = re.compile(r"[^a-z0-9._-]+")


def path_to_id(rel_path: Path, prefix: str = "") -> str:
    """Turn a relative path into a stable, datasource-safe id slug.

    >>> path_to_id(Path("team/onboarding.md"))
    'team-onboarding'
    >>> path_to_id(Path("notes/Q2 Planning.md"))
    'notes-q2-planning'
    """
    no_ext = rel_path.with_suffix("")
    joined = "-".join(no_ext.parts)
    slug = _SLUG_RE.sub("-", joined.lower()).strip("-")
    if prefix:
        slug = f"{prefix.strip('-')}-{slug}".strip("-")
    return slug


def filename_to_title(name: str) -> str:
    """Prettify a filename stem into a human title."""
    base = Path(name).stem
    cleaned = re.sub(r"[_\-]+", " ", base).strip()
    if cleaned and cleaned == cleaned.lower():
        cleaned = cleaned.title()
    return cleaned or name


def _matches_any(rel_str: str, name: str, patterns: Iterable[str]) -> bool:
    """True if either the full relative path, the filename, or any path
    component matches any of the patterns. Component matching lets bare names
    like 'node_modules' or '.git' exclude a whole subtree without the caller
    having to write recursive globs.
    """
    parts = Path(rel_str).parts
    for p in patterns:
        if fnmatch.fnmatch(rel_str, p):
            return True
        if fnmatch.fnmatch(name, p):
            return True
        if any(fnmatch.fnmatch(part, p) for part in parts):
            return True
    return False


def walk_files(root: Path,
               include: Iterable[str] = DEFAULT_INCLUDE,
               exclude: Iterable[str] = DEFAULT_EXCLUDE,
               max_bytes: int = DEFAULT_MAX_BYTES) -> Tuple[List[Tuple[Path, Path]], List[Tuple[Path, str]]]:
    """Walk root and return (matched, skipped).

    matched: list of (rel_path, abs_path) sorted alphabetically.
    skipped: list of (rel_path, reason) for files filtered out by size, etc.
    """
    if not root.exists():
        raise FileNotFoundError(f"path not found: {root}")

    matched: List[Tuple[Path, Path]] = []
    skipped: List[Tuple[Path, str]] = []

    if root.is_file():
        if _matches_any(root.name, root.name, include):
            if root.stat().st_size > max_bytes:
                skipped.append((Path(root.name), f"exceeds max_bytes ({root.stat().st_size} > {max_bytes})"))
            else:
                matched.append((Path(root.name), root.resolve()))
        return matched, skipped

    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        rel_str = str(rel)
        if _matches_any(rel_str, path.name, exclude):
            continue
        if not _matches_any(rel_str, path.name, include):
            continue
        if path.stat().st_size > max_bytes:
            skipped.append((rel, f"exceeds max_bytes ({path.stat().st_size} > {max_bytes})"))
            continue
        matched.append((rel, path.resolve()))
    return matched, skipped


def file_to_document(*, abs_path: Path, rel_path: Path, datasource: str,
                     object_type: str, permissions: Dict[str, Any],
                     view_url_prefix: str = "",
                     id_prefix: str = "") -> Dict[str, Any]:
    """Read a single file and build a DocumentDefinition payload."""
    mime_info = mime_for_path(abs_path)
    if mime_info is None:
        raise ValueError(
            f"unsupported file extension: {abs_path.suffix} (supported: {supported_extensions()})"
        )
    mime_type, body_key = mime_info
    text = abs_path.read_text(encoding="utf-8", errors="replace")
    doc_id = path_to_id(rel_path, prefix=id_prefix)
    title = filename_to_title(abs_path.name)
    if view_url_prefix:
        view_url = f"{view_url_prefix.rstrip('/')}/{rel_path.as_posix()}"
    else:
        view_url = abs_path.as_uri()
    return {
        "datasource":  datasource,
        "id":          doc_id,
        "objectType":  object_type,
        "title":       title,
        "viewURL":     view_url,
        "updatedAt":   int(abs_path.stat().st_mtime * 1000),
        "permissions": permissions,
        "body": {
            "mimeType": mime_type,
            body_key:   text,
        },
    }


def public_permissions() -> Dict[str, Any]:
    return {"allowAnonymousAccess": True}
