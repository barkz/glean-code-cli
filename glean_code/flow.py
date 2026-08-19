"""Flow mapper — local capture, enrichment, and link discovery.

Every Client API call the CLI makes passes through one funnel
(`GleanClient._post`), so a single hook there records what you asked and what
came back. Chat turns, their citations, and search results land in a local
SQLite database; documents are enriched with real text; and a linker connects
related material — both document-to-document and across chat sessions that
never shared any context.

The interesting case is the indirect one. Two unrelated investigations — a
checkout incident and a customer renewal — connect because a QBR document
mentions the incident in passing, with no ticket number to join on.

Design notes worth keeping in view:

  * Rows are tagged with instance, mode, and act_as. Fictional mock content
    must never link to a real tenant's documents, and one person's
    impersonated view must never link to another's.
  * Capture defaults to mock only. In live mode this file becomes a copy of
    company content with the permission model stripped off, so turning it on
    there is a deliberate act with a retention policy attached.
  * sqlite3 is in the standard library, so the zero-dependency rule holds.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .config import CONFIG_DIR

DB_PATH = CONFIG_DIR / "flow.db"

# Capture modes for the `flow_capture` config key.
CAPTURE_MODES = ("mock", "on", "off")
DEFAULT_CAPTURE = "mock"

SCHEMA_VERSION = 2

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
CREATE TABLE IF NOT EXISTS sessions (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id    TEXT,
    instance   TEXT NOT NULL,
    mode       TEXT NOT NULL,
    act_as     TEXT,
    started_at REAL NOT NULL,
    ended_at   REAL
);
CREATE TABLE IF NOT EXISTS turns (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    role       TEXT NOT NULL,
    text       TEXT NOT NULL,
    endpoint   TEXT NOT NULL,
    ts         REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS documents (
    doc_id         TEXT NOT NULL,
    instance       TEXT NOT NULL,
    mode           TEXT NOT NULL,
    title          TEXT,
    url            TEXT,
    datasource     TEXT,
    author         TEXT,
    updated_at     REAL,
    content        TEXT,
    content_source TEXT,
    fetched_at     REAL,
    PRIMARY KEY (doc_id, instance, mode)
);
CREATE TABLE IF NOT EXISTS citations (
    turn_id INTEGER NOT NULL REFERENCES turns(id) ON DELETE CASCADE,
    doc_id  TEXT NOT NULL,
    rank    INTEGER NOT NULL,
    PRIMARY KEY (turn_id, doc_id)
);
CREATE TABLE IF NOT EXISTS doc_links (
    a_doc    TEXT NOT NULL,
    b_doc    TEXT NOT NULL,
    instance TEXT NOT NULL,
    mode     TEXT NOT NULL,
    kind     TEXT NOT NULL,
    score    REAL NOT NULL,
    evidence TEXT,
    PRIMARY KEY (a_doc, b_doc, instance, mode, kind)
);
CREATE TABLE IF NOT EXISTS session_links (
    a_session INTEGER NOT NULL,
    b_session INTEGER NOT NULL,
    kind      TEXT NOT NULL,
    score     REAL NOT NULL,
    via_doc   TEXT,
    to_doc    TEXT,
    evidence  TEXT,
    PRIMARY KEY (a_session, b_session, kind, via_doc)
);
CREATE INDEX IF NOT EXISTS idx_turns_session ON turns(session_id);
CREATE INDEX IF NOT EXISTS idx_citations_doc ON citations(doc_id);
"""


class FlowError(Exception):
    """Anything the user needs to be told about, phrased for a terminal."""


# ---------------------------------------------------------------- connection


def connect(path: Optional[Path] = None) -> sqlite3.Connection:
    """Open (creating if needed) the flow database with 0600 permissions."""
    target = Path(path) if path else DB_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    fresh = not target.exists()
    conn = sqlite3.connect(str(target))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(_SCHEMA)
    _migrate(conn)
    conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('schema_version', ?)",
                 (str(SCHEMA_VERSION),))
    conn.commit()
    if fresh:
        try:
            os.chmod(target, 0o600)
        except OSError:
            pass
    return conn


def _migrate(conn: sqlite3.Connection) -> None:
    """Add columns to tables that already exist.

    `CREATE TABLE IF NOT EXISTS` is a no-op on an existing table, so a new
    column never reaches a database written by an earlier version. Each entry
    is additive and idempotent; nothing here drops or rewrites data.
    """
    added = {
        "session_links": {"to_doc": "TEXT"},   # v2: the far end of the bridge
    }
    for table, columns in added.items():
        try:
            have = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
        except sqlite3.Error:
            continue
        for name, decl in columns.items():
            if name not in have:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")


