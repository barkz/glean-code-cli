"""Tests for the indexing path-walk helpers and --path mode of
/index.document and /index.bulk-documents.
"""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from glean_code import _indexing_walk as walk
from glean_code.commands import HANDLERS, Session
from glean_code.config import Config


class TestPathHelpers(unittest.TestCase):
    def test_path_to_id_basic(self):
        self.assertEqual(walk.path_to_id(Path("team/onboarding.md")), "team-onboarding")

    def test_path_to_id_strips_punctuation_and_spaces(self):
        self.assertEqual(walk.path_to_id(Path("notes/Q2 Planning.md")), "notes-q2-planning")

    def test_path_to_id_with_prefix(self):
        self.assertEqual(walk.path_to_id(Path("a.md"), prefix="proj"), "proj-a")

    def test_filename_to_title_titles_lowercase(self):
        self.assertEqual(walk.filename_to_title("hello-world.md"), "Hello World")

    def test_filename_to_title_preserves_existing_case(self):
        self.assertEqual(walk.filename_to_title("Q2 Planning.md"), "Q2 Planning")

    def test_mime_for_path(self):
        self.assertEqual(walk.mime_for_path(Path("a.md")),  ("text/markdown", "textContent"))
        self.assertEqual(walk.mime_for_path(Path("a.txt")), ("text/plain", "textContent"))
        self.assertEqual(walk.mime_for_path(Path("a.HTML")), ("text/html", "htmlContent"))
        self.assertEqual(walk.mime_for_path(Path("a.json")), ("application/json", "textContent"))
        self.assertIsNone(walk.mime_for_path(Path("a.pdf")))


class TestWalkFiles(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / "readme.md").write_text("# hi")
        (self.tmp / "note.txt").write_text("text")
        (self.tmp / "page.html").write_text("<p>x</p>")
        (self.tmp / "data.json").write_text("{}")
        (self.tmp / "binary.bin").write_text("skip")
        (self.tmp / ".DS_Store").write_text("junk")
        (self.tmp / "sub").mkdir()
        (self.tmp / "sub" / "inner.md").write_text("x")
        (self.tmp / "node_modules").mkdir()
        (self.tmp / "node_modules" / "x.md").write_text("x")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp)

    def test_default_walk_picks_supported_skips_excluded(self):
        matched, skipped = walk.walk_files(self.tmp)
        names = sorted(str(rel) for rel, _ in matched)
        self.assertIn("readme.md", names)
        self.assertIn("note.txt", names)
        self.assertIn("page.html", names)
        self.assertIn("data.json", names)
        self.assertIn(os.path.join("sub", "inner.md"), names)
        self.assertNotIn("binary.bin", names)
        self.assertNotIn(".DS_Store", names)
        self.assertFalse(any("node_modules" in n for n in names))
        self.assertEqual(skipped, [])

    def test_max_bytes_skips_large(self):
        big = self.tmp / "big.md"
        big.write_text("x" * 1024)
        matched, skipped = walk.walk_files(self.tmp, max_bytes=100)
        matched_names = [str(rel) for rel, _ in matched]
        skipped_names = [str(rel) for rel, _ in skipped]
        self.assertNotIn("big.md", matched_names)
        self.assertIn("big.md", skipped_names)

    def test_single_file_root(self):
        single = self.tmp / "readme.md"
        matched, _ = walk.walk_files(single)
        self.assertEqual([str(rel) for rel, _ in matched], ["readme.md"])

    def test_missing_path_raises(self):
        with self.assertRaises(FileNotFoundError):
            walk.walk_files(self.tmp / "nope")

    def test_custom_include_overrides_default(self):
        matched, _ = walk.walk_files(self.tmp, include=["*.txt"])
        names = [rel.name for rel, _ in matched]
        self.assertEqual(names, ["note.txt"])


class TestFileToDocument(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp)

    def test_markdown_file_builds_correct_body(self):
        f = self.tmp / "README.md"
        f.write_text("# Hello\nWorld")
        doc = walk.file_to_document(
            abs_path=f, rel_path=Path("README.md"),
            datasource="custom1", object_type="Article",
            permissions=walk.public_permissions(),
        )
        self.assertEqual(doc["datasource"], "custom1")
        self.assertEqual(doc["objectType"], "Article")
        self.assertEqual(doc["id"], "readme")
        self.assertEqual(doc["title"], "README")
        self.assertEqual(doc["body"], {"mimeType": "text/markdown", "textContent": "# Hello\nWorld"})
        self.assertEqual(doc["permissions"], {"allowAnonymousAccess": True})
        self.assertTrue(doc["viewURL"].startswith("file://"))

    def test_html_file_uses_htmlContent_key(self):
        f = self.tmp / "page.html"
        f.write_text("<p>x</p>")
        doc = walk.file_to_document(
            abs_path=f, rel_path=Path("page.html"),
            datasource="d", object_type="Article",
            permissions=walk.public_permissions(),
        )
        self.assertIn("htmlContent", doc["body"])
        self.assertNotIn("textContent", doc["body"])

    def test_view_url_prefix_overrides_file_uri(self):
        f = self.tmp / "a.md"
        f.write_text("x")
        doc = walk.file_to_document(
            abs_path=f, rel_path=Path("sub/a.md"),
            datasource="d", object_type="Article",
            permissions=walk.public_permissions(),
            view_url_prefix="https://internal/docs/",
        )
        self.assertEqual(doc["viewURL"], "https://internal/docs/sub/a.md")

    def test_unsupported_extension_raises(self):
        f = self.tmp / "a.pdf"
        f.write_text("x")
        with self.assertRaises(ValueError):
            walk.file_to_document(
                abs_path=f, rel_path=Path("a.pdf"),
                datasource="d", object_type="Article",
                permissions=walk.public_permissions(),
            )


