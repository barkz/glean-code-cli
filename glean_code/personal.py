"""Glean Personal — a local content index in one SQLite file.

Point it at a folder, and the files in it become searchable through the same
`/search` and `/chat` surfaces the REPL already has, plus MCP tools so an
external agent can reach them. Nothing is uploaded and nothing listens on a
port: the whole index is `~/.gleancode/personal.db`, which makes it portable
by copy.

Design notes worth keeping in view:

  * Full-text search is SQLite FTS5, which is compiled into essentially every
    SQLite the stdlib ships against. A capability probe at connect time falls
    back to a plain table plus a Python scorer, so a locked-down interpreter
    degrades in quality rather than failing.
  * Chunks, not whole files. A 40-page document answers a question from one
    section of itself, and an agent consuming this over MCP wants the passage,
    not the file. Chunk text lives in exactly one place — the text store — so
    there is no copy to keep in sync.
  * Re-indexing is incremental on a content hash, so pointing this at a
    5,000-file folder every day re-reads only what changed.
  * Local results are REAL content but they are NOT organisation-wide Glean.
    Every surface labels them (`LOCAL_BANNER`), for the same reason mock mode
    carries its banner: a consumer cannot otherwise tell which index answered,
    and "my Downloads folder" must never be mistaken for company truth.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import sqlite3
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from . import _indexing_walk as _walk
from . import extract
from .config import CONFIG_DIR

DB_PATH = CONFIG_DIR / "personal.db"
SCHEMA_VERSION = 1

# Travels with every local answer, into a terminal or an agent's context.
LOCAL_BANNER = (
    "[LOCAL INDEX] From files indexed on this machine, not your organisation's "
    "Glean index — scope is whatever folders you indexed."
)

# Chunk sizing. 1200 characters is roughly 300 tokens: big enough to answer a
# question on its own, small enough that several fit in a prompt.
CHUNK_CHARS = 1200
CHUNK_OVERLAP = 150

DEFAULT_LABEL = "local"
DEFAULT_EXCLUDE = _walk.DEFAULT_EXCLUDE + (
    ".venv", "venv", "dist", "build", ".tox", ".mypy_cache", ".pytest_cache",
    "~$*",          # Office lock files
)
DEFAULT_MAX_BYTES = _walk.DEFAULT_MAX_BYTES


class PersonalError(Exception):
    """Anything the user needs to be told about, phrased for a terminal."""


# ---------------------------------------------------------------- schema

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
CREATE TABLE IF NOT EXISTS sources (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    root         TEXT NOT NULL UNIQUE,
    label        TEXT NOT NULL,
    include      TEXT,
    exclude      TEXT,
    max_bytes    INTEGER,
    added_at     REAL NOT NULL,
    last_indexed REAL
);
CREATE TABLE IF NOT EXISTS documents (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id    INTEGER NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    doc_id       TEXT NOT NULL,
    rel_path     TEXT NOT NULL,
    abs_path     TEXT NOT NULL,
    title        TEXT,
    ext          TEXT,
    mime         TEXT,
    bytes        INTEGER,
    mtime        REAL,
    content_hash TEXT,
    nchars       INTEGER,
    chunk_count  INTEGER,
    indexed_at   REAL,
    UNIQUE (source_id, rel_path),
    UNIQUE (source_id, doc_id)
);
CREATE TABLE IF NOT EXISTS chunks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    ordinal     INTEGER NOT NULL,
    heading     TEXT,
    nchars      INTEGER
);
CREATE TABLE IF NOT EXISTS doc_links (
    a_doc    INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    b_doc    INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    kind     TEXT NOT NULL,
    score    REAL NOT NULL,
    evidence TEXT,
    PRIMARY KEY (a_doc, b_doc, kind)
);
CREATE INDEX IF NOT EXISTS idx_chunks_doc ON chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_documents_source ON documents(source_id);
CREATE INDEX IF NOT EXISTS idx_doc_links_a ON doc_links(a_doc);
"""

# The text store. Chunk bodies live here and nowhere else, so the two variants
# are interchangeable and there is never a second copy to keep in step. Column
# order matters: bm25() weights are positional.
_FTS_SCHEMA = """
CREATE VIRTUAL TABLE chunks_fts USING fts5(
    text, heading, title, tokenize='porter unicode61'
);
"""
_PLAIN_SCHEMA = """
CREATE TABLE chunks_text (
    rowid   INTEGER PRIMARY KEY,
    text    TEXT,
    heading TEXT,
    title   TEXT
);
"""

# bm25 column weights: a title hit beats a body hit by a wide margin.
_BM25_WEIGHTS = (4.0, 2.0, 8.0)

STORE_FTS = "fts5"
STORE_PLAIN = "plain"


def connect(path: Optional[Path] = None) -> sqlite3.Connection:
    """Open (creating if needed) the personal index with 0600 permissions."""
    target = Path(path) if path else DB_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    fresh = not target.exists()
    conn = sqlite3.connect(str(target))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(_SCHEMA)
    _migrate(conn)
    store = _ensure_text_store(conn)
    conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('schema_version', ?)",
                 (str(SCHEMA_VERSION),))
    conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('text_store', ?)",
                 (store,))
    conn.commit()
    if fresh:
        try:
            os.chmod(target, 0o600)
        except OSError:
            pass
    return conn


def _migrate(conn: sqlite3.Connection) -> None:
    """Additive, idempotent column adds for databases written by older versions.

    `CREATE TABLE IF NOT EXISTS` never reaches an existing table, so new
    columns have to arrive this way. Nothing here drops or rewrites data.
    """
    added: Dict[str, Dict[str, str]] = {
        # v1 is the first release; entries land here as the schema grows.
    }
    for table, columns in added.items():
        try:
            have = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
        except sqlite3.Error:
            continue
        for name, decl in columns.items():
            if name not in have:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")


def _tables(conn: sqlite3.Connection) -> set:
    return {r["name"] for r in
            conn.execute("SELECT name FROM sqlite_master WHERE type IN ('table','view')")}


def _ensure_text_store(conn: sqlite3.Connection) -> str:
    """Create the text store, preferring FTS5. Returns which one is in use.

    An existing database keeps whatever it was built with — switching would
    orphan every indexed chunk.
    """
    have = _tables(conn)
    if "chunks_fts" in have:
        return STORE_FTS
    if "chunks_text" in have:
        return STORE_PLAIN
    try:
        conn.executescript(_FTS_SCHEMA)
        return STORE_FTS
    except sqlite3.Error:
        conn.executescript(_PLAIN_SCHEMA)
        return STORE_PLAIN


def text_store(conn: sqlite3.Connection) -> str:
    return STORE_FTS if "chunks_fts" in _tables(conn) else STORE_PLAIN


def fts5_available() -> bool:
    """Whether this interpreter's SQLite can build an FTS5 table at all."""
    probe = sqlite3.connect(":memory:")
    try:
        probe.execute("CREATE VIRTUAL TABLE t USING fts5(x)")
        return True
    except sqlite3.Error:
        return False
    finally:
        probe.close()


def db_size(path: Optional[Path] = None) -> int:
    target = Path(path) if path else DB_PATH
    try:
        return target.stat().st_size
    except OSError:
        return 0


def _store_table(store: str) -> str:
    return "chunks_fts" if store == STORE_FTS else "chunks_text"


# ---------------------------------------------------------------- chunking

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")
_PARA_SPLIT = re.compile(r"\n{2,}")
_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")