def db_size(path: Optional[Path] = None) -> int:
    target = Path(path) if path else DB_PATH
    try:
        return target.stat().st_size
    except OSError:
        return 0


# ---------------------------------------------------------------- capture


def capture_enabled(capture_setting: str, mode: str) -> bool:
    """Should this call be recorded?

    'mock' — the default — records only fictional corpus traffic, so the
    database never accumulates real tenant content by accident.
    """
    if capture_setting == "off":
        return False
    if capture_setting == "on":
        return True
    return mode == "mock"


def _partition(config) -> Tuple[str, str, Optional[str]]:
    instance = (getattr(config, "instance", None) or "local").strip()
    return instance, config.effective_mode, getattr(config, "act_as", None)


def _session_for(conn, chat_id, instance, mode, act_as, ts) -> int:
    """Find the session for a chat id, or open one. Threading is exact.

    /chat echoes chatId back, so turns of one conversation share a key and
    need no time-proximity guessing. Non-chat traffic attaches to the most
    recent session in the same partition within the proximity window.
    """
    if chat_id:
        row = conn.execute(
            "SELECT id FROM sessions WHERE chat_id = ? AND instance = ? AND mode = ?"
            " AND IFNULL(act_as,'') = IFNULL(?,'')",
            (chat_id, instance, mode, act_as),
        ).fetchone()
        if row:
            return int(row["id"])
    cur = conn.execute(
        "INSERT INTO sessions (chat_id, instance, mode, act_as, started_at)"
        " VALUES (?, ?, ?, ?, ?)",
        (chat_id, instance, mode, act_as, ts),
    )
    return int(cur.lastrowid)


def _recent_session(conn, instance, mode, act_as, ts, window: float) -> Optional[int]:
    row = conn.execute(
        "SELECT s.id, MAX(t.ts) AS last_ts FROM sessions s JOIN turns t ON t.session_id = s.id"
        " WHERE s.instance = ? AND s.mode = ? AND IFNULL(s.act_as,'') = IFNULL(?,'')"
        " GROUP BY s.id ORDER BY last_ts DESC LIMIT 1",
        (instance, mode, act_as),
    ).fetchone()
    if row and row["last_ts"] is not None and (ts - float(row["last_ts"])) <= window:
        return int(row["id"])
    return None


def _upsert_document(conn, doc: Dict[str, Any], instance: str, mode: str) -> None:
    md = doc.get("metadata") or {}
    author = md.get("author")
    if isinstance(author, dict):
        author = author.get("name") or author.get("email")
    conn.execute(
        "INSERT INTO documents (doc_id, instance, mode, title, url, datasource,"
        " author, updated_at, content, content_source, fetched_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL)"
        " ON CONFLICT(doc_id, instance, mode) DO UPDATE SET"
        "   title = COALESCE(excluded.title, title),"
        "   url = COALESCE(excluded.url, url),"
        "   datasource = COALESCE(excluded.datasource, datasource),"
        "   author = COALESCE(excluded.author, author),"
        "   updated_at = COALESCE(excluded.updated_at, updated_at)",
        (doc.get("id") or doc.get("url"), instance, mode, doc.get("title"),
         doc.get("url"), doc.get("datasource"), author, md.get("updateTime")),
    )


def record(config, path: str, body: Dict[str, Any], response: Dict[str, Any],
           db: Optional[Path] = None, proximity_window: float = 600.0) -> None:
    """Record one API exchange. Never raises — capture must not break a call."""
    try:
        _record(config, path, body, response, db, proximity_window)
    except Exception:  # noqa: BLE001 - a capture bug must not fail the user's command
        pass