class TestIndexDocumentPathMode(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.f = self.tmp / "hello.md"
        self.f.write_text("# Hello")
        self.session = Session(Config(
            instance="foo-be.glean.com", indexing_token="idx", mode="mock",
        ))
        self.session.client = MagicMock()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp)

    def test_path_mode_calls_index_document_with_built_body(self):
        self.session.client.index_document.return_value = {"status": "ACCEPTED"}
        HANDLERS["index.document"](self.session, [], {
            "path": str(self.f),
            "datasource": "custom1",
            "object-type": "Article",
            "public": True,
        })
        args, kwargs = self.session.client.index_document.call_args
        body = args[0]
        self.assertEqual(body["datasource"], "custom1")
        self.assertEqual(body["id"], "hello")
        self.assertEqual(body["body"]["mimeType"], "text/markdown")

    def test_dry_run_does_not_call_api(self):
        HANDLERS["index.document"](self.session, [], {
            "path": str(self.f),
            "datasource": "d", "object-type": "A", "public": True,
            "dry-run": True,
        })
        self.session.client.index_document.assert_not_called()

    def test_directory_to_single_command_errors(self):
        HANDLERS["index.document"](self.session, [], {
            "path": str(self.tmp),
            "datasource": "d", "object-type": "A", "public": True,
        })
        self.session.client.index_document.assert_not_called()

    def test_missing_perms_errors(self):
        HANDLERS["index.document"](self.session, [], {
            "path": str(self.f),
            "datasource": "d", "object-type": "A",
        })
        self.session.client.index_document.assert_not_called()

    def test_path_and_from_file_mutex(self):
        HANDLERS["index.document"](self.session, [], {
            "path": str(self.f),
            "from-file": "/tmp/x.json",
        })
        self.session.client.index_document.assert_not_called()

    def test_public_and_acl_from_file_mutex(self):
        acl = self.tmp / "perms.json"
        acl.write_text("{}")
        HANDLERS["index.document"](self.session, [], {
            "path": str(self.f),
            "datasource": "d", "object-type": "A",
            "public": True, "acl-from-file": str(acl),
        })
        self.session.client.index_document.assert_not_called()


class TestBulkDocumentsPathMode(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / "a.md").write_text("# a")
        (self.tmp / "b.txt").write_text("b")
        (self.tmp / "sub").mkdir()
        (self.tmp / "sub" / "c.md").write_text("c")
        self.session = Session(Config(
            instance="foo-be.glean.com", indexing_token="idx", mode="mock",
        ))
        self.session.client = MagicMock()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp)

    def test_bulk_path_walks_and_calls_client(self):
        self.session.client.bulk_index_documents.return_value = {"ack": True}
        HANDLERS["index.bulk-documents"](self.session, [], {
            "path": str(self.tmp),
            "datasource": "d", "object-type": "A", "public": True,
        })
        args, _ = self.session.client.bulk_index_documents.call_args
        body = args[0]
        self.assertEqual(body["datasource"], "d")
        self.assertTrue(body["isFirstPage"])
        self.assertTrue(body["isLastPage"])
        self.assertTrue(body["uploadId"])
        self.assertEqual(len(body["documents"]), 3)

    def test_bulk_path_respects_include_filter(self):
        self.session.client.bulk_index_documents.return_value = {"ack": True}
        HANDLERS["index.bulk-documents"](self.session, [], {
            "path": str(self.tmp),
            "datasource": "d", "object-type": "A", "public": True,
            "include": "*.txt",
        })
        args, _ = self.session.client.bulk_index_documents.call_args
        names = sorted(d["id"] for d in args[0]["documents"])
        self.assertEqual(names, ["b"])

    def test_bulk_dry_run_does_not_call_api(self):
        HANDLERS["index.bulk-documents"](self.session, [], {
            "path": str(self.tmp),
            "datasource": "d", "object-type": "A", "public": True,
            "dry-run": True,
        })
        self.session.client.bulk_index_documents.assert_not_called()

    def test_bulk_from_file_still_works(self):
        self.session.client.bulk_index_documents.return_value = {"ack": True}
        body_file = self.tmp / "body.json"
        body_file.write_text(json.dumps({"uploadId": "u", "documents": []}))
        HANDLERS["index.bulk-documents"](self.session, [], {
            "from-file": str(body_file),
        })
        args, _ = self.session.client.bulk_index_documents.call_args
        self.assertEqual(args[0], {"uploadId": "u", "documents": []})


if __name__ == "__main__":
    unittest.main()