def split_sections(text: str) -> List[Tuple[Optional[str], str]]:
    """Break text into (heading, body) sections on markdown headings.

    The Office extractors emit `## Sheet name` / `## Slide 3` markers, so
    spreadsheets and decks section themselves through the same path.
    """
    sections: List[Tuple[Optional[str], str]] = []
    heading: Optional[str] = None
    buf: List[str] = []

    def flush() -> None:
        body = "\n".join(buf).strip()
        if body:
            sections.append((heading, body))
        elif heading:
            # A heading with nothing under it is still worth finding.
            sections.append((heading, heading))

    for line in (text or "").split("\n"):
        m = _HEADING_RE.match(line)
        if m:
            flush()
            heading = m.group(2)
            buf = []
        else:
            buf.append(line)
    flush()
    if not sections and (text or "").strip():
        sections.append((None, text.strip()))
    return sections


def _tail(text: str, chars: int) -> str:
    """Last `chars` of text, snapped forward to a word boundary."""
    if len(text) <= chars:
        return text
    piece = text[-chars:]
    cut = piece.find(" ")
    return piece[cut + 1:] if cut != -1 else piece


def _sentence_windows(body: str, limit: int, overlap: int) -> List[str]:
    """Pack sentences into windows, carrying `overlap` characters forward.

    Only reached for a paragraph longer than one chunk. Overlap matters here
    and nowhere else: a cut inside a paragraph can split the sentence that
    answers the question, whereas a cut at a paragraph break cannot.
    """
    out: List[str] = []
    cur = ""
    for sentence in _SENT_SPLIT.split(body):
        sentence = sentence.strip()
        if not sentence:
            continue
        if not cur:
            cur = sentence
            continue
        if len(cur) + 1 + len(sentence) <= limit:
            cur = f"{cur} {sentence}"
        else:
            out.append(cur)
            carry = _tail(cur, overlap)
            cur = f"{carry} {sentence}" if carry else sentence
    if cur:
        out.append(cur)
    # A single sentence longer than the limit still has to be cut somewhere.
    final: List[str] = []
    for piece in out:
        while len(piece) > limit:
            head = piece[:limit].rsplit(" ", 1)[0] or piece[:limit]
            final.append(head)
            piece = _tail(piece[:limit], overlap) + piece[limit:]
            if len(piece) <= limit:
                break
        if piece:
            final.append(piece)
    return final


def chunk_text(text: str, limit: int = CHUNK_CHARS,
               overlap: int = CHUNK_OVERLAP) -> List[Tuple[Optional[str], str]]:
    """Split a document into [(heading, chunk_text)].

    Paragraphs are packed greedily and split at blank lines, which are natural
    boundaries needing no overlap. Only an oversized paragraph falls through to
    sentence windowing, which does overlap.
    """
    chunks: List[Tuple[Optional[str], str]] = []
    for heading, body in split_sections(text):
        cur = ""
        for para in _PARA_SPLIT.split(body):
            para = para.strip()
            if not para:
                continue
            if len(para) > limit:
                if cur:
                    chunks.append((heading, cur))
                    cur = ""
                for window in _sentence_windows(para, limit, overlap):
                    chunks.append((heading, window))
                continue
            if not cur:
                cur = para
            elif len(cur) + 2 + len(para) <= limit:
                cur = f"{cur}\n\n{para}"
            else:
                chunks.append((heading, cur))
                cur = para
        if cur:
            chunks.append((heading, cur))
    return chunks


# ---------------------------------------------------------------- sources

def _json_list(value: Optional[str], fallback: Sequence[str]) -> Tuple[str, ...]:
    if not value:
        return tuple(fallback)
    try:
        data = json.loads(value)
    except ValueError:
        return tuple(fallback)
    if isinstance(data, list) and all(isinstance(x, str) for x in data):
        return tuple(data) or tuple(fallback)
    return tuple(fallback)


def _resolve_root(folder: str) -> Path:
    root = Path(folder).expanduser()
    try:
        root = root.resolve()
    except OSError as e:
        raise PersonalError(f"could not resolve {folder}: {e}") from None
    if not root.exists():
        raise PersonalError(f"path not found: {root}")
    return root


def sources(conn: Optional[sqlite3.Connection] = None,
            db: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Every indexed root, with its document and chunk counts."""
    own = conn is None
    conn = conn or connect(db)
    try:
        rows = conn.execute("""
            SELECT s.*,
                   (SELECT COUNT(*) FROM documents d WHERE d.source_id = s.id) AS documents,
                   (SELECT COUNT(*) FROM chunks c
                      JOIN documents d ON d.id = c.document_id
                     WHERE d.source_id = s.id) AS chunks
              FROM sources s ORDER BY s.label, s.root
        """).fetchall()
        return [dict(r) for r in rows]
    finally:
        if own:
            conn.close()


def _find_source(conn: sqlite3.Connection, needle: str) -> Optional[sqlite3.Row]:
    """Look a source up by label, exact root, or resolved path."""
    row = conn.execute("SELECT * FROM sources WHERE label = ?", (needle,)).fetchone()
    if row:
        return row
    row = conn.execute("SELECT * FROM sources WHERE root = ?", (needle,)).fetchone()
    if row:
        return row
    try:
        resolved = str(Path(needle).expanduser().resolve())
    except OSError:
        return None
    return conn.execute("SELECT * FROM sources WHERE root = ?", (resolved,)).fetchone()


def remove_source(needle: str, db: Optional[Path] = None) -> Dict[str, Any]:
    """Forget a source and everything indexed from it. Files are untouched."""
    conn = connect(db)
    try:
        row = _find_source(conn, needle)
        if not row:
            raise PersonalError(f"no indexed source matching '{needle}'. See /personal sources.")
        doc_ids = [r["id"] for r in
                   conn.execute("SELECT id FROM documents WHERE source_id = ?", (row["id"],))]
        removed_chunks = _delete_documents(conn, doc_ids, text_store(conn))
        conn.execute("DELETE FROM sources WHERE id = ?", (row["id"],))
        conn.commit()
        return {"label": row["label"], "root": row["root"],
                "documents": len(doc_ids), "chunks": removed_chunks}
    finally:
        conn.close()


# ---------------------------------------------------------------- indexing

class IndexReport(Dict[str, Any]):
    """Plain dict; a class only so callers get a name in tracebacks."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _unique_doc_id(conn: sqlite3.Connection, source_id: int,
                   base: str, rel_path: str) -> str:
    """A stable slug, unique across every source.

    Global rather than per-source because this id is what `/personal show`,
    `local_fetch` and search results hand back, and `_resolve_doc` looks it up
    without a source. Two folders that default to the same label — `~/a/docs`
    and `~/b/docs` — would otherwise both mint `docs-readme`, and every lookup
    would silently return whichever came first.
    """
    base = base or "doc"
    candidate = base
    n = 2
    while True:
        row = conn.execute(
            "SELECT source_id, rel_path FROM documents WHERE doc_id = ?",
            (candidate,)).fetchone()
        if row is None or (row["source_id"] == source_id
                           and row["rel_path"] == rel_path):
            return candidate
        candidate = f"{base}-{n}"
        n += 1


def _delete_documents(conn: sqlite3.Connection, doc_ids: Sequence[int],
                      store: str) -> int:
    """Drop documents, their chunks, and their text-store rows. Returns chunks."""
    if not doc_ids:
        return 0
    table = _store_table(store)
    total = 0
    for doc_id in doc_ids:
        rows = conn.execute("SELECT id FROM chunks WHERE document_id = ?", (doc_id,)).fetchall()
        for row in rows:
            conn.execute(f"DELETE FROM {table} WHERE rowid = ?", (row["id"],))
        total += len(rows)
        # Chunks and links cascade from documents; the text store cannot,
        # because a virtual table carries no foreign keys.
        conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
    return total