def _record(config, path, body, response, db, proximity_window) -> None:
    if path not in ("/chat", "/search"):
        return
    instance, mode, act_as = _partition(config)
    ts = time.time()
    conn = connect(db)
    try:
        if path == "/chat":
            chat_id = response.get("chatId") or body.get("chatId")
            session_id = _session_for(conn, chat_id, instance, mode, act_as, ts)
            question = ""
            msgs = body.get("messages") or []
            if msgs:
                frags = msgs[-1].get("fragments") or []
                question = "".join(f.get("text", "") for f in frags)
            if question:
                conn.execute(
                    "INSERT INTO turns (session_id, role, text, endpoint, ts)"
                    " VALUES (?, 'user', ?, ?, ?)",
                    (session_id, question, path, ts),
                )
            for msg in response.get("messages") or []:
                text = "".join(f.get("text", "") for f in (msg.get("fragments") or []))
                cur = conn.execute(
                    "INSERT INTO turns (session_id, role, text, endpoint, ts)"
                    " VALUES (?, 'assistant', ?, ?, ?)",
                    (session_id, text, path, ts),
                )
                turn_id = int(cur.lastrowid)
                for rank, cite in enumerate(msg.get("citations") or []):
                    doc = cite.get("sourceDocument") or {}
                    doc_id = doc.get("id") or doc.get("url")
                    if not doc_id:
                        continue
                    _upsert_document(conn, doc, instance, mode)
                    conn.execute(
                        "INSERT OR IGNORE INTO citations (turn_id, doc_id, rank)"
                        " VALUES (?, ?, ?)", (turn_id, doc_id, rank),
                    )
        else:  # /search
            session_id = _recent_session(conn, instance, mode, act_as, ts, proximity_window)
            if session_id is None:
                session_id = _session_for(conn, None, instance, mode, act_as, ts)
            query = body.get("query") or ""
            cur = conn.execute(
                "INSERT INTO turns (session_id, role, text, endpoint, ts)"
                " VALUES (?, 'search', ?, ?, ?)", (session_id, query, path, ts),
            )
            turn_id = int(cur.lastrowid)
            for rank, res in enumerate(response.get("results") or []):
                doc_id = res.get("id") or res.get("url")
                if not doc_id:
                    continue
                _upsert_document(conn, res, instance, mode)
                snips = res.get("snippets") or []
                if snips:
                    conn.execute(
                        "UPDATE documents SET content = COALESCE(content, ?),"
                        " content_source = COALESCE(content_source, 'search-snippet'),"
                        " fetched_at = COALESCE(fetched_at, ?)"
                        " WHERE doc_id = ? AND instance = ? AND mode = ?",
                        (snips[0].get("text", ""), ts, doc_id, instance, mode),
                    )
                conn.execute(
                    "INSERT OR IGNORE INTO citations (turn_id, doc_id, rank)"
                    " VALUES (?, ?, ?)", (turn_id, doc_id, rank),
                )
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------- enrichment


def documents_needing_content(conn, instance: str, mode: str,
                              limit: int = 50) -> List[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM documents WHERE instance = ? AND mode = ?"
        "   AND (content IS NULL OR content = '')"
        " ORDER BY fetched_at IS NOT NULL, doc_id LIMIT ?",
        (instance, mode, limit),
    ).fetchall()


def enrich(client, config, db: Optional[Path] = None,
           limit: int = 50) -> Tuple[int, int]:
    """Fill in document text for captured citations.

    Tries /getdocuments first (real content when the API returns it) and falls
    back to /summarize, which yields a usable extract in both modes. Returns
    (enriched, attempted).
    """
    instance, mode, _ = _partition(config)
    conn = connect(db)
    enriched = 0
    try:
        rows = documents_needing_content(conn, instance, mode, limit)
        for row in rows:
            text, source = _fetch_content(client, row)
            if not text:
                continue
            conn.execute(
                "UPDATE documents SET content = ?, content_source = ?, fetched_at = ?"
                " WHERE doc_id = ? AND instance = ? AND mode = ?",
                (text, source, time.time(), row["doc_id"], instance, mode),
            )
            enriched += 1
        conn.commit()
        return enriched, len(rows)
    finally:
        conn.close()


def _fetch_content(client, row) -> Tuple[Optional[str], Optional[str]]:
    spec: Dict[str, Any] = {}
    if row["url"]:
        spec["url"] = row["url"]
    elif row["doc_id"]:
        spec["id"] = row["doc_id"]
    if not spec:
        return None, None

    try:
        resp = client.get_documents(
            ids=[spec["id"]] if "id" in spec else None,
            urls=[spec["url"]] if "url" in spec else None,
        )
        for doc in resp.get("documents") or []:
            body = doc.get("body")
            if isinstance(body, dict):
                body = body.get("textContent") or body.get("text")
            text = body or doc.get("content") or doc.get("text")
            if text:
                return str(text), "getdocuments"
    except Exception:  # noqa: BLE001 - fall through to summarize
        pass

    try:
        resp = client.summarize(**spec)
        summary = resp.get("summary")
        if summary:
            return str(summary), "summarize"
    except Exception:  # noqa: BLE001 - nothing else to try
        pass
    return None, None


# ---------------------------------------------------------------- linking

# Ticket keys and repo references are the highest-precision signal available.
_ID_RE = re.compile(r"\b(?:INC|PLAT|PLAN|SEC|SUP|REV|PAY)-\d+\b|\b[\w.-]+/[\w.-]+#\d+\b")

_STOPWORDS = frozenset("""
a an and are as at be by do does for from has have how i in is it its of on or our
the their there this to us was we what when where which who why will with you your
be been being if then than that these those they them he she his her not no yes but
can could should would may might must about into over under after before during more
most some any each every other another such only just also very much many few both
""".split())

