"""Tests for the flow mapper — capture, enrichment, linking, and rendering.

Every test points the database at a temporary file, so ~/.gleancode/flow.db is
never touched. Nothing here reaches the network: all traffic is mock mode.
"""
import html.parser
import io
import json
import re
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent.parent))

from glean_code import flow, ui
from glean_code.client import GleanClient
from glean_code.commands import HANDLERS, Session
from glean_code.config import Config

INSTANCE = "acme-be.glean.com"


def setUpModule():
    """The mock client sleeps 0.25s per call to feel like a network hop.

    That realism is worth having in the REPL and worth nothing here, where it
    turns a 1-second file into a 30-second one.
    """
    global _no_sleep
    _no_sleep = mock.patch("glean_code.client.time.sleep", lambda *_: None)
    _no_sleep.start()


def tearDownModule():
    _no_sleep.stop()


class _Db:
    """A temp database, plus a client whose capture writes into it."""

    def __enter__(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "flow.db"
        real = flow.record
        self._patch = mock.patch.object(
            flow, "record",
            lambda cfg, p, b, r, db=None, proximity_window=600.0:
                real(cfg, p, b, r, db=self.path, proximity_window=proximity_window),
        )
        self._patch.start()
        return self

    def __exit__(self, *exc):
        self._patch.stop()
        self.tmp.cleanup()
        return False

    def client(self, **kw):
        cfg = Config(mode="mock", instance=INSTANCE, flow_capture="on", **kw)
        return GleanClient(cfg), cfg


class TestCaptureGate(unittest.TestCase):
    """Capture defaults to mock only — live content is opt-in, deliberately."""

    def test_default_records_mock_only(self):
        self.assertTrue(flow.capture_enabled("mock", "mock"))
        self.assertFalse(flow.capture_enabled("mock", "live"))

    def test_on_records_both(self):
        self.assertTrue(flow.capture_enabled("on", "live"))
        self.assertTrue(flow.capture_enabled("on", "mock"))

    def test_off_records_nothing(self):
        self.assertFalse(flow.capture_enabled("off", "mock"))
        self.assertFalse(flow.capture_enabled("off", "live"))

    def test_default_is_mock(self):
        self.assertEqual(flow.DEFAULT_CAPTURE, "mock")
        self.assertEqual(Config().flow_capture, "mock")


class TestCapture(unittest.TestCase):
    def test_chat_records_turns_and_citations(self):
        with _Db() as db:
            client, _ = db.client()
            client.chat("what happened in the checkout incident?")
            st = flow.stats(db.path)
            self.assertEqual(st["sessions"], 1)
            self.assertGreaterEqual(st["turns"], 2)      # question + answer
            self.assertGreater(st["documents"], 0)
            self.assertGreater(st["citations"], 0)

    def test_same_chat_id_is_one_session(self):
        """Threading is exact: /chat echoes chatId, so no time-guessing."""
        with _Db() as db:
            client, _ = db.client()
            first = client.chat("what happened in the checkout incident?")
            client.chat("who owned the fix?", chat_id=first["chatId"])
            self.assertEqual(flow.stats(db.path)["sessions"], 1)

    def test_new_chat_id_is_a_new_session(self):
        with _Db() as db:
            client, _ = db.client()
            client.chat("checkout incident")
            client.chat("northwind renewal")     # no chat_id -> new thread
            self.assertEqual(flow.stats(db.path)["sessions"], 2)

    def test_search_is_captured_with_snippets(self):
        with _Db() as db:
            client, cfg = db.client()
            client.search("checkout incident", page_size=3)
            conn = flow.connect(db.path)
            rows = conn.execute("SELECT * FROM turns WHERE role = 'search'").fetchall()
            self.assertEqual(len(rows), 1)
            docs = conn.execute(
                "SELECT * FROM documents WHERE content IS NOT NULL").fetchall()
            self.assertTrue(docs, "search snippets should seed document content")
            self.assertEqual(docs[0]["content_source"], "search-snippet")
            conn.close()

    def test_rows_are_tagged_with_instance_and_mode(self):
        """Fictional and real content must never be linked together."""
        with _Db() as db:
            client, _ = db.client()
            client.chat("checkout incident")
            conn = flow.connect(db.path)
            for table in ("sessions", "documents"):
                row = conn.execute(f"SELECT * FROM {table} LIMIT 1").fetchone()
                self.assertEqual(row["instance"], INSTANCE)
                self.assertEqual(row["mode"], "mock")
            conn.close()

    def test_capture_never_breaks_the_call(self):
        with _Db() as db:
            client, _ = db.client()
            with mock.patch.object(flow, "_record", side_effect=RuntimeError("boom")):
                resp = client.chat("still works?")
            self.assertIn("messages", resp)

    def test_capture_off_records_nothing(self):
        with _Db() as db:
            cfg = Config(mode="mock", instance=INSTANCE, flow_capture="off")
            GleanClient(cfg).chat("checkout incident")
            self.assertEqual(flow.stats(db.path)["sessions"], 0)


class TestEnrichment(unittest.TestCase):
    def test_enrich_fills_document_text(self):
        with _Db() as db:
            client, cfg = db.client()
            client.chat("what happened in the checkout incident?")
            before = flow.stats(db.path)
            enriched, attempted = flow.enrich(client, cfg, db=db.path)
            after = flow.stats(db.path)
            self.assertGreater(enriched, 0)
            self.assertEqual(attempted, before["documents"] - before["enriched"])
            self.assertEqual(after["enriched"], after["documents"])

    def test_enrich_prefers_getdocuments(self):
        """Mock /getdocuments returns body, so no fallback should be needed."""
        with _Db() as db:
            client, cfg = db.client()
            client.chat("checkout incident")
            flow.enrich(client, cfg, db=db.path)
            conn = flow.connect(db.path)
            sources = {r["content_source"] for r in
                       conn.execute("SELECT content_source FROM documents")}
            conn.close()
            self.assertIn("getdocuments", sources)


class TestLinking(unittest.TestCase):
    def _prepared(self, db):
        client, cfg = db.client()
        first = client.chat("what happened in the checkout incident?")
        client.chat("who owned the fix?", chat_id=first["chatId"])
        client.chat("what are the risks going into the Northwind renewal?")
        flow.enrich(client, cfg, db=db.path, limit=100)
        flow.link_documents(db=db.path, instance=INSTANCE, mode="mock")
        flow.link_sessions(db=db.path, instance=INSTANCE, mode="mock")
        return client, cfg

    def test_identifier_links_are_exact(self):
        with _Db() as db:
            self._prepared(db)
            conn = flow.connect(db.path)
            rows = conn.execute(
                "SELECT * FROM doc_links WHERE kind = 'identifier'").fetchall()
            conn.close()
            self.assertTrue(rows, "INC-1183 spans several documents")
            self.assertTrue(all(r["score"] == 1.0 for r in rows))
            self.assertTrue(any("INC-" in r["evidence"] for r in rows))

    def test_unrelated_sessions_are_connected_through_a_document(self):
        """The case worth having: a QBR mentions an incident in passing.

        Neither conversation shares wording with the other, and the QBR names
        no ticket — the link exists only because a document cited by one
        investigation refers to the other's subject.
        """
        with _Db() as db:
            self._prepared(db)
            summary = flow.get_flow_summary(db=db.path, instance=INSTANCE, mode="mock")
            self.assertTrue(summary["connections"], "expected a cross-session link")
            conn = summary["connections"][0]
            self.assertEqual(conn["kind"], "linked-document")
            self.assertIn("checkout", conn["why"].lower())

    def test_link_evidence_is_specific_not_generic(self):
        """A link nobody can explain is worse than no link."""
        with _Db() as db:
            self._prepared(db)
            c = flow.connect(db.path)
            rows = c.execute("SELECT evidence FROM doc_links WHERE kind = 'phrase'").fetchall()
            c.close()
            generic = {"across", "percent", "customer", "going", "into"}
            for r in rows:
                terms = {t.strip() for t in r["evidence"].split(",")}
                self.assertTrue(terms - generic,
                                f"evidence is entirely generic: {r['evidence']}")

    def test_title_anchoring_beats_bare_rarity(self):
        """A word in the other document's title outranks a once-seen word."""
        docs = [
            {"doc_id": "a", "title": "Checkout Latency Incident",
             "content": "A connection pool exhaustion pushed checkout latency up."},
            {"doc_id": "b", "title": "Customer QBR",
             "content": "Risks: the checkout incident in June and a stray zebra."},
        ]
        rows = [dict(d) for d in docs]
        idf = flow.build_idf(rows)
        # 'zebra' appears once and is therefore rarer than 'checkout'...
        self.assertGreater(idf.get("zebra", 0), idf.get("checkout", 0))
        # ...but only 'checkout' is anchored in the other document's title.
        a_title, _, _ = flow._doc_parts(rows[0])
        _, b_words, _ = flow._doc_parts(rows[1])
        self.assertIn("checkout", b_words & a_title)
        self.assertNotIn("zebra", b_words & a_title)

    def test_links_never_cross_partitions(self):
        with _Db() as db:
            self._prepared(db)
            written = flow.link_documents(db=db.path, instance="other-be.glean.com",
                                          mode="mock")
            self.assertEqual(written, 0)


class TestQueries(unittest.TestCase):
    def test_summary_lists_questions_and_documents(self):
        with _Db() as db:
            client, _ = db.client()
            client.chat("what happened in the checkout incident?")
            s = flow.get_flow_summary(db=db.path, instance=INSTANCE, mode="mock")
            self.assertEqual(len(s["sessions"]), 1)
            self.assertIn("checkout", s["sessions"][0]["questions"][0])
            self.assertTrue(s["sessions"][0]["documents"])

    def test_collapsed_counts_repeats(self):
        with _Db() as db:
            client, _ = db.client()
            first = client.chat("same question")
            client.chat("same question", chat_id=first["chatId"])
            c = flow.get_flow_collapsed(db=db.path, instance=INSTANCE, mode="mock")
            counts = {q["text"]: q["count"] for q in c["threads"][0]["questions"]}
            self.assertEqual(counts["same question"], 2)

    def test_get_flow_can_narrow_to_one_session(self):
        with _Db() as db:
            client, _ = db.client()
            client.chat("first")
            client.chat("second")
            all_sessions = flow.get_flow(db=db.path, instance=INSTANCE, mode="mock")
            one = flow.get_flow(db=db.path, session_id=all_sessions["sessions"][0]["id"],
                                instance=INSTANCE, mode="mock")
            self.assertEqual(len(all_sessions["sessions"]), 2)
            self.assertEqual(len(one["sessions"]), 1)

    def test_queries_are_json_serialisable(self):
        with _Db() as db:
            client, _ = db.client()
            client.chat("checkout incident")
            for fn in (flow.get_flow, flow.get_flow_summary, flow.get_flow_collapsed):
                json.dumps(fn(db=db.path, instance=INSTANCE, mode="mock"), default=str)


class TestPurge(unittest.TestCase):
    def test_purge_scoped_to_partition(self):
        with _Db() as db:
            client, _ = db.client()
            client.chat("checkout incident")
            removed = flow.purge(db=db.path, instance=INSTANCE, mode="mock")
            self.assertEqual(removed, 1)
            self.assertEqual(flow.stats(db.path)["sessions"], 0)

    def test_purge_everything(self):
        with _Db() as db:
            client, _ = db.client()
            client.chat("one")
            client.chat("two")
            flow.purge(db=db.path)
            st = flow.stats(db.path)
            self.assertEqual((st["sessions"], st["turns"], st["documents"]), (0, 0, 0))


class TestRendering(unittest.TestCase):
    def _html(self, db):
        client, cfg = db.client()
        first = client.chat("what happened in the checkout incident?")
        client.chat("who owned the fix?", chat_id=first["chatId"])
        client.chat("what are the risks going into the Northwind renewal?")
        flow.enrich(client, cfg, db=db.path, limit=100)
        flow.link_documents(db=db.path, instance=INSTANCE, mode="mock")
        flow.link_sessions(db=db.path, instance=INSTANCE, mode="mock")
        return flow.render_timeline(db=db.path, instance=INSTANCE, mode="mock")

    def test_html_is_self_contained(self):
        with _Db() as db:
            page = self._html(db)
            self.assertNotRegex(page, r'src=|href="http|@import',
                                "the timeline must not reference anything external")

    def test_html_is_well_formed(self):
        class Checker(html.parser.HTMLParser):
            def __init__(self):
                super().__init__(); self.stack = []; self.bad = []
            def handle_starttag(self, tag, attrs):
                if tag not in ("meta", "br", "img", "link", "hr"):
                    self.stack.append(tag)
            def handle_endtag(self, tag):
                if self.stack and self.stack[-1] == tag:
                    self.stack.pop()
                else:
                    self.bad.append(tag)
        with _Db() as db:
            c = Checker(); c.feed(self._html(db))
            self.assertEqual(c.bad, [])
            self.assertEqual(c.stack, [])

    def test_mock_data_is_badged(self):
        with _Db() as db:
            self.assertIn("Mock mode", self._html(db))

    def test_connections_are_rendered_with_their_evidence(self):
        with _Db() as db:
            page = self._html(db)
            self.assertIn("Connects to", page)
            self.assertIn("checkout", page.lower())

    def test_escaping(self):
        self.assertEqual(flow._esc('<script>&"'), "&lt;script&gt;&amp;&quot;")

    def test_empty_database_renders_a_message(self):
        with _Db() as db:
            page = flow.render_timeline(db=db.path, instance=INSTANCE, mode="mock")
            self.assertIn("Nothing captured yet", page)

    def test_write_timeline_creates_the_file(self):
        with _Db() as db:
            out = Path(db.tmp.name) / "sub" / "flow.html"
            written = flow.write_timeline(out, db=db.path, instance=INSTANCE, mode="mock")
            self.assertTrue(written.exists())
            self.assertGreater(written.stat().st_size, 500)


class TestFlowCommand(unittest.TestCase):
    def _run(self, pos, flags=None, cfg=None):
        session = Session(cfg or Config(mode="mock", instance=INSTANCE))
        buf = io.StringIO()
        with redirect_stdout(buf):
            HANDLERS["flow"](session, pos, flags or {})
        return buf.getvalue()

    def test_bare_flow_shows_status(self):
        with _Db() as db:
            with mock.patch.object(flow, "stats", return_value={
                    "sessions": 0, "turns": 0, "documents": 0, "enriched": 0,
                    "citations": 0, "doc_links": 0, "session_links": 0,
                    "partitions": [], "path": str(db.path), "size": 0}):
                out = self._run([])
        self.assertIn("capture", out)
        self.assertIn("session links", out)

    def test_unknown_subcommand_errors(self):
        out = self._run(["frobnicate"])
        self.assertIn("Usage: /flow", out)

    def test_link_rejects_a_bad_score(self):
        out = self._run(["link"], {"min-score": "high"})
        self.assertIn("--min-score must be a number", out)

    def test_enrich_rejects_a_bad_limit(self):
        out = self._run(["enrich"], {"limit": "lots"})
        self.assertIn("--limit must be an integer", out)

    def test_purge_requires_confirmation(self):
        with mock.patch("builtins.input", return_value="n"):
            out = self._run(["purge"])
        self.assertIn("Cancelled", out)


class TestSchemaMigration(unittest.TestCase):
    """A database written by an earlier version must keep working."""

    def _v1_database(self, path):
        """The schema as it shipped before session_links carried `to_doc`."""
        import sqlite3
        conn = sqlite3.connect(str(path))
        conn.executescript(flow._SCHEMA.replace("    to_doc    TEXT\n", ""))
        conn.execute(
            "INSERT INTO session_links"
            " (a_session, b_session, kind, score, via_doc, evidence)"
            " VALUES (1, 2, 'linked-document', 0.6, 'doc-a', 'doc-a -> doc-b')")
        conn.commit()
        conn.close()

    def test_migration_adds_the_missing_column(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "old.db"
            self._v1_database(path)
            conn = flow.connect(path)
            cols = {r["name"] for r in conn.execute("PRAGMA table_info(session_links)")}
            row = conn.execute("SELECT * FROM session_links").fetchone()
            version = conn.execute(
                "SELECT value FROM meta WHERE key = 'schema_version'").fetchone()[0]
            conn.close()
            self.assertIn("to_doc", cols)
            self.assertEqual(row["via_doc"], "doc-a", "existing rows must survive")
            self.assertIsNone(row["to_doc"])
            self.assertEqual(version, str(flow.SCHEMA_VERSION))

    def test_migration_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "old.db"
            self._v1_database(path)
            for _ in range(3):
                flow.connect(path).close()
            conn = flow.connect(path)
            cols = [r["name"] for r in conn.execute("PRAGMA table_info(session_links)")]
            conn.close()
            self.assertEqual(cols.count("to_doc"), 1)

    def test_session_links_record_both_ends(self):
        """The renderer draws an arrow, so it needs the far end, not just the near one."""
        with _Db() as db:
            client, cfg = db.client()
            first = client.chat("what happened in the checkout incident?")
            client.chat("who owned the fix?", chat_id=first["chatId"])
            client.chat("what are the risks going into the Northwind renewal?")
            flow.enrich(client, cfg, db=db.path, limit=100)
            flow.link_documents(db=db.path, instance=INSTANCE, mode="mock")
            flow.link_sessions(db=db.path, instance=INSTANCE, mode="mock")
            conn = flow.connect(db.path)
            rows = conn.execute("SELECT * FROM session_links").fetchall()
            conn.close()
            self.assertTrue(rows)
            for r in rows:
                self.assertTrue(r["via_doc"])
                self.assertTrue(r["to_doc"])


class TestShowRendering(unittest.TestCase):
    """`/flow show` draws a rail; connections branch off it in a bridge."""

    def _show(self, db, flags=None, width=84, colour=False):
        session = Session(Config(mode="mock", instance=INSTANCE))
        buf = io.StringIO()
        with mock.patch.object(flow, "DB_PATH", db.path), \
                mock.patch.object(ui, "term_width", lambda default=80: width), \
                mock.patch.object(ui, "supports_colour", lambda: colour), \
                redirect_stdout(buf):
            HANDLERS["flow"](session, ["show"], flags or {})
        return buf.getvalue()

    def _prepared(self, db):
        client, cfg = db.client()
        first = client.chat("what happened in the checkout incident?")
        client.chat("who owned the fix?", chat_id=first["chatId"])
        client.chat("what are the risks going into the Northwind renewal?")
        flow.enrich(client, cfg, db=db.path, limit=100)
        flow.link_documents(db=db.path, instance=INSTANCE, mode="mock")
        flow.link_sessions(db=db.path, instance=INSTANCE, mode="mock")

    def test_sessions_hang_off_a_vertical_rail(self):
        with _Db() as db:
            self._prepared(db)
            out = self._show(db)
        self.assertIn("●─ 1", out)
        self.assertIn("●─ 2", out)
        self.assertIn("│", out)

    def test_documents_are_labelled_with_their_datasource(self):
        with _Db() as db:
            self._prepared(db)
            out = self._show(db)
        self.assertIn("confluence", out)
        self.assertIn("gdrive", out)
        self.assertIn("▪", out)

    def test_a_connection_branches_off_the_rail_with_both_documents(self):
        """The point of the feature: which documents bridge, and why."""
        with _Db() as db:
            self._prepared(db)
            out = self._show(db)
        self.assertIn("├──◆", out)
        self.assertIn("linked-document", out)
        self.assertIn("Postmortem: Checkout Latency Incident", out)
        self.assertIn("Customer QBR — Northwind Retail", out)
        self.assertIn("shares:", out)
        self.assertIn("↓", out)

    def test_the_bridge_names_the_session_it_reaches(self):
        """A link is not always to the next session down the rail."""
        with _Db() as db:
            self._prepared(db)
            out = self._show(db)
        bridge = [l for l in out.splitlines() if "├──◆" in l][0]
        self.assertRegex(bridge, r"→\s+\d")

    def test_structure_survives_without_colour(self):
        """Piped or NO_COLOR, the glyphs still carry the shape."""
        with _Db() as db:
            self._prepared(db)
            out = self._show(db, colour=False)
        self.assertNotIn("\033[", out)
        for glyph in ("●─", "│", "├──◆", "↓", "▪"):
            self.assertIn(glyph, out)

    def test_no_line_exceeds_the_terminal_width(self):
        for width in (40, 58, 84, 120):
            with _Db() as db:
                self._prepared(db)
                for colour in (False, True):
                    out = self._show(db, width=width, colour=colour)
                    effective = max(40, min(width, 100))
                    for line in out.splitlines():
                        self.assertLessEqual(
                            ui._vis(line), effective,
                            f"width={width} colour={colour}: {line!r}")

    def test_documents_are_capped_and_the_remainder_counted(self):
        with _Db() as db:
            self._prepared(db)
            out = self._show(db, {"docs": "2"})
        self.assertIn("more documents", out)

    def test_bridges_are_capped_and_the_remainder_counted(self):
        """One session can link to many others; the rail must not become a wall."""
        with _Db() as db:
            self._prepared(db)
            out = self._show(db, {"links": "0"})
        self.assertIn("not shown", out)
        self.assertNotIn("├──◆", out)

    def test_links_flag_must_be_an_integer(self):
        with _Db() as db:
            self._prepared(db)
            out = self._show(db, {"links": "many"})
        self.assertIn("--links must be an integer", out)

    def test_overflow_counts_read_as_english(self):
        with _Db() as db:
            self._prepared(db)
            out = self._show(db, {"docs": "5"})   # 6 documents captured, 1 over
        self.assertIn("1 more document", out)
        self.assertNotIn("1 more documents", out)

    def test_docs_flag_must_be_an_integer(self):
        with _Db() as db:
            self._prepared(db)
            out = self._show(db, {"docs": "loads"})
        self.assertIn("--docs must be an integer", out)

    def test_empty_partition_says_so(self):
        with _Db() as db:
            out = self._show(db)
        self.assertIn("Nothing captured", out)

    def test_unlinked_capture_points_at_the_next_step(self):
        with _Db() as db:
            client, _ = db.client()
            client.chat("what happened in the checkout incident?")
            out = self._show(db)
        self.assertIn("/flow link", out)


class TestOrdering(unittest.TestCase):
    """What leads the list is the whole difference between useful and noise."""

    def test_informative_links_come_before_trivial_ones(self):
        """A shared citation is certain and says little; it must not lead.

        Re-running the same question produces score-1.0 shared-citation links
        to every earlier identical session. Ordered by score they would bury
        the linked-document link, which is the one that actually found
        something.
        """
        summary = {"connections": [
            {"kind": "shared-citation", "score": 1.0},
            {"kind": "linked-document", "score": 0.6},
            {"kind": "shared-citation", "score": 1.0},
            {"kind": "linked-document", "score": 0.9},
        ]}
        ordered = sorted(summary["connections"],
                         key=lambda c: (flow._LINK_INTEREST.get(c["kind"], 99),
                                        -float(c["score"])))
        self.assertEqual([c["kind"] for c in ordered],
                         ["linked-document", "linked-document",
                          "shared-citation", "shared-citation"])
        self.assertEqual(ordered[0]["score"], 0.9, "strongest of its kind first")

    def test_a_repeated_session_puts_its_real_link_first(self):
        with _Db() as db:
            client, cfg = db.client()
            # The same investigation twice, then a related one — which is what
            # anyone testing the feature actually produces.
            for _ in range(2):
                first = client.chat("what happened in the checkout incident?")
                client.chat("who owned the fix?", chat_id=first["chatId"])
            client.chat("what are the risks going into the Northwind renewal?")
            flow.enrich(client, cfg, db=db.path, limit=100)
            flow.link_documents(db=db.path, instance=INSTANCE, mode="mock")
            flow.link_sessions(db=db.path, instance=INSTANCE, mode="mock")
            summary = flow.get_flow_summary(db=db.path, instance=INSTANCE, mode="mock")
        kinds = [c["kind"] for c in summary["connections"]]
        self.assertIn("linked-document", kinds)
        self.assertEqual(kinds[0], "linked-document",
                         "the discovery must not sit under a wall of 1.0 scores")

    def test_documents_keep_each_turn_block_together(self):
        """Sorting by rank would interleave the turns, alternating relevance.

        Every turn's citations restart at rank 0, so a tangential follow-up's
        top hit ties with the document the thread is about.
        """
        with _Db() as db:
            client, _ = db.client()
            first = client.chat("what happened in the checkout incident?")
            client.chat("who owned the fix?", chat_id=first["chatId"])
            summary = flow.get_flow_summary(db=db.path, instance=INSTANCE, mode="mock")
        docs = summary["sessions"][0]["documents"]
        titles = [d["title"] for d in docs]
        self.assertIn("checkout", titles[0].lower(),
                      f"the thread's own subject must lead, got {titles[0]!r}")
        seqs = [d["seq"] for d in docs if d["cited"] == 1]
        self.assertEqual(seqs, sorted(seqs), "singly-cited docs keep citation order")

    def test_documents_cited_by_several_turns_lead(self):
        with _Db() as db:
            client, _ = db.client()
            first = client.chat("what happened in the checkout incident?")
            client.chat("what happened in the checkout incident?", chat_id=first["chatId"])
            summary = flow.get_flow_summary(db=db.path, instance=INSTANCE, mode="mock")
        docs = summary["sessions"][0]["documents"]
        counts = [d["cited"] for d in docs]
        self.assertEqual(counts, sorted(counts, reverse=True))


class TestDatasourceColours(unittest.TestCase):
    def test_known_datasources_differ(self):
        picked = {ui.datasource_colour(n)
                  for n in ("gdrive", "confluence", "jira", "slack")}
        self.assertEqual(len(picked), 4, "each source needs its own colour")

    def test_unknown_datasource_falls_back_to_grey(self):
        """An unfamiliar source must not borrow a familiar one's colour."""
        self.assertEqual(ui.datasource_colour("whatever"), ui.C.GREY)
        self.assertEqual(ui.datasource_colour(None), ui.C.GREY)

    def test_lookup_ignores_case_and_padding(self):
        self.assertEqual(ui.datasource_colour("  JIRA "), ui.C.PURPLE)


if __name__ == "__main__":
    unittest.main()