def _write_chunks(conn: sqlite3.Connection, document_id: int, title: str,
                  pieces: Sequence[Tuple[Optional[str], str]], store: str) -> int:
    table = _store_table(store)
    for ordinal, (heading, body) in enumerate(pieces):
        cur = conn.execute(
            "INSERT INTO chunks (document_id, ordinal, heading, nchars) VALUES (?,?,?,?)",
            (document_id, ordinal, heading, len(body)))
        conn.execute(
            f"INSERT INTO {table} (rowid, text, heading, title) VALUES (?,?,?,?)",
            (cur.lastrowid, body, heading or "", title or ""))
    return len(pieces)


def index_source(folder: str,
                 label: Optional[str] = None,
                 include: Optional[Sequence[str]] = None,
                 exclude: Optional[Sequence[str]] = None,
                 max_bytes: Optional[int] = None,
                 reindex: bool = False,
                 db: Optional[Path] = None,
                 progress: Optional[Any] = None) -> IndexReport:
    """Index (or re-index) one folder. Returns counts and skip reasons.

    Incremental by content hash: an unchanged file is not re-read past its
    digest. Files that have disappeared from disk, or that new filters now
    exclude, are removed from the index.
    """
    started = time.time()
    root = _resolve_root(folder)
    conn = connect(db)
    try:
        store = text_store(conn)
        existing = conn.execute("SELECT * FROM sources WHERE root = ?", (str(root),)).fetchone()

        if existing:
            src_label = label or existing["label"]
            inc = tuple(include) if include else _json_list(existing["include"], extract.INCLUDE_PATTERNS)
            exc = tuple(exclude) if exclude else _json_list(existing["exclude"], DEFAULT_EXCLUDE)
            cap = int(max_bytes if max_bytes is not None else (existing["max_bytes"] or DEFAULT_MAX_BYTES))
            source_id = existing["id"]
            conn.execute("UPDATE sources SET label=?, include=?, exclude=?, max_bytes=? WHERE id=?",
                         (src_label, json.dumps(list(inc)), json.dumps(list(exc)), cap, source_id))
        else:
            src_label = label or _default_label(root)
            inc = tuple(include) if include else tuple(extract.INCLUDE_PATTERNS)
            exc = tuple(exclude) if exclude else tuple(DEFAULT_EXCLUDE)
            cap = int(max_bytes if max_bytes is not None else DEFAULT_MAX_BYTES)
            cur = conn.execute(
                "INSERT INTO sources (root, label, include, exclude, max_bytes, added_at) "
                "VALUES (?,?,?,?,?,?)",
                (str(root), src_label, json.dumps(list(inc)), json.dumps(list(exc)),
                 cap, started))
            source_id = cur.lastrowid

        try:
            matched, skipped = _walk.walk_files(root, include=inc, exclude=exc, max_bytes=cap)
        except FileNotFoundError as e:
            raise PersonalError(str(e)) from None

        seen: set = set()
        added = updated = unchanged = 0
        chunks_written = 0
        skips: List[Tuple[str, str]] = [(str(rel), reason) for rel, reason in skipped]

        for rel, abs_path in matched:
            rel_str = rel.as_posix()
            seen.add(rel_str)
            if progress:
                progress(rel_str)
            try:
                stat = abs_path.stat()
                digest = _sha256(abs_path)
            except OSError as e:
                skips.append((rel_str, f"unreadable: {e}"))
                continue

            row = conn.execute(
                "SELECT * FROM documents WHERE source_id = ? AND rel_path = ?",
                (source_id, rel_str)).fetchone()
            if row and not reindex and row["content_hash"] == digest:
                conn.execute("UPDATE documents SET mtime=?, indexed_at=? WHERE id=?",
                             (stat.st_mtime, started, row["id"]))
                unchanged += 1
                continue

            try:
                text, title_hint = extract.extract(abs_path)
            except extract.ExtractError as e:
                skips.append((rel_str, str(e)))
                continue
            if not text.strip():
                skips.append((rel_str, "no extractable text"))
                continue

            title = title_hint or _walk.filename_to_title(abs_path.name)
            pieces = chunk_text(text)
            if not pieces:
                skips.append((rel_str, "no extractable text"))
                continue

            if row:
                _delete_documents(conn, [row["id"]], store)
                updated += 1
            else:
                added += 1

            doc_slug = _unique_doc_id(
                conn, source_id, _walk.path_to_id(rel, prefix=src_label), rel_str)
            cur = conn.execute("""
                INSERT INTO documents
                    (source_id, doc_id, rel_path, abs_path, title, ext, mime,
                     bytes, mtime, content_hash, nchars, chunk_count, indexed_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (source_id, doc_slug, rel_str, str(abs_path), title,
                  abs_path.suffix.lower(), extract.mime_for(abs_path),
                  stat.st_size, stat.st_mtime, digest, len(text),
                  len(pieces), started))
            chunks_written += _write_chunks(conn, cur.lastrowid, title, pieces, store)

        # Anything indexed before but no longer matched has left the corpus.
        stale = [r["id"] for r in conn.execute(
            "SELECT id, rel_path FROM documents WHERE source_id = ?", (source_id,))
            if r["rel_path"] not in seen]
        removed_chunks = _delete_documents(conn, stale, store)

        conn.execute("UPDATE sources SET last_indexed = ? WHERE id = ?",
                     (time.time(), source_id))
        conn.commit()

        return IndexReport(
            root=str(root), label=src_label, store=store,
            added=added, updated=updated, unchanged=unchanged,
            removed=len(stale), removed_chunks=removed_chunks,
            chunks=chunks_written, skipped=skips,
            files=len(matched), elapsed=time.time() - started,
        )
    finally:
        conn.close()


def _default_label(root: Path) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", root.name.lower()).strip("-")
    return slug or DEFAULT_LABEL


# ---------------------------------------------------------------- retrieval

# Unicode-aware on purpose. An ASCII-only class silently mangles non-English
# content: "Munchen" with an umlaut tokenized to "nchen", "Zurich" with one to
# "rich", and a CJK query to nothing at all — indexed but unreachable. FTS5's
# unicode61 tokenizer keeps those characters, so the query builder has to as
# well. The leading [^\W_] excludes underscores from starting a term.
#
# Inner punctuation is kept so "comp-plan", "v1.2" and "q3.report" survive
# as single terms; the trailing run is then stripped, or "weekly." and
# "weekly" become different terms and stop matching each other.
_WORD_RE = re.compile(r"[^\W_][\w'\u2019._-]*", re.UNICODE)
_EDGE_PUNCT = "._-" + "'\u2019"

_STOPWORDS = frozenset("""
a an and are as at be by do does for from how has have i in is it its me my of on or our
the their there this to us was we what when where which who why will with you your
""".split())

# Ceiling for the no-FTS5 fallback scan. Reached only on an interpreter whose
# SQLite lacks FTS5, where the alternative is no search at all.
MAX_SCAN_ROWS = 50_000

# Above this many query terms the no-FTS5 prefilter is dropped and the scan runs
# unfiltered: a long OR-chain stops narrowing anything, and correctness on the
# fallback path matters more than the rows saved.
_MAX_PREFILTER_TERMS = 12


def _words(text: str) -> List[str]:
    """Every term in text, lowercased, with edge punctuation trimmed."""
    out: List[str] = []
    for raw in _WORD_RE.findall((text or "").lower()):
        word = raw.strip(_EDGE_PUNCT)
        if word:
            out.append(word)
    return out


def _tokens(text: str) -> List[str]:
    """Query and content terms: words minus stopwords and single characters."""
    return [w for w in _words(text) if w not in _STOPWORDS and len(w) > 1]


_QUOTED_RE = re.compile(r'"([^"]+)"')
_ONE_LINE = re.compile(r"\s+")


def fts_query(query: str) -> str:
    """Turn free text into a safe FTS5 MATCH expression.

    Every term is quoted so that a stray `-`, `:`, `*`, `OR` or `NEAR` in the
    user's words is data rather than syntax. Bare terms get a prefix wildcard;
    a "double quoted" span stays an exact phrase. Terms are ORed and left to
    bm25 to rank, which beats ANDing them and returning nothing.
    """
    query = query or ""
    parts: List[str] = []
    for phrase in _QUOTED_RE.findall(query):
        words = _words(phrase)
        if words:
            parts.append('"' + " ".join(words) + '"')
    remainder = _QUOTED_RE.sub(" ", query)
    for token in _tokens(remainder):
        parts.append(f'"{token}"*')
    return " OR ".join(parts)


def _matched_terms(text: str, title: str, heading: str,
                   tokens: Sequence[str]) -> List[str]:
    """Which query terms appear in this passage.

    Re-derived rather than reported by FTS5, which does not expose per-term
    hits. It is therefore an approximation in one direction: FTS5 tokenizes
    with the porter stemmer, so it can match a term this check misses on an
    irregular stem. Prefix matching is checked both ways, which covers the
    common plural/singular case ("agents" against "agent"), and the fallout
    from a miss is an explanation that under-reports, never a wrong result.
    """
    words = set(_words(text)) | set(_words(title)) | set(_words(heading))
    matched: List[str] = []
    for token in tokens:
        if token in words or any(
            word.startswith(token) or (len(word) >= 4 and token.startswith(word))
            for word in words
        ):
            matched.append(token)
    return matched


# Two scores this close are not meaningfully different: bm25 is corpus-relative,
# and presenting a 0.4% gap as an ordering invites more trust than it earns.
TIE_TOLERANCE = 0.01


def tie_groups(scores: Sequence[float]) -> List[int]:
    """Group index per score, where adjacent near-equal scores share a group."""
    groups: List[int] = []
    current = 0
    for i, score in enumerate(scores):
        if i:
            previous = scores[i - 1]
            spread = abs(previous - score) / max(abs(previous), abs(score), 1e-12)
            if spread > TIE_TOLERANCE:
                current += 1
        groups.append(current)
    return groups


def _snippet(text: str, tokens: Sequence[str], limit: int = 240) -> str:
    """The most on-topic window of a chunk, cut at sentence boundaries."""
    sentences = [s.strip() for s in _SENT_SPLIT.split(text or "") if s.strip()]
    if not sentences:
        return (text or "")[:limit]
    best_i, best_hits = 0, -1
    for i, sentence in enumerate(sentences):
        words = set(_words(sentence))
        hits = sum(1 for t in tokens if t in words)
        if hits > best_hits:
            best_hits, best_i = hits, i
    out = sentences[best_i]
    nxt = best_i + 1
    while nxt < len(sentences) and len(out) + 1 + len(sentences[nxt]) <= limit:
        out = f"{out} {sentences[nxt]}"
        nxt += 1
    if len(out) > limit:
        out = out[:limit].rsplit(" ", 1)[0] + "…"
    prefix = "…" if best_i > 0 else ""
    # One line out. Structured formats (JSON, spreadsheets) carry no sentence
    # enders, so a whole chunk arrives as a single "sentence" full of newlines
    # and wrecks any aligned layout it is dropped into.
    return _ONE_LINE.sub(" ", f"{prefix}{out}").strip()


_HIT_SQL = """
SELECT {store}.rowid      AS chunk_id,
       {store}.text       AS text,
       {score}            AS score,
       c.heading          AS heading,
       c.ordinal          AS ordinal,
       d.id               AS document_id,
       d.doc_id           AS doc_id,
       d.title            AS title,
       d.rel_path         AS rel_path,
       d.abs_path         AS abs_path,
       d.ext              AS ext,
       d.bytes            AS bytes,
       d.chunk_count      AS chunk_count,
       d.mtime            AS mtime,
       s.label            AS label,
       s.root             AS root
  FROM {store}
  JOIN chunks    c ON c.id = {store}.rowid
  JOIN documents d ON d.id = c.document_id
  JOIN sources   s ON s.id = d.source_id
 WHERE {where}
"""


def _hit_rows(conn: sqlite3.Connection, query: str, source: Optional[str],
              store: str, scan: int) -> List[sqlite3.Row]:
    """Candidate chunks for a query, best-first where the store can rank."""
    label_clause = "AND (:label IS NULL OR s.label = :label)"
    if store == STORE_FTS:
        match = fts_query(query)
        if not match:
            return []
        sql = _HIT_SQL.format(
            store="chunks_fts",
            score="bm25(chunks_fts, {}, {}, {})".format(*_BM25_WEIGHTS),
            where=f"chunks_fts MATCH :match {label_clause}",
        ) + " ORDER BY score LIMIT :scan"
        return conn.execute(sql, {"match": match, "label": source, "scan": scan}).fetchall()

    # No FTS5: pull candidate rows and score them in Python. The prefilter has
    # to cover *every* term, not just one — filtering on the longest token alone
    # dropped any document that matched only a different term, so
    # search("payments zebra") could not return the one file containing "zebra".
    # Past a handful of terms the prefilter stops paying for itself and is
    # skipped entirely, because losing recall is worse than reading more rows.
    tokens = _tokens(query)
    where = "1=1 " + label_clause
    params: Dict[str, Any] = {"label": source, "scan": min(scan, MAX_SCAN_ROWS)}
    if tokens and len(tokens) <= _MAX_PREFILTER_TERMS:
        clauses = []
        for i, token in enumerate(tokens):
            key = f"like{i}"
            clauses.append(f"(chunks_text.text LIKE :{key} "
                           f"OR chunks_text.title LIKE :{key} "
                           f"OR chunks_text.heading LIKE :{key})")
            params[key] = f"%{token}%"
        where = "(" + " OR ".join(clauses) + ") " + label_clause
    sql = _HIT_SQL.format(store="chunks_text", score="0.0", where=where) + " LIMIT :scan"
    return conn.execute(sql, params).fetchall()


def search(query: str, limit: int = 10, source: Optional[str] = None,
           db: Optional[Path] = None,
           conn: Optional[sqlite3.Connection] = None) -> List[Dict[str, Any]]:
    """Rank indexed documents against a query, best first.

    One row per document, carrying the best-matching chunk's snippet and how
    many of its chunks matched at all.
    """
    own = conn is None
    conn = conn or connect(db)
    try:
        store = text_store(conn)
        tokens = _tokens(query)
        # FTS5 ranks in SQL, so a modest candidate window is enough. The plain
        # store cannot rank at all — scoring happens in Python afterwards — so
        # it has to see the whole corpus or it silently loses recall.
        scan = (max(200, limit * 20) if store == STORE_FTS else MAX_SCAN_ROWS)
        rows = _hit_rows(conn, query, source, store, scan=scan)

        # The fallback scorer needs rarity weights, which only exist once the
        # candidate set is known.
        weights = (None if store == STORE_FTS or not tokens
                   else _fallback_weights(rows, tokens))

        best: Dict[int, Dict[str, Any]] = {}
        counts: Counter = Counter()
        for row in rows:
            if store == STORE_FTS:
                # bm25 returns negatives, better being more negative.
                score = -float(row["score"])
            else:
                score = _python_score(row["text"], row["title"], row["heading"],
                                      tokens, weights)
                if score <= 0:
                    continue
            doc = row["document_id"]
            counts[doc] += 1
            prev = best.get(doc)
            if prev is None or score > prev["score"]:
                best[doc] = {"row": row, "score": score}

        out: List[Dict[str, Any]] = []
        for doc_id, entry in best.items():
            row = entry["row"]
            extra = counts[doc_id] - 1
            # A document matching in several places is more likely on-topic,
            # but the effect has to stay small or long files always win.
            score = entry["score"] * (1.0 + min(0.3, 0.06 * extra))
            out.append({
                "document_id": doc_id,
                "doc_id": row["doc_id"],
                "title": row["title"] or row["rel_path"],
                "rel_path": row["rel_path"],
                "abs_path": row["abs_path"],
                "url": _file_url(row["abs_path"]),
                "datasource": row["label"],
                "root": row["root"],
                "ext": row["ext"],
                "bytes": row["bytes"],
                "mtime": row["mtime"],
                "heading": row["heading"],
                "chunk_ordinal": row["ordinal"],
                "matched_chunks": counts[doc_id],
                "total_chunks": row["chunk_count"],
                "matched_terms": _matched_terms(
                    row["text"], row["title"], row["heading"], tokens),
                "query_terms": list(tokens),
                "score": _sig(score),
                "snippet": _snippet(row["text"], tokens),
            })
        out.sort(key=lambda r: (-r["score"], -(r["mtime"] or 0), r["doc_id"]))
        return out[:max(0, int(limit))]
    finally:
        if own:
            conn.close()


def _token_hit(token: str, words: set) -> bool:
    return token in words or any(word.startswith(token) for word in words)


def _fallback_weights(rows: Sequence[sqlite3.Row],
                      tokens: Sequence[str]) -> Dict[str, float]:
    """Rarity weight per query term, measured over the candidate rows.

    bm25 gets this from the index; the plain scorer has no statistics at all, so
    without it every term counts the same and a word appearing in most documents
    outranks the one rare word that actually distinguishes a hit. Measured on a
    131-document fallback corpus, `search("payments zebra")` scored the single
    file containing "zebra" identically to all 130 containing "payments", so it
    placed by mtime rather than relevance and fell outside the results.
    """
    n = max(1, len(rows))
    df: Counter = Counter()
    for row in rows:
        words = (set(_words(row["text"])) | set(_words(row["title"]))
                 | set(_words(row["heading"])))
        for token in tokens:
            if _token_hit(token, words):
                df[token] += 1
    return {t: math.log((n + 1.0) / (df.get(t, 0) + 0.5)) for t in tokens}


def _python_score(text: str, title: str, heading: str, tokens: Sequence[str],
                  weights: Optional[Dict[str, float]] = None) -> float:
    """Fallback relevance when FTS5 is unavailable. Same weighting spirit as bm25."""
    if not tokens:
        return 0.0
    body_words = set(_words(text))
    title_words = set(_words(title))
    head_words = set(_words(heading))
    score = 0.0
    for token in tokens:
        weight = 1.0 if weights is None else max(0.05, weights.get(token, 1.0))
        field = 0.0
        if token in title_words:
            field += 8.0
        elif any(w.startswith(token) for w in title_words):
            field += 4.0
        if token in head_words:
            field += 2.0
        if token in body_words:
            field += 4.0
        elif any(w.startswith(token) for w in body_words):
            field += 1.0
        score += field * weight
    return score


def _sig(value: float, digits: int = 4) -> float:
    """Round to significant figures, not decimal places.

    bm25 scores on a small corpus land around 1e-06 — every term is in most
    documents, so the IDF factor is nearly zero. Fixed-point rounding turns
    the whole result set into 0.0 and throws away the ordering it is meant
    to show.
    """
    try:
        return float(f"{value:.{digits}g}")
    except (TypeError, ValueError):
        return 0.0


def _file_url(abs_path: str) -> str:
    try:
        return Path(abs_path).as_uri()
    except (ValueError, OSError):
        return f"file://{abs_path}"


# ---------------------------------------------------------------- lookup

_DOC_SELECT = ("SELECT d.*, s.label, s.root FROM documents d "
               "JOIN sources s ON s.id = d.source_id WHERE ")

# Tried in order: exact identifiers first, then progressively looser matches, so
# `/personal show roadmap` finds sub/roadmap.txt without ever preferring a fuzzy
# hit over an exact one. ORDER BY keeps an ambiguous ref resolving the same way
# every time rather than depending on row order.
_DOC_LOOKUPS: Tuple[Tuple[str, bool], ...] = (
    ("d.doc_id = :ref", False),
    ("d.abs_path = :ref", False),
    ("d.rel_path = :ref", False),
    ("d.doc_id LIKE :like", True),
    ("d.rel_path LIKE :like", True),
    ("d.title LIKE :like", True),
)


def _resolve_doc(conn: sqlite3.Connection, ref: str) -> Optional[sqlite3.Row]:
    """Find one document by id, path, file URL, title, or any unique fragment."""
    ref = (ref or "").strip()
    if not ref:
        return None
    if ref.startswith("file://"):
        ref = ref[7:]
    params = {"ref": ref, "like": f"%{ref}%"}
    for clause, _fuzzy in _DOC_LOOKUPS:
        row = conn.execute(
            f"{_DOC_SELECT}{clause} ORDER BY d.rel_path LIMIT 1", params).fetchone()
        if row:
            return row
    return None


def fetch(ref: str, db: Optional[Path] = None,
          max_chars: int = 40_000) -> Optional[Dict[str, Any]]:
    """One document with its text reassembled from chunks, or None."""
    conn = connect(db)
    try:
        row = _resolve_doc(conn, ref)
        if not row:
            return None
        table = _store_table(text_store(conn))
        pieces = conn.execute(f"""
            SELECT c.ordinal, c.heading, {table}.text AS text
              FROM chunks c JOIN {table} ON {table}.rowid = c.id
             WHERE c.document_id = ? ORDER BY c.ordinal
        """, (row["id"],)).fetchall()
        body_parts: List[str] = []
        used = 0
        truncated = False
        for piece in pieces:
            text = piece["text"] or ""
            if used + len(text) > max_chars:
                # Cut inside this chunk rather than dropping it. Bailing out
                # returned an empty body whenever the first chunk alone
                # exceeded the budget, which is the common case for a small
                # max_chars against any real document.
                room = max_chars - used
                if room > 0:
                    body_parts.append(text[:room].rsplit(" ", 1)[0] or text[:room])
                truncated = True
                break
            body_parts.append(text)
            used += len(text)
        return {
            "doc_id": row["doc_id"],
            "title": row["title"] or row["rel_path"],
            "rel_path": row["rel_path"],
            "abs_path": row["abs_path"],
            "url": _file_url(row["abs_path"]),
            "datasource": row["label"],
            "root": row["root"],
            "ext": row["ext"],
            "mime": row["mime"],
            "bytes": row["bytes"],
            "mtime": row["mtime"],
            "chunk_count": row["chunk_count"],
            "nchars": row["nchars"],
            "indexed_at": row["indexed_at"],
            # De-duplicated, order preserved: a long section splits across
            # several chunks that all carry its heading, and listing it once
            # per chunk reads as a document with repeated sections.
            "headings": list(dict.fromkeys(
                p["heading"] for p in pieces if p["heading"])),
            "text": "\n\n".join(body_parts),
            "truncated": truncated,
        }
    finally:
        conn.close()


def list_documents(source: Optional[str] = None, limit: int = 100,
                   db: Optional[Path] = None) -> List[Dict[str, Any]]:
    conn = connect(db)
    try:
        rows = conn.execute("""
            SELECT d.doc_id, d.title, d.rel_path, d.abs_path, d.ext, d.bytes,
                   d.mtime, d.chunk_count, s.label
              FROM documents d JOIN sources s ON s.id = d.source_id
             WHERE (:label IS NULL OR s.label = :label)
             ORDER BY d.mtime DESC LIMIT :limit
        """, {"label": source, "limit": max(1, int(limit))}).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def stats(db: Optional[Path] = None) -> Dict[str, Any]:
    target = Path(db) if db else DB_PATH
    conn = connect(db)
    try:
        one = lambda sql: conn.execute(sql).fetchone()[0]  # noqa: E731
        return {
            "path": str(target),
            "size": db_size(target),
            "store": text_store(conn),
            "sources": one("SELECT COUNT(*) FROM sources"),
            "documents": one("SELECT COUNT(*) FROM documents"),
            "chunks": one("SELECT COUNT(*) FROM chunks"),
            "characters": one("SELECT COALESCE(SUM(nchars), 0) FROM documents"),
            "links": one("SELECT COUNT(*) FROM doc_links"),
            "last_indexed": one("SELECT COALESCE(MAX(last_indexed), 0) FROM sources") or None,
        }
    finally:
        conn.close()


def is_empty(db: Optional[Path] = None) -> bool:
    """True when nothing has been indexed yet.

    Callers use this to tell "your index is empty" from "no match for that
    query", which are very different pieces of advice. It deliberately checks
    for the file first: connect() creates the database, so asking the question
    the obvious way would answer it wrongly and leave a file behind.
    """
    target = Path(db) if db else DB_PATH
    if not target.exists():
        return True
    conn = connect(target)
    try:
        return conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0] == 0
    finally:
        conn.close()


def purge(source: Optional[str] = None, db: Optional[Path] = None) -> Dict[str, Any]:
    """Delete indexed content. With no source, empties the whole index."""
    if source:
        return remove_source(source, db=db)
    conn = connect(db)
    try:
        docs = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        chunks = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        srcs = conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0]
        table = _store_table(text_store(conn))
        conn.execute(f"DELETE FROM {table}")
        conn.execute("DELETE FROM doc_links")
        conn.execute("DELETE FROM chunks")
        conn.execute("DELETE FROM documents")
        conn.execute("DELETE FROM sources")
        conn.commit()
        conn.execute("VACUUM")
        return {"label": None, "root": "(everything)",
                "documents": docs, "chunks": chunks, "sources": srcs}
    finally:
        conn.close()


# ---------------------------------------------------------------- content graph

# Link discovery thresholds, expressed as document frequency rather than IDF.
# IDF is corpus-size dependent — on a five-file folder a phrase shared by two
# documents scores 0.6, below any fixed floor, so an IDF gate finds no links at
# all in exactly the case a personal index starts from. Document frequency says
# the same thing scale-free: a phrase in one document cannot connect anything,
# and a phrase in most of them is vocabulary rather than subject matter.
_LINK_MAX_DF_RATIO = 0.5
_LINK_MAX_DF_ABS = 200      # keeps the per-phrase pair loop from exploding
_LINK_EVIDENCE = 6

# Link strength floor. Lower than the flow mapper's 0.45 because these scores
# normalise against a folder rather than a whole tenant: a handful of personal
# files share less vocabulary mass than a company corpus does.
DEFAULT_LINK_MIN_SCORE = 0.3

# Neighbours kept per document. Measured on a real 1,350-document folder, a
# bare threshold produced 52,631 links — a median of 34 neighbours each and a
# worst case of 292, with 60% of them sitting within 0.05 of the threshold. A
# threshold alone cannot fix that: raising it enough to thin the noise also
# drops genuine links between short documents. Keeping each document's
# strongest few is what makes the graph navigable, and a link survives if
# either endpoint ranks it, so an asymmetric relationship is not lost.
DEFAULT_LINK_TOP_K = 10

# Absolute ceiling on phrases per document, as a guard against one enormous file
# dominating comparison cost. Set high enough that it effectively never binds;
# the real trimming is by document frequency in _prepare.
#
# It is applied with a deterministic total order — (-idf, phrase) — and that
# detail is load-bearing. Ranking by IDF alone leaves every equally-rare phrase
# tied, and sorting a *set* breaks ties in iteration order, which differs per
# document. Two near-duplicate files then keep disjoint slices of the very
# phrases that connect them: measured on two real 20 KB decks sharing 1,495
# phrases, a rank-only prune to 400 left them sharing none, and the strongest
# link in the corpus scored 0.0.
_LINK_MAX_PHRASES = 3000


def _bigrams(tokens: Sequence[str]) -> List[str]:
    return [f"{a} {b}" for a, b in zip(tokens, tokens[1:])]


def _link_corpus(conn: sqlite3.Connection, max_chars: int) -> List[Dict[str, Any]]:
    """Per-document phrase sets, built from the title and leading chunk text."""
    table = _store_table(text_store(conn))
    rows = conn.execute(f"""
        SELECT d.id, d.doc_id, d.title,
               GROUP_CONCAT(SUBSTR({table}.text, 1, 4000), ' ') AS body
          FROM documents d
          JOIN chunks c ON c.document_id = d.id
          JOIN {table} ON {table}.rowid = c.id
         GROUP BY d.id
    """).fetchall()
    corpus: List[Dict[str, Any]] = []
    for row in rows:
        title_toks = _tokens(row["title"] or "")
        body_toks = _tokens((row["body"] or "")[:max_chars])
        toks = set(title_toks) | set(body_toks)
        corpus.append({
            "id": row["id"],
            "doc_id": row["doc_id"],
            "title": row["title"],
            "title_toks": set(title_toks),
            "toks": toks,
            "phrases": toks | set(_bigrams(title_toks + body_toks)),
        })
    return corpus


def _document_frequency(corpus: Sequence[Dict[str, Any]]) -> Counter:
    df: Counter = Counter()
    for doc in corpus:
        for phrase in doc["phrases"]:
            df[phrase] += 1
    return df


def _idf(corpus: Sequence[Dict[str, Any]],
         df: Optional[Counter] = None) -> Dict[str, float]:
    """Rarity weight per phrase, used for scoring and evidence ranking only.

    Smoothed — log((n + 1) / (df + 0.5)) — rather than the simpler 1 - df/n.
    That form goes to exactly zero for any phrase present in every document,
    which on a two-document index is *every shared phrase*, so no pair could
    ever score above zero and nothing would ever link. Smoothing keeps the
    rarity ordering while staying strictly positive at any corpus size.
    """
    n = max(1, len(corpus))
    df = df if df is not None else _document_frequency(corpus)
    return {phrase: math.log((n + 1.0) / (count + 0.5))
            for phrase, count in df.items()}


def _df_cap(n: int) -> int:
    """Highest document frequency a phrase may have and still carry signal."""
    return min(_LINK_MAX_DF_ABS, max(2, int(n * _LINK_MAX_DF_RATIO)))


def _candidate_pairs(corpus: Sequence[Dict[str, Any]],
                     idf: Dict[str, float]) -> Dict[Tuple[int, int], None]:
    """Pairs sharing at least one discriminating phrase.

    Comparing every pair is quadratic, which a folder of several thousand files
    makes untenable. An inverted index over selective phrases only keeps the
    comparison set to documents that could plausibly link.
    """
    n = max(1, len(corpus))
    by_phrase: Dict[str, List[int]] = defaultdict(list)
    for i, doc in enumerate(corpus):
        for phrase in doc["phrases"]:
            by_phrase[phrase].append(i)
    pairs: Dict[Tuple[int, int], None] = {}
    cap = _df_cap(n)
    for holders in by_phrase.values():
        if len(holders) < 2 or len(holders) > cap:
            continue
        for a_i in range(len(holders)):
            for b_i in range(a_i + 1, len(holders)):
                pairs[(holders[a_i], holders[b_i])] = None
    return pairs


def _prepare(corpus: Sequence[Dict[str, Any]], idf: Dict[str, float],
             df: Counter) -> None:
    """Drop uninformative phrases and cache each document's IDF mass.

    Trimming is by document frequency, which is a property of the phrase rather
    than of the document holding it — so a phrase is kept by both ends of a pair
    or by neither, and pruning can never delete the overlap that would have
    linked them. A per-document rank cut cannot promise that (see
    _LINK_MAX_PHRASES).

    Caching the mass is pure performance: it was previously recomputed inside
    every pair comparison, summing the same few thousand floats once per pair.
    """
    cap = _df_cap(len(corpus))
    for doc in corpus:
        phrases = {p for p in doc["phrases"] if df.get(p, 0) <= cap}
        if len(phrases) > _LINK_MAX_PHRASES:
            # Deterministic total order, so this stays symmetric across docs.
            phrases = set(sorted(phrases, key=lambda p: (-idf.get(p, 0.0), p))
                          [:_LINK_MAX_PHRASES])
        doc["phrases"] = phrases
        doc["mass"] = sum(idf.get(p, 0.0) for p in phrases) or 1.0


def _pair_score(a: Dict[str, Any], b: Dict[str, Any],
                idf: Dict[str, float]) -> Tuple[float, List[str]]:
    shared = a["phrases"] & b["phrases"]
    if not shared:
        return 0.0, []
    weight = sum(idf.get(p, 0.0) * (2.0 if " " in p else 1.0) for p in shared)
    score = weight / math.sqrt(a["mass"] * b["mass"])
    # Two documents whose titles share a rare word are about the same thing far
    # more often than two that merely share body vocabulary.
    title_shared = a["title_toks"] & b["title_toks"]
    score += 0.25 * sum(idf.get(t, 0.0) for t in title_shared)
    evidence = sorted(shared, key=lambda p: -idf.get(p, 0.0))[:_LINK_EVIDENCE]
    return min(1.0, score), evidence


def link_documents(min_score: float = DEFAULT_LINK_MIN_SCORE,
                   db: Optional[Path] = None,
                   max_chars: int = 20_000,
                   top_k: int = DEFAULT_LINK_TOP_K,
                   progress: Optional[Any] = None) -> int:
    """Rebuild the document-to-document graph. Returns the number of links.

    Two stages: score every candidate pair above the threshold, then keep each
    document's `top_k` strongest neighbours. A link is kept when either endpoint
    ranks it, so a hub document does not monopolise the graph and a small
    document's single best link is never crowded out.
    """
    conn = connect(db)
    try:
        corpus = _link_corpus(conn, max_chars)
        conn.execute("DELETE FROM doc_links")
        if len(corpus) < 2:
            conn.commit()
            return 0
        if progress:
            progress(f"scoring {len(corpus)} documents")
        df = _document_frequency(corpus)
        idf = _idf(corpus, df)
        _prepare(corpus, idf, df)

        pairs = _candidate_pairs(corpus, idf)
        if progress:
            progress(f"comparing {len(pairs):,} candidate pairs")

        scored: List[Tuple[float, int, int, List[str]]] = []
        for n, (a_i, b_i) in enumerate(pairs):
            a, b = corpus[a_i], corpus[b_i]
            score, evidence = _pair_score(a, b, idf)
            if score >= min_score:
                scored.append((score, a["id"], b["id"], evidence))
            if progress and pairs and n and n % 100_000 == 0:
                progress(f"  {100 * n // len(pairs)}%")

        keep = _top_k_links(scored, top_k)
        if progress:
            progress(f"keeping {len(keep):,} of {len(scored):,} scored links")
        conn.executemany(
            "INSERT OR REPLACE INTO doc_links (a_doc, b_doc, kind, score, evidence) "
            "VALUES (?,?,?,?,?)",
            [(min(a, b), max(a, b), "phrase", round(score, 4), json.dumps(evidence))
             for score, a, b, evidence in keep])
        conn.commit()
        return len(keep)
    finally:
        conn.close()


def _top_k_links(scored: Sequence[Tuple[float, int, int, List[str]]],
                 top_k: int) -> List[Tuple[float, int, int, List[str]]]:
    """Keep each document's strongest `top_k` neighbours, union across both ends."""
    if top_k <= 0:
        return list(scored)
    by_doc: Dict[int, List[int]] = defaultdict(list)
    for index, (_score, a, b, _ev) in enumerate(scored):
        by_doc[a].append(index)
        by_doc[b].append(index)
    keep: set = set()
    for indices in by_doc.values():
        indices.sort(key=lambda i: -scored[i][0])
        keep.update(indices[:top_k])
    return [scored[i] for i in sorted(keep, key=lambda i: -scored[i][0])]


def related(ref: str, limit: int = 8, db: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Documents linked to this one, strongest first."""
    conn = connect(db)
    try:
        row = _resolve_doc(conn, ref)
        if not row:
            raise PersonalError(
                f"No indexed document matching '{ref}'. See /personal sources.")
        rows = conn.execute("""
            SELECT d.doc_id, d.title, d.rel_path, d.abs_path, s.label,
                   l.score, l.evidence, l.kind
              FROM doc_links l
              JOIN documents d ON d.id = CASE WHEN l.a_doc = :id THEN l.b_doc ELSE l.a_doc END
              JOIN sources s ON s.id = d.source_id
             WHERE l.a_doc = :id OR l.b_doc = :id
             ORDER BY l.score DESC LIMIT :limit
        """, {"id": row["id"], "limit": max(1, int(limit))}).fetchall()
        out = []
        for r in rows:
            item = dict(r)
            try:
                item["evidence"] = json.loads(r["evidence"] or "[]")
            except ValueError:
                item["evidence"] = []
            item["url"] = _file_url(r["abs_path"])
            out.append(item)
        return out
    finally:
        conn.close()


# ---------------------------------------------------------------- Glean shapes
#
# The REPL's renderers and the MCP server already speak the Client API's
# response shapes. Emitting the same shapes here means `/search` and `/chat`
# work against a local index with no change to any rendering code — the same
# trick that lets mock mode reuse every handler.

def _ago(ts: Optional[float]) -> str:
    if not ts:
        return ""
    days = max(0, int((time.time() - float(ts)) // 86400))
    if days == 0:
        return "today"
    if days == 1:
        return "yesterday"
    if days < 30:
        return f"{days} days ago"
    if days < 365:
        months = days // 30
        return f"{months} month{'s' if months != 1 else ''} ago"
    years = days // 365
    return f"{years} year{'s' if years != 1 else ''} ago"


_EXT_LABEL = {
    ".md": "Markdown", ".markdown": "Markdown", ".txt": "Text",
    ".html": "Web page", ".htm": "Web page", ".json": "JSON",
    ".docx": "Word document", ".xlsx": "Spreadsheet", ".pptx": "Presentation",
}


def _metadata(hit: Dict[str, Any]) -> Dict[str, Any]:
    container = str(Path(hit.get("rel_path", "")).parent)
    return {
        "datasource": hit.get("datasource", DEFAULT_LABEL),
        "documentType": _EXT_LABEL.get(hit.get("ext", ""), "File"),
        "container": "" if container in (".", "") else container,
        "updateTime": int(float(hit.get("mtime") or 0)),
        "updatedAgo": _ago(hit.get("mtime")),
        "localPath": hit.get("abs_path", ""),
    }


def as_result(hit: Dict[str, Any], explain: bool = False) -> Dict[str, Any]:
    """One local hit in /search result shape.

    With explain, an extra `explain` key carries the ranking evidence. It sits
    outside the Client API shape deliberately: the default result must stay
    byte-compatible with what Glean returns, because that compatibility is what
    lets one renderer draw local and remote hits alike.
    """
    result = {
        "id": hit["doc_id"],
        "title": hit["title"],
        "url": hit["url"],
        "datasource": hit.get("datasource", DEFAULT_LABEL),
        "snippets": [{"text": hit.get("snippet", "")}],
        "trackingToken": f"local_{hit['doc_id']}",
        "metadata": _metadata(hit),
    }
    if explain:
        matched = hit.get("matched_terms") or []
        result["explain"] = {
            "score": hit.get("score"),
            "heading": hit.get("heading"),
            "matched_chunks": hit.get("matched_chunks"),
            "total_chunks": hit.get("total_chunks"),
            "matched_terms": matched,
            "missed_terms": [t for t in (hit.get("query_terms") or [])
                             if t not in matched],
        }
    return result


def as_document(doc: Dict[str, Any]) -> Dict[str, Any]:
    """One local document in /getdocuments shape."""
    return {
        "id": doc["doc_id"],
        "title": doc["title"],
        "url": doc["url"],
        "datasource": doc.get("datasource", DEFAULT_LABEL),
        "metadata": _metadata(doc),
    }


def search_response(query: str, page_size: int = 10,
                    datasource: Optional[str] = None,
                    facets: bool = False,
                    explain: bool = False,
                    db: Optional[Path] = None) -> Dict[str, Any]:
    hits = search(query, limit=page_size, source=datasource, db=db)
    results = [as_result(h, explain=explain) for h in hits]
    if explain and results:
        # Rank and tie group are properties of the result set, not of one hit.
        groups = tie_groups([h.get("score") or 0.0 for h in hits])
        top = max((h.get("score") or 0.0) for h in hits) or 1.0
        for rank, (result, group) in enumerate(zip(results, groups), 1):
            result["explain"]["rank"] = rank
            result["explain"]["tie_group"] = group
            result["explain"]["tied_with"] = [
                r + 1 for r, g in enumerate(groups) if g == group and r != rank - 1]
            result["explain"]["score_ratio"] = round(
                (result["explain"]["score"] or 0.0) / top, 4)
    resp: Dict[str, Any] = {
        "results": results,
        "totalCount": len(hits),
        "localIndex": True,
    }
    if facets:
        resp["facetResults"] = [{"sourceName": "datasource",
                                 "buckets": facet_buckets(datasource, db=db)}]
    return resp


def facet_buckets(datasource: Optional[str] = None,
                  db: Optional[Path] = None) -> List[Dict[str, Any]]:
    return [{"value": s["label"], "count": s["documents"]}
            for s in sources(db=db)
            if not datasource or s["label"] == datasource]


def chat_response(message: str, chat_id: Optional[str] = None,
                  limit: int = 5, db: Optional[Path] = None) -> Dict[str, Any]:
    """An extractive answer: the passages that match, never generated prose.

    Nothing here writes an answer, because there is no model in this process
    and inventing one would be the single worst thing a local index could do.
    An agent reading this over MCP has a model of its own and can synthesise
    from the passages; a human reads them directly.
    """
    hits = search(message, limit=limit, db=db)
    if not hits:
        text = (f"{LOCAL_BANNER}\n\nNothing in the local index matches "
                f"“{message}”. Index a folder with "
                f"/personal index <folder>, or check /personal sources.")
        citations: List[Dict[str, Any]] = []
    else:
        lines = [LOCAL_BANNER, "",
                 f"{len(hits)} passage{'s' if len(hits) != 1 else ''} matching "
                 f"“{message}”. These are extracted verbatim — "
                 f"no answer has been generated from them.", ""]
        for i, hit in enumerate(hits, 1):
            where = f" › {hit['heading']}" if hit.get("heading") else ""
            lines.append(f"{i}. {hit['title']}{where}  ({hit['datasource']})")
            lines.append(f"   {hit['snippet']}")
            lines.append("")
        text = "\n".join(lines).rstrip()
        citations = [{"sourceDocument": {
            "id": h["doc_id"], "title": h["title"],
            "url": h["url"], "datasource": h["datasource"],
        }} for h in hits]
    return {
        "chatId": chat_id or f"local_{int(time.time())}",
        "messages": [{
            "author": "GLEAN_AI",
            "messageType": "CONTENT",
            "fragments": [{"text": text}],
            "citations": citations,
        }],
        "localIndex": True,
    }


def documents_response(body: Dict[str, Any], db: Optional[Path] = None) -> Dict[str, Any]:
    """/getdocuments over the local index, keyed by id or url."""
    specs = body.get("documentSpecs") or []
    if not specs:
        for key in ("ids", "documentIds"):
            specs = [{"id": i} for i in (body.get(key) or [])] or specs
        for url in (body.get("urls") or []):
            specs.append({"url": url})
    # A list, matching the Client API and the mock. A map here meant
    # flow.enrich iterated dict keys and silently enriched nothing.
    out: List[Dict[str, Any]] = []
    for spec in specs:
        ref = ""
        if isinstance(spec, dict):
            ref = spec.get("id") or spec.get("documentId") or spec.get("url") or ""
        elif isinstance(spec, str):
            ref = spec
        if not ref:
            continue
        doc = fetch(ref, db=db)
        if doc:
            shaped = as_document(doc)
            shaped["content"] = doc["text"]
            shaped["requestedRef"] = ref
            out.append(shaped)
    return {"documents": out, "localIndex": True}


def autocomplete_response(query: str, db: Optional[Path] = None) -> Dict[str, Any]:
    """Completions drawn from indexed titles and headings."""
    query = (query or "").strip().lower()
    seen: List[str] = []
    for hit in search(query or "*", limit=8, db=db):
        for candidate in (hit["title"], hit.get("heading") or ""):
            candidate = (candidate or "").strip()
            if candidate and candidate.lower() != query and candidate not in seen:
                seen.append(candidate)
    # The Client API (and the mock, and cmd_autocomplete) read `suggestion`.
    # Emitting `text` here rendered "(no suggestions)" despite real matches.
    return {"results": [{"suggestion": t} for t in seen[:6]], "localIndex": True}