_WORD_RE = re.compile(r"[a-z0-9][a-z0-9'-]*")


def _tokens(text: str) -> List[str]:
    return [w for w in _WORD_RE.findall((text or "").lower())
            if w not in _STOPWORDS and len(w) > 2]


def _bigrams(tokens: Sequence[str]) -> List[str]:
    return [f"{a} {b}" for a, b in zip(tokens, tokens[1:])]


def build_idf(docs: Sequence[sqlite3.Row]) -> Dict[str, float]:
    """Rarity weight per phrase. A phrase in most documents carries no signal."""
    n = max(1, len(docs))
    seen: Counter = Counter()
    for d in docs:
        text = f"{d['title'] or ''} {d['content'] or ''}"
        toks = _tokens(text)
        for phrase in set(toks) | set(_bigrams(toks)):
            seen[phrase] += 1
    # A plain ratio is enough here and keeps the maths readable.
    return {p: 1.0 - (c / n) for p, c in seen.items()}


def _identifiers(row) -> set:
    return set(_ID_RE.findall(f"{row['title'] or ''} {row['content'] or ''}"))


def _doc_parts(row) -> Tuple[set, set, set]:
    """(title words, all words, bigrams) for one document."""
    title = row["title"] or ""
    all_toks = _tokens(f"{title} {row['content'] or ''}")
    return set(_tokens(title)), set(all_toks), set(_bigrams(all_toks))


def link_documents(db: Optional[Path] = None, instance: str = "", mode: str = "",
                   min_score: float = 0.45, max_phrases: int = 3) -> int:
    """Discover document-to-document links. Returns the number written.

    Three tiers, each storing its evidence so a link can be explained rather
    than asserted:

      identifier — a shared ticket key or repo reference. Exact.
      phrase     — a shared bigram, or a word from one document's *title*
                   appearing in the other's text. The title anchor is what
                   makes this precise: rarity alone promotes accidents, since
                   in a small corpus a word used once anywhere scores higher
                   than a meaningful word used four times. A title is a
                   curated label, so prose echoing one is a real reference —
                   this is what connects a QBR saying "the checkout incident
                   in June" to a postmortem titled "Checkout Latency Incident"
                   with no ticket number shared between them.
    """
    conn = connect(db)
    written = 0
    try:
        docs = conn.execute(
            "SELECT * FROM documents WHERE instance = ? AND mode = ?"
            "   AND content IS NOT NULL AND content != ''",
            (instance, mode),
        ).fetchall()
        if len(docs) < 2:
            return 0

        idf = build_idf(docs)
        ids = {d["doc_id"]: _identifiers(d) for d in docs}
        parts = {d["doc_id"]: _doc_parts(d) for d in docs}

        conn.execute("DELETE FROM doc_links WHERE instance = ? AND mode = ?",
                     (instance, mode))
        for i, a in enumerate(docs):
            for b in docs[i + 1:]:
                a_id, b_id = a["doc_id"], b["doc_id"]

                shared_ids = ids[a_id] & ids[b_id]
                if shared_ids:
                    written += _write_link(conn, a_id, b_id, instance, mode,
                                           "identifier", 1.0,
                                           ", ".join(sorted(shared_ids)))
                    continue

                a_title, a_words, a_grams = parts[a_id]
                b_title, b_words, b_grams = parts[b_id]
                scored: Dict[str, float] = {}
                for g in a_grams & b_grams:              # a shared phrase
                    scored[g] = idf.get(g, 0.0)
                for w in (a_words & b_title) | (b_words & a_title):
                    scored[w] = max(scored.get(w, 0.0), idf.get(w, 0.0) * 0.9)
                if not scored:
                    continue

                ranked = sorted(scored, key=lambda p: -scored[p])[:max_phrases]
                score = sum(scored[p] for p in ranked) / len(ranked)
                if score >= min_score:
                    written += _write_link(conn, a_id, b_id, instance, mode,
                                           "phrase", round(score, 3),
                                           ", ".join(ranked))
        conn.commit()
        return written
    finally:
        conn.close()


def _write_link(conn, a, b, instance, mode, kind, score, evidence) -> int:
    lo, hi = sorted((a, b))
    conn.execute(
        "INSERT OR REPLACE INTO doc_links (a_doc, b_doc, instance, mode, kind, score, evidence)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)", (lo, hi, instance, mode, kind, score, evidence),
    )
    return 1


