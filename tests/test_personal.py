"""Tests for Glean Personal — the local content index.

Every test points the database at a temporary file and indexes a temporary
folder, so ~/.gleancode/personal.db and the user's real files are never
touched. Nothing here reaches the network: the local index has no network path
at all.
"""
import io
import sqlite3
import sys
import tempfile
import time
import unittest
import zipfile
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent.parent))

from glean_code import personal
from glean_code.client import GleanClient, GleanError
from glean_code.commands import HANDLERS, Session
from glean_code.config import Config, MODES

_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

CORPUS = {
    "comp.md": "# Compensation policy\n\n"
               "Salary bands for FY27 are under review. Band 4 tops out at 120k.\n"
               "Managers submit proposals to People Ops by March.\n\n"
               "## Calibration\n\nCalibration sessions run in April.\n",
    "specs/roadmap.md": "# Q3 roadmap\n\n"
                        "Ship the local search index. Salary review tooling is out of scope.\n"
                        "Owner: platform team. Depends on the calibration data model.\n",
    "notes.txt": "Espresso machine needs descaling weekly. The kitchen rota is on the fridge.\n",
    "runbook.json": '{"title":"Runbook","oncall":"platform","steps":["page owner"]}',
}


class _Index(unittest.TestCase):
    """A temp corpus folder plus a temp database, wired to the module default."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.corpus = self.root / "corpus"
        self.db = self.root / "personal.db"
        for name, body in CORPUS.items():
            path = self.corpus / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(body, encoding="utf-8")
        # Handlers and the client call through to the module default, so point
        # it here rather than threading a db argument through every call.
        patch = mock.patch.object(personal, "DB_PATH", self.db)
        patch.start()
        self.addCleanup(patch.stop)

    def write(self, rel: str, body: str) -> Path:
        path = self.corpus / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        return path

    def index(self, **kw):
        kw.setdefault("label", "work")
        return personal.index_source(str(self.corpus), db=self.db, **kw)


# ---------------------------------------------------------------- schema


class TestConnect(_Index):
    def test_creates_schema_and_reports_the_text_store(self):
        conn = personal.connect(self.db)
        self.addCleanup(conn.close)
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        for expected in ("sources", "documents", "chunks", "doc_links", "meta"):
            self.assertIn(expected, tables)
        self.assertIn(personal.text_store(conn),
                      (personal.STORE_FTS, personal.STORE_PLAIN))

    def test_records_schema_version_and_store_in_meta(self):
        conn = personal.connect(self.db)
        self.addCleanup(conn.close)
        meta = dict(conn.execute("SELECT key, value FROM meta").fetchall())
        self.assertEqual(meta["schema_version"], str(personal.SCHEMA_VERSION))
        self.assertIn(meta["text_store"], (personal.STORE_FTS, personal.STORE_PLAIN))

    def test_a_new_database_is_private_to_the_user(self):
        personal.connect(self.db).close()
        self.assertEqual(self.db.stat().st_mode & 0o777, 0o600)

    def test_connect_is_idempotent(self):
        personal.connect(self.db).close()
        conn = personal.connect(self.db)   # must not raise on existing tables
        self.addCleanup(conn.close)
        self.assertTrue(self.db.exists())

    def test_fts5_is_preferred_when_available(self):
        if not personal.fts5_available():
            self.skipTest("this SQLite has no FTS5")
        conn = personal.connect(self.db)
        self.addCleanup(conn.close)
        self.assertEqual(personal.text_store(conn), personal.STORE_FTS)

    def test_db_size_is_zero_for_a_missing_file(self):
        self.assertEqual(personal.db_size(self.root / "nope.db"), 0)


class TestNoFts5Fallback(_Index):
    """The degraded path: an interpreter whose SQLite cannot build FTS5."""

    def setUp(self):
        super().setUp()
        broken = "CREATE VIRTUAL TABLE chunks_fts USING fts5_absent(text);"
        patch = mock.patch.object(personal, "_FTS_SCHEMA", broken)
        patch.start()
        self.addCleanup(patch.stop)

    def test_falls_back_to_the_plain_store(self):
        conn = personal.connect(self.db)
        self.addCleanup(conn.close)
        self.assertEqual(personal.text_store(conn), personal.STORE_PLAIN)

    def test_indexing_and_search_still_work(self):
        self.index()
        hits = personal.search("salary bands", db=self.db)
        self.assertTrue(hits)
        self.assertEqual(hits[0]["doc_id"], "work-comp")

    def test_fetch_still_reassembles_text(self):
        self.index()
        doc = personal.fetch("work-comp", db=self.db)
        self.assertIn("Salary bands", doc["text"])

    def test_the_fallback_scans_past_the_fts5_candidate_window(self):
        """Regression: the scan was capped at 200 rows for both stores.

        The plain store cannot rank in SQL — scoring happens in Python after the
        fetch — so a candidate window sized for FTS5 silently lost recall on any
        corpus bigger than the window.
        """
        big = self.root / "big"
        big.mkdir()
        for i in range(130):
            (big / f"f{i}.md").write_text(f"# Doc {i}\n\n" + "filler payments text here. " * 100)
        (big / "needle.md").write_text("# Needle\n\nThe rare token zebra appears only here.\n")
        personal.index_source(str(big), label="big", db=self.db)
        conn = personal.connect(self.db)
        chunks = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        conn.close()
        self.assertGreater(chunks, 200)

        # Reachable on its own term...
        self.assertEqual([h["doc_id"] for h in personal.search("zebra", db=self.db)],
                         ["big-needle"])
        # ...and alongside a term that 130 other documents share. This needs all
        # three fixes together: the scan window, a prefilter covering every term,
        # and rarity weighting so the common term does not bury the rare one.
        for query in ("payments zebra", "zebra payments"):
            with self.subTest(query=query):
                hits = [h["doc_id"] for h in personal.search(query, db=self.db)]
                self.assertIn("big-needle", hits, query)
                self.assertEqual(hits[0], "big-needle", query)

    def test_fallback_weights_favour_the_rarer_term(self):
        rows = [{"text": "common word here", "title": "", "heading": ""}] * 9
        rows.append({"text": "rare zebra here", "title": "", "heading": ""})
        weights = personal._fallback_weights(rows, ["common", "zebra"])
        self.assertGreater(weights["zebra"], weights["common"])

    def test_python_score_without_weights_still_works(self):
        # weights=None is the documented unweighted path.
        self.assertGreater(
            personal._python_score("salary bands", "Comp", "", ["salary"]), 0)

    def test_an_existing_database_keeps_its_store_choice(self):
        personal.connect(self.db).close()
        # Even with FTS5 working again, switching would orphan every chunk.
        mock.patch.stopall()
        conn = personal.connect(self.db)
        self.addCleanup(conn.close)
        self.assertEqual(personal.text_store(conn), personal.STORE_PLAIN)


# ---------------------------------------------------------------- chunking


class TestChunking(unittest.TestCase):
    def test_sections_split_on_headings(self):
        got = personal.split_sections("# A\n\nbody a\n\n## B\n\nbody b")
        self.assertEqual(got, [("A", "body a"), ("B", "body b")])

    def test_text_with_no_heading_is_one_section(self):
        self.assertEqual(personal.split_sections("just text"), [(None, "just text")])

    def test_a_heading_with_no_body_is_still_indexed(self):
        got = personal.split_sections("# Orphan heading")
        self.assertEqual(got, [("Orphan heading", "Orphan heading")])

    def test_empty_text_yields_no_sections(self):
        self.assertEqual(personal.split_sections("   "), [])

    def test_short_text_is_a_single_chunk(self):
        self.assertEqual(personal.chunk_text("# A\n\nshort"), [("A", "short")])

    def test_paragraphs_pack_up_to_the_limit(self):
        body = "\n\n".join(["x" * 400] * 4)
        chunks = personal.chunk_text(body, limit=1000, overlap=50)
        self.assertGreater(len(chunks), 1)
        for _heading, text in chunks:
            self.assertLessEqual(len(text), 1000)

    def test_an_oversized_paragraph_is_windowed_with_overlap(self):
        body = " ".join(f"sentence{i} number words here." for i in range(200))
        chunks = personal.chunk_text(body, limit=500, overlap=100)
        self.assertGreater(len(chunks), 2)
        for _heading, text in chunks:
            self.assertLessEqual(len(text), 500)
        # Overlap means consecutive windows share trailing/leading words.
        first_tail = chunks[0][1].split()[-1]
        self.assertIn(first_tail, chunks[1][1])

    def test_a_single_sentence_longer_than_the_limit_is_still_cut(self):
        chunks = personal.chunk_text("word" * 500, limit=200, overlap=20)
        self.assertTrue(chunks)
        for _heading, text in chunks:
            self.assertLessEqual(len(text), 200)

    def test_headings_travel_with_their_chunks(self):
        chunks = personal.chunk_text("# Alpha\n\n" + "a" * 50 + "\n\n## Beta\n\n" + "b" * 50)
        self.assertEqual([h for h, _ in chunks], ["Alpha", "Beta"])


# ---------------------------------------------------------------- query building


class TestFtsQuery(unittest.TestCase):
    def test_bare_terms_become_quoted_prefix_matches(self):
        self.assertEqual(personal.fts_query("salary bands"),
                         '"salary"* OR "bands"*')

    def test_a_quoted_span_stays_a_phrase(self):
        self.assertEqual(personal.fts_query('"salary bands"'), '"salary bands"')

    def test_fts_operators_in_user_text_are_neutralised(self):
        # Every term is quoted, so none of this is parsed as syntax.
        built = personal.fts_query("NEAR AND OR NOT * -x:y")
        self.assertNotIn(" NEAR ", f" {built} ".replace('"NEAR"', ""))
        for piece in built.split(" OR "):
            self.assertTrue(piece.startswith('"'))

    def test_stopwords_and_empty_input_yield_nothing(self):
        self.assertEqual(personal.fts_query("the and of"), "")
        self.assertEqual(personal.fts_query("   "), "")
        self.assertEqual(personal.fts_query(None), "")

    def test_tokens_drop_edge_punctuation_but_keep_inner(self):
        self.assertEqual(personal._tokens("Weekly. comp-plan v1.2 'quoted'"),
                         ["weekly", "comp-plan", "v1.2", "quoted"])


# ---------------------------------------------------------------- indexing


class TestIndexSource(_Index):
    def test_first_run_adds_every_supported_file(self):
        report = self.index()
        self.assertEqual(report["added"], len(CORPUS))
        self.assertEqual(report["updated"], 0)
        self.assertEqual(report["unchanged"], 0)
        self.assertGreater(report["chunks"], 0)
        self.assertEqual(report["label"], "work")

    def test_unsupported_files_are_never_matched(self):
        (self.corpus / "scan.pdf").write_bytes(b"%PDF-1.4")
        report = self.index()
        self.assertEqual(report["added"], len(CORPUS))

    def test_a_second_run_changes_nothing(self):
        self.index()
        report = self.index()
        self.assertEqual((report["added"], report["updated"]), (0, 0))
        self.assertEqual(report["unchanged"], len(CORPUS))
        self.assertEqual(report["chunks"], 0)

    def test_an_edited_file_is_reindexed_and_others_are_not(self):
        self.index()
        self.write("comp.md", "# Compensation policy\n\nBand 5 added at 160k.")
        report = self.index()
        self.assertEqual(report["updated"], 1)
        self.assertEqual(report["unchanged"], len(CORPUS) - 1)
        hits = personal.search("band 5", db=self.db)
        self.assertEqual(hits[0]["doc_id"], "work-comp")

    def test_a_touched_but_unchanged_file_is_not_reindexed(self):
        self.index()
        path = self.corpus / "comp.md"
        path.touch()
        report = self.index()
        self.assertEqual(report["updated"], 0)

    def test_reindex_forces_a_reread(self):
        self.index()
        report = self.index(reindex=True)
        self.assertEqual(report["updated"], len(CORPUS))
        self.assertEqual(report["unchanged"], 0)

    def test_a_deleted_file_leaves_the_index(self):
        self.index()
        (self.corpus / "notes.txt").unlink()
        report = self.index()
        self.assertEqual(report["removed"], 1)
        self.assertIsNone(personal.fetch("work-notes", db=self.db))

    def test_include_filter_narrows_the_corpus(self):
        report = self.index(include=("*.txt",))
        self.assertEqual(report["added"], 1)

    def test_exclude_filter_skips_a_subtree(self):
        report = self.index(exclude=("specs",))
        self.assertEqual(report["added"], len(CORPUS) - 1)

    def test_filters_persist_across_runs(self):
        self.index(include=("*.txt",))
        report = self.index()   # no include passed: the stored one applies
        self.assertEqual(report["unchanged"], 1)
        self.assertEqual(report["added"], 0)

    def test_max_bytes_records_a_skip_reason(self):
        report = self.index(max_bytes=10)
        self.assertEqual(report["added"], 0)
        self.assertTrue(report["skipped"])
        self.assertIn("max_bytes", report["skipped"][0][1])

    def test_an_empty_file_is_skipped_with_a_reason(self):
        self.write("blank.md", "   \n\n  ")
        report = self.index()
        reasons = dict(report["skipped"])
        self.assertIn("blank.md", reasons)
        self.assertIn("no extractable text", reasons["blank.md"])

    def test_a_corrupt_office_file_is_skipped_not_fatal(self):
        (self.corpus / "broken.docx").write_bytes(b"not a zip")
        report = self.index()
        self.assertEqual(report["added"], len(CORPUS))
        self.assertIn("broken.docx", dict(report["skipped"]))

    def test_office_content_is_indexed_and_searchable(self):
        path = self.corpus / "offsite.docx"
        with zipfile.ZipFile(path, "w") as zf:
            zf.writestr("word/document.xml",
                        f'<w:document xmlns:w="{_W}"><w:body><w:p><w:r>'
                        '<w:t>Offsite covers the FY27 salary bands.</w:t>'
                        '</w:r></w:p></w:body></w:document>')
        self.index()
        ids = [h["doc_id"] for h in personal.search("offsite", db=self.db)]
        self.assertIn("work-offsite", ids)

    def test_label_defaults_to_the_folder_name(self):
        report = personal.index_source(str(self.corpus), db=self.db)
        self.assertEqual(report["label"], "corpus")

    def test_doc_ids_are_disambiguated_on_collision(self):
        # Both slug to "work-a-b"; the second must not collide.
        self.write("a/b.md", "first body text here")
        self.write("a-b.md", "second body text here")
        self.index()
        conn = personal.connect(self.db)
        self.addCleanup(conn.close)
        ids = [r[0] for r in conn.execute(
            "SELECT doc_id FROM documents WHERE doc_id LIKE 'work-a-b%'")]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(len(ids), 2)

    def test_doc_ids_are_unique_across_sources(self):
        """Regression: doc_id is what users and agents pass back, and
        _resolve_doc looks it up without a source, so two folders defaulting to
        the same label both minted the same id and every lookup returned one."""
        for parent in ("a", "b"):
            folder = self.root / parent / "docs"
            folder.mkdir(parents=True)
            (folder / "readme.md").write_text(f"readme belonging to {parent}")
            personal.index_source(str(folder), db=self.db)   # label defaults to "docs"
        ids = [d["doc_id"] for d in personal.list_documents(db=self.db)]
        self.assertEqual(len(ids), len(set(ids)), ids)
        for doc_id in ids:
            self.assertIsNotNone(personal.fetch(doc_id, db=self.db))

    def test_progress_callback_sees_every_file(self):
        seen = []
        self.index(progress=seen.append)
        self.assertEqual(len(seen), len(CORPUS))

    def test_a_missing_folder_raises_personal_error(self):
        with self.assertRaises(personal.PersonalError):
            personal.index_source(str(self.root / "nope"), db=self.db)

    def test_indexing_a_single_file_works(self):
        report = personal.index_source(str(self.corpus / "notes.txt"), db=self.db)
        self.assertEqual(report["added"], 1)


# ---------------------------------------------------------------- retrieval


class TestSearch(_Index):
    def setUp(self):
        super().setUp()
        self.index()

    def test_the_best_document_ranks_first(self):
        hits = personal.search("salary bands FY27", db=self.db)
        self.assertEqual(hits[0]["doc_id"], "work-comp")

    def test_a_hit_carries_a_snippet_and_a_score(self):
        hit = personal.search("calibration", db=self.db)[0]
        self.assertTrue(hit["snippet"])
        self.assertIsInstance(hit["score"], float)

    def test_snippets_are_a_single_line(self):
        # Structured formats have no sentence enders and would otherwise emit
        # a whole multi-line chunk into an aligned layout.
        hit = personal.search("oncall platform", db=self.db)[0]
        self.assertNotIn("\n", hit["snippet"])

    def test_one_row_per_document_not_per_chunk(self):
        hits = personal.search("calibration", db=self.db)
        ids = [h["doc_id"] for h in hits]
        self.assertEqual(len(ids), len(set(ids)))

    def test_limit_is_respected(self):
        self.assertLessEqual(len(personal.search("the", limit=2, db=self.db)), 2)

    def test_source_filter_restricts_to_one_folder(self):
        other = self.root / "other"
        other.mkdir()
        (other / "misc.md").write_text("Salary bands appear here too.")
        personal.index_source(str(other), label="other", db=self.db)
        hits = personal.search("salary bands", source="other", db=self.db)
        self.assertTrue(hits)
        self.assertEqual({h["datasource"] for h in hits}, {"other"})

    def test_no_match_returns_nothing(self):
        self.assertEqual(personal.search("zzzznotpresent", db=self.db), [])

    def test_an_all_stopword_query_returns_nothing(self):
        self.assertEqual(personal.search("the and of", db=self.db), [])

    def test_non_ascii_content_is_searchable(self):
        """Regression: an ASCII-only term regex made non-English text unreachable.

        "München" tokenized to "nchen" and a CJK query to nothing at all, so the
        content was indexed but could never be found.
        """
        self.write("intl.md", "# Standorte\n\n"
                              "Das Büro in München eröffnet im Frühling. "
                              "Zürich folgt. 日本語のドキュメント。 Café Ubersicht.\n")
        self.index()
        for query in ("München", "Zürich", "Frühling", "日本語", "Café"):
            with self.subTest(query=query):
                hits = [h["doc_id"] for h in personal.search(query, db=self.db)]
                self.assertIn("work-intl", hits, query)

    def test_non_ascii_terms_survive_tokenisation(self):
        self.assertEqual(personal._tokens("München Zürich café"),
                         ["münchen", "zürich", "café"])
        self.assertEqual(personal._tokens("日本語"), ["日本語"])

    def test_results_expose_a_file_url(self):
        hit = personal.search("calibration", db=self.db)[0]
        self.assertTrue(hit["url"].startswith("file://"))


class TestFetchAndList(_Index):
    def setUp(self):
        super().setUp()
        self.index()

    def test_fetch_by_doc_id(self):
        self.assertEqual(personal.fetch("work-comp", db=self.db)["doc_id"], "work-comp")

    def test_fetch_by_relative_path(self):
        self.assertEqual(personal.fetch("specs/roadmap.md", db=self.db)["doc_id"],
                         "work-specs-roadmap")

    def test_fetch_by_absolute_path_and_file_url(self):
        abs_path = str((self.corpus / "notes.txt").resolve())
        self.assertEqual(personal.fetch(abs_path, db=self.db)["doc_id"], "work-notes")
        self.assertEqual(personal.fetch(f"file://{abs_path}", db=self.db)["doc_id"],
                         "work-notes")

    def test_fetch_by_filename_fragment(self):
        self.assertEqual(personal.fetch("roadmap", db=self.db)["doc_id"],
                         "work-specs-roadmap")

    def test_fetch_reassembles_the_whole_document(self):
        doc = personal.fetch("work-comp", db=self.db)
        self.assertIn("Salary bands", doc["text"])
        self.assertIn("Calibration sessions", doc["text"])
        self.assertFalse(doc["truncated"])

    def test_fetch_truncates_and_flags_it(self):
        doc = personal.fetch("work-comp", max_chars=20, db=self.db)
        self.assertTrue(doc["truncated"])

    def test_fetch_exposes_headings(self):
        self.assertIn("Calibration", personal.fetch("work-comp", db=self.db)["headings"])

    def test_fetch_headings_are_deduplicated_in_order(self):
        # A section longer than one chunk splits into several, each carrying the
        # same heading; listing it once per chunk reads as repeated sections.
        self.write("long.md", "# Alpha\n\n" + ("alpha " * 400)
                              + "\n\n# Beta\n\n" + ("beta " * 400))
        self.index()
        headings = personal.fetch("work-long", db=self.db)["headings"]
        self.assertEqual(headings, ["Alpha", "Beta"])

    def test_fetch_cuts_inside_an_oversized_first_chunk(self):
        """Regression: bailing out returned an empty body marked truncated.

        Any max_chars below the first chunk's length hit this, which is the
        common case for a small budget against a real document.
        """
        self.write("long.md", "# Long\n\n" + "word " * 400)
        self.index()
        doc = personal.fetch("work-long", max_chars=500, db=self.db)
        self.assertTrue(doc["truncated"])
        self.assertGreater(len(doc["text"]), 100)
        self.assertLessEqual(len(doc["text"]), 500)

    def test_fetch_of_an_unknown_reference_is_none(self):
        self.assertIsNone(personal.fetch("nothing-like-this", db=self.db))
        self.assertIsNone(personal.fetch("", db=self.db))

    def test_list_documents_and_source_filter(self):
        self.assertEqual(len(personal.list_documents(db=self.db)), len(CORPUS))
        self.assertEqual(personal.list_documents(source="nope", db=self.db), [])


class TestSourcesStatsPurge(_Index):
    def test_sources_reports_counts(self):
        self.index()
        srcs = personal.sources(db=self.db)
        self.assertEqual(len(srcs), 1)
        self.assertEqual(srcs[0]["label"], "work")
        self.assertEqual(srcs[0]["documents"], len(CORPUS))
        self.assertGreater(srcs[0]["chunks"], 0)

    def test_stats_totals(self):
        self.index()
        st = personal.stats(db=self.db)
        self.assertEqual(st["documents"], len(CORPUS))
        self.assertEqual(st["sources"], 1)
        self.assertGreater(st["characters"], 0)
        self.assertGreater(st["size"], 0)

    def test_reindexing_the_same_root_does_not_duplicate_the_source(self):
        self.index()
        self.index()
        self.assertEqual(len(personal.sources(db=self.db)), 1)

    def test_remove_source_by_label_clears_its_documents(self):
        self.index()
        removed = personal.remove_source("work", db=self.db)
        self.assertEqual(removed["documents"], len(CORPUS))
        self.assertEqual(personal.stats(db=self.db)["documents"], 0)
        self.assertEqual(personal.stats(db=self.db)["chunks"], 0)

    def test_remove_source_by_path(self):
        self.index()
        personal.remove_source(str(self.corpus), db=self.db)
        self.assertEqual(personal.stats(db=self.db)["sources"], 0)

    def test_remove_unknown_source_raises(self):
        with self.assertRaises(personal.PersonalError):
            personal.remove_source("not-a-source", db=self.db)

    def test_purge_everything_empties_the_index(self):
        self.index()
        personal.purge(db=self.db)
        st = personal.stats(db=self.db)
        self.assertEqual((st["documents"], st["chunks"], st["sources"]), (0, 0, 0))

    def test_purge_leaves_the_files_on_disk(self):
        self.index()
        personal.purge(db=self.db)
        self.assertTrue((self.corpus / "comp.md").exists())

    def test_removing_a_source_drops_its_text_rows_too(self):
        self.index()
        personal.remove_source("work", db=self.db)
        conn = personal.connect(self.db)
        self.addCleanup(conn.close)
        table = personal._store_table(personal.text_store(conn))
        self.assertEqual(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0], 0)


# ---------------------------------------------------------------- content graph


class TestContentGraph(_Index):
    def setUp(self):
        super().setUp()
        self.write("offsite.md", "# Offsite\n\nThe offsite covers FY27 salary bands "
                                "and the Q3 roadmap. Platform team presents the "
                                "calibration data model.\n")
        self.index()

    def test_links_are_discovered_between_related_documents(self):
        self.assertGreater(personal.link_documents(min_score=0.2, db=self.db), 0)

    def test_related_returns_neighbours_with_evidence(self):
        personal.link_documents(min_score=0.2, db=self.db)
        links = personal.related("work-offsite", db=self.db)
        self.assertTrue(links)
        self.assertTrue(links[0]["evidence"])
        self.assertIn("score", links[0])

    def test_unrelated_documents_do_not_link(self):
        personal.link_documents(min_score=0.2, db=self.db)
        neighbours = {l["doc_id"] for l in personal.related("work-notes", db=self.db)}
        self.assertNotIn("work-comp", neighbours)

    def test_a_higher_threshold_yields_fewer_links(self):
        loose = personal.link_documents(min_score=0.1, db=self.db)
        strict = personal.link_documents(min_score=0.9, db=self.db)
        self.assertLessEqual(strict, loose)

    def test_relinking_replaces_rather_than_accumulates(self):
        first = personal.link_documents(min_score=0.2, db=self.db)
        second = personal.link_documents(min_score=0.2, db=self.db)
        self.assertEqual(first, second)

    def test_related_on_an_unknown_document_raises(self):
        with self.assertRaises(personal.PersonalError):
            personal.related("nope", db=self.db)

    def test_near_duplicate_documents_link_at_full_strength(self):
        """Regression: pruning must never delete the overlap that makes a link.

        Trimming each document to its top-N phrases by IDF alone leaves every
        equally-rare phrase tied, and sorting a set breaks ties in iteration
        order — which differs per document. Two near-duplicate files then kept
        disjoint slices of the very phrases connecting them. Measured on two
        real 20 KB decks that shared 1,495 phrases, the prune left them sharing
        none and the strongest link in the corpus scored 0.0.
        """
        personal.purge(db=self.db)
        body = ("# Quarterly review\n\n"
                "Latency alerts route through the CMDB with no helpdesk ticket. "
                "Calibration sessions reconcile the payroll extract.\n")
        self.write("deck_a.md", body)
        self.write("deck_b.md", body + "\nAppendix: owner is the platform team.\n")
        self.write("unrelated.md", "# Coffee\n\nDescale the espresso machine.\n")
        self.index()
        personal.link_documents(db=self.db)
        # path_to_id preserves underscores, so deck_a.md -> work-deck_a.
        neighbours = {l["doc_id"]: l["score"]
                      for l in personal.related("work-deck_a", db=self.db)}
        self.assertIn("work-deck_b", neighbours)
        self.assertGreater(neighbours["work-deck_b"], 0.9)

    def test_phrase_pruning_is_symmetric_across_documents(self):
        """A phrase is dropped for every document or for none of them."""
        conn = personal.connect(self.db)
        self.addCleanup(conn.close)
        corpus = personal._link_corpus(conn, 20_000)
        df = personal._document_frequency(corpus)
        idf = personal._idf(corpus, df)
        before = [set(d["phrases"]) for d in corpus]
        personal._prepare(corpus, idf, df)
        cap = personal._df_cap(len(corpus))
        for original, doc in zip(before, corpus):
            for phrase in original:
                kept = phrase in doc["phrases"]
                # Survival depends only on the phrase's corpus-wide frequency.
                self.assertEqual(kept, df[phrase] <= cap,
                                 f"{phrase!r} pruned asymmetrically")

    def test_top_k_caps_neighbours_per_document(self):
        for i in range(12):
            self.write(f"dup{i}.md", "# Shared subject\n\n"
                                     "Latency alerts route through the CMDB "
                                     f"with no helpdesk ticket. Variant {i}.\n")
        self.index()
        personal.link_documents(top_k=3, db=self.db)
        conn = personal.connect(self.db)
        self.addCleanup(conn.close)
        worst = conn.execute("""
            SELECT MAX(n) FROM (
              SELECT COUNT(*) n FROM (
                SELECT a_doc AS d FROM doc_links UNION ALL
                SELECT b_doc AS d FROM doc_links) GROUP BY d)
        """).fetchone()[0]
        # Each end keeps 3, so a document can appear in at most 3 of its own
        # plus those that ranked it — bounded, and far below the 11 it would
        # otherwise have.
        self.assertLessEqual(worst, 11)
        self.assertGreater(worst, 0)

    def test_top_k_zero_keeps_every_link_above_the_threshold(self):
        for i in range(6):
            self.write(f"dup{i}.md", "# Shared subject\n\nLatency alerts route "
                                     f"through the CMDB. Variant {i}.\n")
        self.index()
        capped = personal.link_documents(top_k=2, db=self.db)
        uncapped = personal.link_documents(top_k=0, db=self.db)
        self.assertGreaterEqual(uncapped, capped)

    def test_link_progress_is_reported(self):
        self.index()
        seen = []
        personal.link_documents(db=self.db, progress=seen.append)
        self.assertTrue(any("documents" in m for m in seen))
        self.assertTrue(any("candidate pairs" in m for m in seen))

    def test_a_single_document_produces_no_links(self):
        personal.purge(db=self.db)
        self.index(include=("notes.txt",))
        self.assertEqual(personal.link_documents(db=self.db), 0)


# ---------------------------------------------------------------- Glean shapes


class TestGleanShapes(_Index):
    def setUp(self):
        super().setUp()
        self.index()

    def test_search_response_matches_the_client_api_shape(self):
        resp = personal.search_response("salary bands", db=self.db)
        self.assertIn("results", resp)
        self.assertTrue(resp["localIndex"])
        result = resp["results"][0]
        for key in ("id", "title", "url", "datasource", "snippets",
                    "trackingToken", "metadata"):
            self.assertIn(key, result)
        self.assertIn("text", result["snippets"][0])
        self.assertIn("updatedAgo", result["metadata"])

    def test_search_response_can_include_facets(self):
        resp = personal.search_response("salary", facets=True, db=self.db)
        buckets = resp["facetResults"][0]["buckets"]
        self.assertEqual(buckets[0]["value"], "work")

    def test_chat_response_carries_the_banner_and_citations(self):
        resp = personal.chat_response("salary bands", db=self.db)
        text = resp["messages"][0]["fragments"][0]["text"]
        self.assertIn(personal.LOCAL_BANNER, text)
        self.assertIn("no answer has been generated", text)
        self.assertTrue(resp["messages"][0]["citations"])
        self.assertIn("sourceDocument", resp["messages"][0]["citations"][0])

    def test_chat_response_preserves_a_chat_id(self):
        self.assertEqual(
            personal.chat_response("x", chat_id="keep-me", db=self.db)["chatId"],
            "keep-me")

    def test_chat_response_with_no_match_still_carries_the_banner(self):
        resp = personal.chat_response("zzzznotpresent", db=self.db)
        text = resp["messages"][0]["fragments"][0]["text"]
        self.assertIn(personal.LOCAL_BANNER, text)
        self.assertEqual(resp["messages"][0]["citations"], [])

    def test_documents_response_returns_a_list_like_the_client_api(self):
        # A map here made flow.enrich iterate dict keys and enrich nothing.
        resp = personal.documents_response(
            {"documentSpecs": [{"id": "work-comp"}]}, db=self.db)
        self.assertIsInstance(resp["documents"], list)
        doc = resp["documents"][0]
        self.assertEqual(doc["id"], "work-comp")
        self.assertIn("content", doc)

    def test_documents_response_shape_matches_the_mock(self):
        from glean_code.client import _mock_response
        mock_docs = _mock_response("/getdocuments",
                                   {"documentSpecs": [{"id": "acme-1"}]})["documents"]
        local_docs = personal.documents_response(
            {"documentSpecs": [{"id": "work-comp"}]}, db=self.db)["documents"]
        self.assertIs(type(local_docs), type(mock_docs))
        for key in ("id", "title", "url"):
            self.assertIn(key, local_docs[0])

    def test_documents_response_accepts_a_urls_list(self):
        url = personal.fetch("work-notes", db=self.db)["url"]
        resp = personal.documents_response({"urls": [url]}, db=self.db)
        self.assertEqual([d["requestedRef"] for d in resp["documents"]], [url])

    def test_documents_response_ignores_unknown_references(self):
        resp = personal.documents_response({"ids": ["nope"]}, db=self.db)
        self.assertEqual(resp["documents"], [])

    def test_autocomplete_uses_the_key_the_renderer_reads(self):
        # cmd_autocomplete and the mock both read `suggestion`; emitting `text`
        # printed "(no suggestions)" despite real matches.
        resp = personal.autocomplete_response("cal", db=self.db)
        self.assertTrue(resp["results"])
        self.assertIn("suggestion", resp["results"][0])
        self.assertNotIn("text", resp["results"][0])

    def test_autocomplete_shape_matches_the_mock(self):
        from glean_code.client import _mock_response
        mock_keys = set(_mock_response("/autocomplete", {"query": "pay"})["results"][0])
        local_keys = set(personal.autocomplete_response("cal", db=self.db)["results"][0])
        self.assertEqual(local_keys, mock_keys)

    def test_autocomplete_renders_in_the_repl(self):
        session = Session(Config(mode="local"))
        buf = io.StringIO()
        with redirect_stdout(buf):
            HANDLERS["autocomplete"](session, ["cal"], {})
        self.assertNotIn("(no suggestions)", buf.getvalue())

    def test_ago_formats_relative_times(self):
        now = time.time()
        self.assertEqual(personal._ago(now), "today")
        self.assertEqual(personal._ago(now - 86400 * 1.5), "yesterday")
        self.assertIn("days ago", personal._ago(now - 86400 * 5))
        self.assertIn("month", personal._ago(now - 86400 * 60))
        self.assertIn("year", personal._ago(now - 86400 * 400))
        self.assertEqual(personal._ago(None), "")


class TestExplain(_Index):
    """--explain: why a result ranked where it did."""

    def setUp(self):
        super().setUp()
        self.index()

    # -- term matching -------------------------------------------------------

    def test_matched_terms_are_reported_per_hit(self):
        hit = personal.search("salary bands", db=self.db)[0]
        self.assertEqual(set(hit["matched_terms"]), {"salary", "bands"})
        self.assertEqual(hit["query_terms"], personal._tokens("salary bands"))

    def test_a_term_that_did_not_match_is_identifiable(self):
        # The diagnostic the flag exists for: an ORed query puts documents in
        # the list that matched only part of it.
        resp = personal.search_response("salary zzzznotpresent", explain=True,
                                        db=self.db)
        ex = resp["results"][0]["explain"]
        self.assertIn("salary", ex["matched_terms"])
        self.assertIn("zzzznotpresent", ex["missed_terms"])

    def test_plural_and_singular_count_as_matched(self):
        # FTS5 stems with porter, so "managers" finds "manager"; the explanation
        # re-derives matching and must not contradict the ranking it explains.
        self.assertIn("managers",
                      personal._matched_terms("The managers submit proposals.",
                                              "", "", ["managers"]))
        self.assertIn("manager",
                      personal._matched_terms("The managers submit proposals.",
                                              "", "", ["manager"]))

    def test_terms_matching_only_the_title_still_count(self):
        self.assertEqual(personal._matched_terms("body", "Roadmap", "", ["roadmap"]),
                         ["roadmap"])

    # -- passage counts ------------------------------------------------------

    def test_matched_chunks_is_a_real_fraction_of_the_document(self):
        self.write("long.md", "# Wide\n\n" + "\n\n".join(
            [f"Paragraph {i} about scheduling. " * 30 for i in range(6)])
            + "\n\nA single mention of rutabaga.\n")
        self.index()
        narrow = {h["doc_id"]: h for h in personal.search("rutabaga", db=self.db)}
        wide = {h["doc_id"]: h for h in personal.search("scheduling", db=self.db)}
        self.assertEqual(narrow["work-long"]["matched_chunks"], 1)
        self.assertGreater(wide["work-long"]["matched_chunks"], 1)
        self.assertEqual(narrow["work-long"]["total_chunks"],
                         wide["work-long"]["total_chunks"])

    # -- ties ----------------------------------------------------------------

    def test_tie_groups_collapse_near_equal_scores(self):
        self.assertEqual(personal.tie_groups([10.0, 10.0, 9.99, 5.0]), [0, 0, 0, 1])
        self.assertEqual(personal.tie_groups([10.0, 5.0, 1.0]), [0, 1, 2])
        self.assertEqual(personal.tie_groups([]), [])
        self.assertEqual(personal.tie_groups([3.0]), [0])

    def test_tie_groups_survive_zero_scores(self):
        self.assertEqual(personal.tie_groups([0.0, 0.0]), [0, 0])

    def test_tied_results_name_each_other(self):
        resp = personal.search_response("calibration", explain=True, db=self.db)
        for result in resp["results"]:
            ex = result["explain"]
            for other in ex["tied_with"]:
                self.assertNotEqual(other, ex["rank"])
                peer = resp["results"][other - 1]["explain"]
                self.assertEqual(peer["tie_group"], ex["tie_group"])

    # -- shape ---------------------------------------------------------------

    def test_explain_is_absent_unless_asked_for(self):
        # The default result must stay byte-compatible with the Client API.
        resp = personal.search_response("salary", db=self.db)
        self.assertNotIn("explain", resp["results"][0])

    def test_explain_carries_rank_ratio_and_evidence(self):
        resp = personal.search_response("salary bands", explain=True, db=self.db)
        ex = resp["results"][0]["explain"]
        for key in ("score", "heading", "matched_chunks", "total_chunks",
                    "matched_terms", "missed_terms", "rank", "tie_group",
                    "tied_with", "score_ratio"):
            self.assertIn(key, ex)
        self.assertEqual(ex["rank"], 1)
        self.assertEqual(ex["score_ratio"], 1.0)

    def test_score_ratio_descends_with_rank(self):
        resp = personal.search_response("calibration salary roadmap", explain=True,
                                        db=self.db)
        ratios = [r["explain"]["score_ratio"] for r in resp["results"]]
        self.assertEqual(ratios, sorted(ratios, reverse=True))

    def test_explain_on_an_empty_result_set_does_not_raise(self):
        resp = personal.search_response("zzzznotpresent", explain=True, db=self.db)
        self.assertEqual(resp["results"], [])


# ---------------------------------------------------------------- local mode


class TestLocalMode(_Index):
    def setUp(self):
        super().setUp()
        self.index()
        self.client = GleanClient(Config(mode="local"))

    def test_local_is_a_recognised_mode(self):
        self.assertIn("local", MODES)
        self.assertEqual(Config(mode="local").effective_mode, "local")

    def test_local_mode_is_not_overridden_by_credentials(self):
        cfg = Config(mode="local", instance="acme", api_token="tok")
        self.assertEqual(cfg.effective_mode, "local")

    def test_search_routes_to_the_local_index(self):
        resp = self.client.search("salary bands")
        self.assertTrue(resp["localIndex"])
        self.assertEqual(resp["results"][0]["id"], "work-comp")

    def test_search_honours_a_datasource_filter(self):
        resp = self.client.search("salary bands", datasource="nope")
        self.assertEqual(resp["results"], [])

    def test_chat_routes_to_the_local_index(self):
        resp = self.client.chat("salary bands")
        self.assertIn(personal.LOCAL_BANNER,
                      resp["messages"][0]["fragments"][0]["text"])

    def test_autocomplete_and_getdocuments_route_locally(self):
        self.assertTrue(self.client.autocomplete("cal")["localIndex"])
        docs = self.client.get_documents(ids=["work-comp"])["documents"]
        self.assertEqual([d["id"] for d in docs], ["work-comp"])

    def test_an_endpoint_with_no_local_equivalent_explains_itself(self):
        with self.assertRaises(GleanError) as ctx:
            self.client.agents_search()
        message = str(ctx.exception)
        self.assertIn("no local equivalent", message)
        self.assertIn("/mode live", message)

    def test_the_indexing_api_explains_itself_before_asking_for_a_token(self):
        with self.assertRaises(GleanError) as ctx:
            self.client.datasource_status("x")
        message = str(ctx.exception)
        self.assertIn("/personal index", message)
        self.assertNotIn("indexing token", message)

    def test_indexing_commands_explain_local_mode_rather_than_asking_for_a_token(self):
        """The handler guard runs ahead of the client, so it needs the check too.

        Without it, every indexing command in local mode advises setting a
        token — which would not help, since the Indexing API has no local
        counterpart at all.
        """
        session = Session(Config(mode="local"))
        doc = str(self.corpus / "comp.md")
        for command, pos, flags in (
            ("documents.count", [], {"datasource": "github"}),
            ("datasources.status", ["github"], {}),
            ("indexing.rotate-token", [], {}),
            # A real file, so the guard is reached: body construction runs
            # first on purpose, which is what lets --dry-run work with no
            # credentials in any mode.
            ("index.document", [], {"path": None, "datasource": "d",
                                    "object-type": "A", "public": True}),
        ):
            if flags.get("path", "missing") is None:
                flags = dict(flags, path=doc)
            buf = io.StringIO()
            with redirect_stdout(buf):
                HANDLERS[command](session, pos, flags)
            out = buf.getvalue()
            self.assertIn("/personal index", out, command)
            self.assertNotIn("indexing_token", out, command)

    def test_dry_run_still_works_in_local_mode(self):
        """--dry-run prints the request body and sends nothing, so no mode or
        credential gate should stand in its way."""
        session = Session(Config(mode="local"))
        buf = io.StringIO()
        with redirect_stdout(buf):
            HANDLERS["index.document"](session, [], {
                "path": str(self.corpus / "comp.md"), "datasource": "d",
                "object-type": "A", "public": True, "dry-run": True})
        out = buf.getvalue()
        self.assertIn("Compensation", out)
        self.assertNotIn("/personal index", out)

    def test_the_planner_falls_back_locally_instead_of_demanding_a_token(self):
        """/ask has no model in local mode, the same as in mock mode.

        Without this it advised running /login to reach "live mode" — from
        inside local mode, which the user had just deliberately selected.
        """
        self.index()
        session = Session(Config(mode="local"))
        buf = io.StringIO()
        with redirect_stdout(buf):
            HANDLERS["ask"](session, ["find my notes on calibration"], {})
        out = buf.getvalue()
        self.assertIn("[local] using canned plan", out)
        self.assertNotIn("Live mode requires", out)

    def test_local_mode_never_reaches_the_network(self):
        with mock.patch("glean_code.client.urllib.request.urlopen",
                        side_effect=AssertionError("network call attempted")):
            self.client.search("salary bands")
            self.client.chat("salary bands")


# ---------------------------------------------------------------- commands


class TestPersonalCommand(_Index):
    def _run(self, pos, flags=None):
        session = Session(Config(mode="local"))
        buf = io.StringIO()
        with redirect_stdout(buf):
            HANDLERS["personal"](session, pos, flags or {})
        return buf.getvalue()

    def test_index_prints_a_report(self):
        out = self._run(["index", str(self.corpus)], {"label": "work"})
        self.assertIn("indexed: work", out)
        self.assertIn("chunks written", out)

    def test_index_without_a_folder_shows_usage(self):
        self.assertIn("Usage: /personal index", self._run(["index"]))

    def test_index_reports_skipped_files(self):
        (self.corpus / "broken.docx").write_bytes(b"not a zip")
        out = self._run(["index", str(self.corpus)])
        self.assertIn("skipped", out)
        self.assertIn("broken.docx", out)

    def test_index_rejects_a_non_numeric_max_bytes(self):
        out = self._run(["index", str(self.corpus)], {"max-bytes": "big"})
        self.assertIn("--max-bytes must be an integer", out)

    def test_index_accepts_comma_separated_globs(self):
        out = self._run(["index", str(self.corpus)], {"include": "*.txt"})
        self.assertIn("added", out)
        self.assertEqual(personal.stats(db=self.db)["documents"], 1)

    def test_index_of_a_missing_folder_reports_an_error(self):
        self.assertIn("path not found", self._run(["index", str(self.root / "nope")]))

    def test_search_renders_results_with_the_banner(self):
        self.index()
        out = self._run(["search", "salary bands"])
        self.assertIn("[LOCAL INDEX]", out)
        self.assertIn("Comp", out)

    def test_search_explain_shows_matched_and_missed_terms(self):
        self.index()
        out = self._run(["search", "salary zzzznotpresent"], {"explain": True})
        self.assertIn("matched:", out)
        self.assertIn("missed:", out)
        self.assertIn("zzzznotpresent", out)
        self.assertIn("bm25", out)
        self.assertIn("passage", out)

    def test_search_without_explain_stays_clean(self):
        self.index()
        out = self._run(["search", "salary bands"])
        for noise in ("bm25", "matched:", "passages matched"):
            self.assertNotIn(noise, out)

    def test_search_explain_names_the_matching_section(self):
        self.index()
        out = self._run(["search", "calibration"], {"explain": True})
        self.assertIn("Calibration", out)

    def test_search_without_a_query_shows_usage(self):
        self.assertIn("Usage: /personal search", self._run(["search"]))

    def test_status_reports_the_store_and_counts(self):
        self.index()
        out = self._run(["status"])
        self.assertIn("personal index", out)
        self.assertIn("documents", out)

    def test_status_on_an_empty_index_suggests_indexing(self):
        self.assertIn("Nothing indexed yet", self._run(["status"]))

    def test_bare_personal_defaults_to_status(self):
        self.assertIn("personal index", self._run([]))

    def test_sources_lists_indexed_folders(self):
        self.index()
        out = self._run(["sources"])
        self.assertIn("work", out)
        self.assertIn(str(self.corpus), out)

    def test_sources_on_an_empty_index_suggests_indexing(self):
        self.assertIn("No folders indexed", self._run(["sources"]))

    def test_show_prints_metadata_and_text(self):
        self.index()
        out = self._run(["show", "work-comp"])
        self.assertIn("Salary bands", out)
        self.assertIn("Calibration", out)

    def test_show_meta_only_omits_the_body(self):
        self.index()
        out = self._run(["show", "work-comp"], {"meta": True})
        self.assertIn("Sections", out)
        self.assertNotIn("Band 4 tops out", out)

    def test_show_of_an_unknown_document_errors(self):
        self.assertIn("No indexed document", self._run(["show", "nope"]))

    def test_link_then_related(self):
        self.index()
        self.assertIn("document link", self._run(["link"], {"min-score": "0.2"}))
        self.write("offsite.md", "Salary bands FY27 and the calibration data model.")
        self.index()
        self._run(["link"], {"min-score": "0.2"})
        self.assertIn("related to", self._run(["related", "work-offsite"]))

    def test_link_rejects_a_non_numeric_threshold(self):
        self.assertIn("--min-score must be a number",
                      self._run(["link"], {"min-score": "loose"}))

    def test_related_without_links_says_so(self):
        self.index()
        self.assertIn("Nothing linked", self._run(["related", "work-comp"]))

    def test_purge_asks_before_deleting(self):
        self.index()
        with mock.patch("builtins.input", return_value="n"):
            self.assertIn("Cancelled", self._run(["purge"]))
        self.assertEqual(personal.stats(db=self.db)["documents"], len(CORPUS))

    def test_purge_confirmed_empties_the_index(self):
        self.index()
        with mock.patch("builtins.input", return_value="y"):
            self._run(["purge"])
        self.assertEqual(personal.stats(db=self.db)["documents"], 0)

    def test_purge_of_one_source_leaves_others(self):
        self.index()
        other = self.root / "other"
        other.mkdir()
        (other / "x.md").write_text("unrelated content")
        personal.index_source(str(other), label="other", db=self.db)
        with mock.patch("builtins.input", return_value="y"):
            self._run(["purge", "work"])
        labels = {s["label"] for s in personal.sources(db=self.db)}
        self.assertEqual(labels, {"other"})

    def test_purge_of_an_unknown_source_errors(self):
        with mock.patch("builtins.input", return_value="y"):
            self.assertIn("no indexed source", self._run(["purge", "nope"]))

    def test_an_unknown_subcommand_shows_usage(self):
        self.assertIn("Usage: /personal", self._run(["frobnicate"]))


class TestScoreBar(unittest.TestCase):
    """The bar is relative to the top hit and never claims to be a percentage."""

    def setUp(self):
        from glean_code.commands import _score_bar, _render_explain
        self.bar = _score_bar
        self.render = _render_explain

    def test_top_hit_fills_the_bar(self):
        self.assertEqual(self.bar(1.0, width=8), "\u2588" * 8)

    def test_a_weak_hit_still_shows_something(self):
        # A zero-width bar would read as "no result" rather than "weak result".
        self.assertTrue(self.bar(0.0, width=8).startswith("\u2588"))

    def test_out_of_range_ratios_are_clamped(self):
        self.assertEqual(len(self.bar(5.0, width=8)), 8)
        self.assertEqual(len(self.bar(-1.0, width=8)), 8)

    def test_bar_length_is_constant(self):
        for ratio in (0.0, 0.13, 0.5, 0.87, 1.0):
            self.assertEqual(len(self.bar(ratio, width=8)), 8)

    def test_render_tolerates_a_sparse_explain_block(self):
        # Nothing here should assume a key is present.
        self.assertEqual(self.render({}), [])
        self.assertTrue(self.render({"score": 1.0, "score_ratio": 1.0}))

    def test_render_names_ties_as_arbitrary(self):
        out = " ".join(self.render(
            {"score": 2.0, "score_ratio": 1.0, "rank": 1, "tied_with": [2]}))
        self.assertIn("tied with #2", out)
        self.assertIn("arbitrary", out)


class TestModeCommand(_Index):
    def _run(self, pos):
        session = Session(Config())
        buf = io.StringIO()
        with mock.patch.object(Config, "save", lambda self: None):
            with redirect_stdout(buf):
                HANDLERS["mode"](session, pos, {})
        return buf.getvalue()

    def test_mode_local_is_accepted(self):
        self.index()
        out = self._run(["local"])
        self.assertIn("Mode set to local", out)
        self.assertIn("locally indexed", out)

    def test_mode_local_with_an_empty_index_says_so(self):
        self.assertIn("personal index is empty", self._run(["local"]))

    def test_usage_lists_every_mode(self):
        out = self._run(["nonsense"])
        for mode in MODES:
            self.assertIn(mode, out)


if __name__ == "__main__":
    unittest.main()