def link_sessions(db: Optional[Path] = None, instance: str = "", mode: str = "") -> int:
    """Connect sessions that never shared context.

    'shared-citation' — both sessions cited the same document.
    'linked-document' — a document cited by one session links to a document
                        cited by the other. This is the indirect case: two
                        investigations connected only because a document
                        mentions the other's subject in passing.
    """
    conn = connect(db)
    written = 0
    try:
        rows = conn.execute(
            "SELECT s.id AS sid, c.doc_id AS doc_id FROM sessions s"
            " JOIN turns t ON t.session_id = s.id JOIN citations c ON c.turn_id = t.id"
            " WHERE s.instance = ? AND s.mode = ?", (instance, mode),
        ).fetchall()
        by_session: Dict[int, set] = defaultdict(set)
        for r in rows:
            by_session[int(r["sid"])].add(r["doc_id"])

        links = conn.execute(
            "SELECT a_doc, b_doc, kind, score, evidence FROM doc_links"
            " WHERE instance = ? AND mode = ?", (instance, mode),
        ).fetchall()
        link_map: Dict[str, List[sqlite3.Row]] = defaultdict(list)
        for l in links:
            link_map[l["a_doc"]].append(l)
            link_map[l["b_doc"]].append(l)

        conn.execute("DELETE FROM session_links")
        sids = sorted(by_session)
        for i, a in enumerate(sids):
            for b in sids[i + 1:]:
                shared = by_session[a] & by_session[b]
                if shared:
                    doc = sorted(shared)[0]
                    conn.execute(
                        "INSERT OR REPLACE INTO session_links"
                        " (a_session, b_session, kind, score, via_doc, to_doc, evidence)"
                        " VALUES (?, ?, 'shared-citation', 1.0, ?, ?, ?)",
                        (a, b, doc, doc, f"both sessions cited {doc}"),
                    )
                    written += 1
                    continue
                best = None
                for doc_a in by_session[a]:
                    for l in link_map.get(doc_a, []):
                        other = l["b_doc"] if l["a_doc"] == doc_a else l["a_doc"]
                        if other in by_session[b]:
                            cand = (float(l["score"]), doc_a, other, l["kind"], l["evidence"])
                            if best is None or cand[0] > best[0]:
                                best = cand
                if best:
                    score, doc_a, other, kind, evidence = best
                    conn.execute(
                        "INSERT OR REPLACE INTO session_links"
                        " (a_session, b_session, kind, score, via_doc, to_doc, evidence)"
                        " VALUES (?, ?, 'linked-document', ?, ?, ?, ?)",
                        (a, b, score, doc_a, other,
                         f"{doc_a} -> {other} ({kind}: {evidence})"),
                    )
                    written += 1
        conn.commit()
        return written
    finally:
        conn.close()


# ---------------------------------------------------------------- queries


def stats(db: Optional[Path] = None) -> Dict[str, Any]:
    conn = connect(db)
    try:
        def one(sql: str) -> int:
            return int(conn.execute(sql).fetchone()[0])
        partitions = conn.execute(
            "SELECT instance, mode, COUNT(*) AS n FROM sessions"
            " GROUP BY instance, mode ORDER BY n DESC"
        ).fetchall()
        return {
            "sessions": one("SELECT COUNT(*) FROM sessions"),
            "turns": one("SELECT COUNT(*) FROM turns"),
            "documents": one("SELECT COUNT(*) FROM documents"),
            "enriched": one("SELECT COUNT(*) FROM documents WHERE content IS NOT NULL AND content != ''"),
            "citations": one("SELECT COUNT(*) FROM citations"),
            "doc_links": one("SELECT COUNT(*) FROM doc_links"),
            "session_links": one("SELECT COUNT(*) FROM session_links"),
            "partitions": [dict(r) for r in partitions],
            "path": str(Path(db) if db else DB_PATH),
            "size": db_size(db),
        }
    finally:
        conn.close()


def get_flow(db: Optional[Path] = None, session_id: Optional[int] = None,
             instance: str = "", mode: str = "") -> Dict[str, Any]:
    """The full graph: sessions, their turns and citations, and every link."""
    conn = connect(db)
    try:
        where = "WHERE instance = ? AND mode = ?"
        args: List[Any] = [instance, mode]
        if session_id is not None:
            where += " AND id = ?"
            args.append(session_id)
        sessions = []
        for s in conn.execute(f"SELECT * FROM sessions {where} ORDER BY started_at", args):
            turns = []
            for t in conn.execute(
                "SELECT * FROM turns WHERE session_id = ? ORDER BY ts, id", (s["id"],)
            ):
                cites = conn.execute(
                    "SELECT c.doc_id, c.rank, d.title, d.url, d.datasource"
                    " FROM citations c LEFT JOIN documents d"
                    "   ON d.doc_id = c.doc_id AND d.instance = ? AND d.mode = ?"
                    " WHERE c.turn_id = ? ORDER BY c.rank", (instance, mode, t["id"])
                ).fetchall()
                turns.append({**dict(t), "citations": [dict(c) for c in cites]})
            sessions.append({**dict(s), "turns": turns})

        sids = {s["id"] for s in sessions}
        slinks = [dict(r) for r in conn.execute("SELECT * FROM session_links")
                  if r["a_session"] in sids or r["b_session"] in sids]
        dlinks = [dict(r) for r in conn.execute(
            "SELECT * FROM doc_links WHERE instance = ? AND mode = ? ORDER BY score DESC",
            (instance, mode))]
        return {"sessions": sessions, "session_links": slinks,
                "document_links": dlinks, "instance": instance, "mode": mode}
    finally:
        conn.close()


# Ordering for display. A shared citation is trivially certain and says little
# — two sessions cited the same document. A linked-document link is the one
# that found something, and it must not sit underneath a wall of 1.0 scores.
_LINK_INTEREST = {"linked-document": 0, "shared-citation": 1}


def get_flow_summary(db: Optional[Path] = None, instance: str = "",
                     mode: str = "") -> Dict[str, Any]:
    """The compressed narrative: what was investigated and what connected."""
    flow = get_flow(db, None, instance, mode)
    sessions = []
    doc_titles: Dict[str, str] = {}
    for s in flow["sessions"]:
        questions = [t["text"] for t in s["turns"] if t["role"] in ("user", "search") and t["text"]]
        docs: Dict[str, Dict[str, Any]] = {}
        seq = 0
        for t in s["turns"]:
            for c in t["citations"]:
                entry = docs.setdefault(c["doc_id"], {"doc_id": c["doc_id"],
                                                      "title": c.get("title"),
                                                      "datasource": c.get("datasource"),
                                                      "rank": c.get("rank"),
                                                      "cited": 0,
                                                      "seq": seq})
                entry["cited"] += 1
                seq += 1
                if c.get("rank") is not None:
                    best = entry.get("rank")
                    entry["rank"] = c["rank"] if best is None else min(best, c["rank"])
                if c.get("title"):
                    doc_titles[c["doc_id"]] = c["title"]
        sessions.append({
            "session_id": s["id"],
            "chat_id": s["chat_id"],
            "started_at": s["started_at"],
            "turn_count": len(s["turns"]),
            "questions": questions,
            # Documents a thread kept coming back to lead; everything else
            # holds the order it was cited in.
            #
            # Sorting by rank instead would interleave the turns, because every
            # turn's citations restart at rank 0 — a tangential question's top
            # hit would land level with the document the thread is actually
            # about. `seq` keeps each turn's results together and in its own
            # relevance order, which is what a reader is expecting to see.
            "documents": sorted(docs.values(),
                                key=lambda d: (-d.get("cited", 0), d.get("seq", 0))),
        })

    # The evidence a session link carries is a sentence built for a human. The
    # renderer wants the parts, so read them back off the document link itself.
    by_pair = {}
    for l in flow["document_links"]:
        by_pair[(l["a_doc"], l["b_doc"])] = l
        by_pair[(l["b_doc"], l["a_doc"])] = l

    connections = []
    titles = {s["session_id"]: (s["questions"][0] if s["questions"] else f"session {s['session_id']}")
              for s in sessions}
    for l in flow["session_links"]:
        from_doc = l.get("via_doc")
        to_doc = l.get("to_doc") or from_doc
        dl = by_pair.get((from_doc, to_doc)) if from_doc and to_doc else None
        connections.append({
            "a": titles.get(l["a_session"], l["a_session"]),
            "b": titles.get(l["b_session"], l["b_session"]),
            "a_session": l["a_session"],
            "b_session": l["b_session"],
            "kind": l["kind"], "score": l["score"], "why": l["evidence"],
            "from_doc": from_doc,
            "to_doc": to_doc,
            "from_title": doc_titles.get(from_doc or "", from_doc),
            "to_title": doc_titles.get(to_doc or "", to_doc),
            "shares": (dl["evidence"] if dl else None),
            "via_kind": (dl["kind"] if dl else None),
        })
    connections.sort(key=lambda c: (_LINK_INTEREST.get(c["kind"], 99),
                                    -float(c["score"] or 0)))
    return {"instance": instance, "mode": mode,
            "sessions": sessions, "connections": connections}


def get_flow_collapsed(db: Optional[Path] = None, instance: str = "",
                       mode: str = "") -> Dict[str, Any]:
    """Repeated questions and multi-turn threads folded into counted nodes."""
    flow = get_flow(db, None, instance, mode)
    threads = []
    for s in flow["sessions"]:
        questions = Counter(t["text"] for t in s["turns"]
                            if t["role"] in ("user", "search") and t["text"])
        docs = {c["doc_id"]: c.get("title") for t in s["turns"] for c in t["citations"]}
        threads.append({
            "session_id": s["id"],
            "chat_id": s["chat_id"],
            "turn_count": len(s["turns"]),
            "started_at": s["started_at"],
            "questions": [{"text": q, "count": n} for q, n in questions.most_common()],
            "document_count": len(docs),
            "documents": [{"doc_id": k, "title": v} for k, v in docs.items()],
        })
    return {"instance": instance, "mode": mode, "threads": threads,
            "connections": flow["session_links"]}


def purge(db: Optional[Path] = None, instance: Optional[str] = None,
          mode: Optional[str] = None, older_than_days: Optional[float] = None) -> int:
    """Delete captured data. Returns the number of sessions removed."""
    conn = connect(db)
    try:
        clauses, args = [], []
        if instance:
            clauses.append("instance = ?"); args.append(instance)
        if mode:
            clauses.append("mode = ?"); args.append(mode)
        if older_than_days:
            clauses.append("started_at < ?")
            args.append(time.time() - older_than_days * 86400)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        removed = int(conn.execute(f"SELECT COUNT(*) FROM sessions{where}", args).fetchone()[0])
        conn.execute(f"DELETE FROM sessions{where}", args)
        if not clauses:
            for table in ("turns", "citations", "documents", "doc_links", "session_links"):
                conn.execute(f"DELETE FROM {table}")
        else:
            conn.execute(
                "DELETE FROM documents WHERE 1=1" +
                (" AND instance = ?" if instance else "") +
                (" AND mode = ?" if mode else ""),
                [a for a, c in zip(args, clauses) if c.startswith(("instance", "mode"))],
            )
            conn.execute("DELETE FROM turns WHERE session_id NOT IN (SELECT id FROM sessions)")
            conn.execute("DELETE FROM citations WHERE turn_id NOT IN (SELECT id FROM turns)")
            conn.execute("DELETE FROM session_links WHERE a_session NOT IN (SELECT id FROM sessions)"
                         " OR b_session NOT IN (SELECT id FROM sessions)")
        conn.commit()
        conn.execute("VACUUM")
        return removed
    finally:
        conn.close()


# ---------------------------------------------------------------- rendering

_CSS = """
:root { --bg:#fbfaf7; --fg:#1c1c1a; --muted:#6b6a66; --line:#e2e0da;
        --card:#ffffff; --accent:#343ced; --warn:#b35309; --chip:#f1efe9; }
@media (prefers-color-scheme: dark) {
  :root { --bg:#16171a; --fg:#e8e6e1; --muted:#9a9892; --line:#2c2e33;
          --card:#1d1f23; --accent:#8f97ff; --warn:#e0a35c; --chip:#25272c; }
}
* { box-sizing:border-box; }
body { margin:0; padding:2rem 1.25rem 4rem; background:var(--bg); color:var(--fg);
       font:15px/1.55 ui-sans-serif,-apple-system,"Segoe UI",Roboto,sans-serif; }
.wrap { max-width:820px; margin:0 auto; }
h1 { font-size:1.35rem; margin:0 0 .25rem; letter-spacing:-.01em; }
.sub { color:var(--muted); font-size:.85rem; margin-bottom:1.5rem; }
.banner { background:var(--warn); color:#fff; padding:.5rem .75rem; border-radius:6px;
          font-size:.8rem; margin-bottom:1.25rem; }
.tl { position:relative; padding-left:1.5rem; }
.tl:before { content:""; position:absolute; left:.32rem; top:.4rem; bottom:.4rem;
             width:2px; background:var(--line); }
.node { position:relative; margin-bottom:1.1rem; }
.node:before { content:""; position:absolute; left:-1.32rem; top:1.15rem; width:9px; height:9px;
               border-radius:50%; background:var(--accent); }
.card { background:var(--card); border:1px solid var(--line); border-radius:9px; padding:.85rem 1rem; }
.q { font-weight:600; }
.meta { color:var(--muted); font-size:.78rem; margin-top:.15rem; }
details { margin-top:.6rem; }
summary { cursor:pointer; color:var(--accent); font-size:.82rem; }
summary::marker { color:var(--muted); }
.turn { border-left:2px solid var(--line); margin:.5rem 0 0 .2rem; padding:.1rem 0 .1rem .7rem; }
.role { color:var(--muted); font-size:.72rem; text-transform:uppercase; letter-spacing:.04em; }
.chips { margin-top:.6rem; display:flex; flex-wrap:wrap; gap:.35rem; }
.chip { background:var(--chip); border:1px solid var(--line); border-radius:999px;
        padding:.15rem .6rem; font-size:.76rem; text-decoration:none; color:var(--fg); }
.ds { color:var(--muted); }
.link { border-left:3px solid var(--accent); background:var(--card); border-radius:0 8px 8px 0;
        padding:.6rem .85rem; margin:0 0 1.1rem 0; font-size:.85rem; }
.why { color:var(--muted); font-size:.78rem; margin-top:.2rem; font-family:ui-monospace,monospace; }
.count { background:var(--chip); border-radius:999px; padding:0 .4rem; font-size:.72rem;
         color:var(--muted); }
.empty { color:var(--muted); font-style:italic; }
"""


def _esc(text: Any) -> str:
    s = "" if text is None else str(text)
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
             .replace('"', "&quot;"))


def when(ts: Optional[float]) -> str:
    """A timestamp as a person reads it. Shared by the HTML and the terminal."""
    if not ts:
        return "unknown time"
    return time.strftime("%a %d %b %Y, %H:%M", time.localtime(float(ts)))


def render_timeline(db: Optional[Path] = None, instance: str = "",
                    mode: str = "") -> str:
    """A self-contained HTML timeline. No CDN, no framework, no network."""
    collapsed = get_flow_collapsed(db, instance, mode)
    flow_data = get_flow(db, None, instance, mode)
    turns_by_session = {s["id"]: s["turns"] for s in flow_data["sessions"]}
    titles = {t["session_id"]: (t["questions"][0]["text"] if t["questions"]
                                else f"session {t['session_id']}")
              for t in collapsed["threads"]}

    links_by_a: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
    for l in collapsed["connections"]:
        links_by_a[l["a_session"]].append(l)

    parts: List[str] = []
    if mode == "mock":
        parts.append('<div class="banner">Mock mode — every document below is '
                     'fictional demo data, not your organisation\'s content.</div>')

    if not collapsed["threads"]:
        parts.append('<p class="empty">Nothing captured yet. Run some /chat or '
                     '/search commands with capture on.</p>')

    parts.append('<div class="tl">')
    for thread in collapsed["threads"]:
        sid = thread["session_id"]
        parts.append('<div class="node"><div class="card">')
        parts.append(f'<div class="q">{_esc(titles.get(sid, ""))}</div>')
        chat_id = f' · {_esc(thread["chat_id"])}' if thread["chat_id"] else ""
        parts.append(f'<div class="meta">{_esc(when(thread["started_at"]))}'
                     f'{chat_id} · {thread["turn_count"]} turns · '
                     f'{thread["document_count"]} documents</div>')

        # Repeated questions fold into one row with a count.
        extra = [q for q in thread["questions"][1:]]
        if extra:
            parts.append(f'<details><summary>{len(extra)} more question'
                         f'{"s" if len(extra) != 1 else ""} in this thread</summary>')
            for q in extra:
                badge = f' <span class="count">×{q["count"]}</span>' if q["count"] > 1 else ""
                parts.append(f'<div class="turn"><div class="role">asked</div>'
                             f'{_esc(q["text"])}{badge}</div>')
            parts.append('</details>')

        turns = turns_by_session.get(sid, [])
        if turns:
            parts.append(f'<details><summary>Show all {len(turns)} messages</summary>')
            for t in turns:
                parts.append(f'<div class="turn"><div class="role">{_esc(t["role"])}</div>'
                             f'{_esc(t["text"])}</div>')
            parts.append('</details>')

        if thread["documents"]:
            parts.append('<div class="chips">')
            for d in thread["documents"]:
                label = _esc(d["title"] or d["doc_id"])
                parts.append(f'<span class="chip">{label}</span>')
            parts.append('</div>')
        parts.append('</div></div>')

        for l in links_by_a.get(sid, []):
            other = titles.get(l["b_session"], f'session {l["b_session"]}')
            parts.append(
                f'<div class="link">Connects to <strong>{_esc(other)}</strong>'
                f' <span class="count">{_esc(l["kind"])} {l["score"]}</span>'
                f'<div class="why">{_esc(l["evidence"])}</div></div>')
    parts.append('</div>')

    body = "\n".join(parts)
    scope = f'{_esc(instance)} · {_esc(mode)} mode'
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Glean Code — flow</title><style>{_CSS}</style></head>
<body><div class="wrap">
<h1>Flow</h1>
<div class="sub">{scope} · {len(collapsed["threads"])} sessions ·
{len(collapsed["connections"])} connections · rendered {_esc(when(time.time()))}</div>
{body}
</div></body></html>
"""


def write_timeline(path: Path, db: Optional[Path] = None, instance: str = "",
                   mode: str = "") -> Path:
    html = render_timeline(db, instance, mode)
    target = Path(path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(html, encoding="utf-8")
    return target
