"""Tests for the mock corpus that backs offline mode.

Standard library only. No network, no temp state beyond a scratch corpus file.
"""
import json
import os
import tempfile
import unittest
from pathlib import Path

from glean_code import mock_corpus
from glean_code.client import _mock_response


class TestRanking(unittest.TestCase):
    def setUp(self):
        mock_corpus.reset()
        os.environ.pop(mock_corpus.CORPUS_ENV_VAR, None)
        mock_corpus.use_path(None)

    def test_corpus_is_balanced_across_datasources(self):
        counts = {}
        for d in mock_corpus.DOCS:
            counts[d["datasource"]] = counts.get(d["datasource"], 0) + 1
        self.assertEqual(sorted(counts), ["confluence", "gdrive", "github", "jira", "slack"])
        self.assertEqual(set(counts.values()), {14}, counts)

    def test_ids_and_urls_are_unique(self):
        ids = [d["id"] for d in mock_corpus.DOCS]
        urls = [d["url"] for d in mock_corpus.DOCS]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(len(urls), len(set(urls)))

    def test_every_author_is_in_the_roster(self):
        for d in mock_corpus.DOCS:
            self.assertIn(d["author"], mock_corpus.PEOPLE, d["id"])

    def test_every_datasource_fills_a_full_page(self):
        for name in mock_corpus.DATASOURCE_COUNTS:
            results = mock_corpus.search("*", page_size=10, datasource=name)
            self.assertEqual(len(results), 10, name)

    def test_query_ranks_relevant_document_first(self):
        top = mock_corpus.rank("quarterly planning")[0]
        self.assertIn("planning", top["title"].lower())

    def test_unrelated_queries_rank_differently(self):
        planning = mock_corpus.rank("quarterly planning")[0]["id"]
        oncall = mock_corpus.rank("oncall runbook payments")[0]["id"]
        self.assertNotEqual(planning, oncall)

    def test_match_all_returns_freshest_first(self):
        ages = [d["updated_days_ago"] for d in mock_corpus.rank("*")]
        self.assertEqual(ages, sorted(ages))

    def test_datasource_filter_restricts_results(self):
        results = mock_corpus.search("planning", page_size=10, datasource="slack")
        self.assertTrue(results)
        self.assertTrue(all(r["datasource"] == "slack" for r in results))

    def test_page_is_padded_when_query_matches_nothing(self):
        results = mock_corpus.search("zzzzz nonsense", page_size=5)
        self.assertEqual(len(results), 5)

    def test_page_size_capped(self):
        self.assertEqual(len(mock_corpus.search("planning", page_size=99)), 10)

    def test_snippet_prefers_a_sentence_containing_the_query(self):
        result = mock_corpus.search("circuit breaker", page_size=1)[0]
        self.assertIn("breaker", result["snippets"][0]["text"].lower())

    def test_results_carry_author_and_freshness(self):
        r = mock_corpus.search("quarterly planning", page_size=1)[0]
        md = r["metadata"]
        self.assertTrue(md["author"]["name"])
        self.assertIn("@", md["author"]["email"])
        self.assertTrue(md["updatedAgo"].startswith("updated"))


class TestPlaceholders(unittest.TestCase):
    def test_quarter_placeholder_is_expanded(self):
        expanded = mock_corpus.expand("{Q+1} Planning")
        self.assertNotIn("{", expanded)
        self.assertRegex(expanded, r"^Q[1-4] FY\d{2} Planning$")

    def test_next_quarter_differs_from_current(self):
        self.assertNotEqual(mock_corpus.expand("{Q}"), mock_corpus.expand("{Q+1}"))

    def test_no_raw_placeholders_leak_into_results(self):
        for r in mock_corpus.search("*", page_size=10):
            self.assertNotIn("{", r["title"])


class TestLookups(unittest.TestCase):
    def setUp(self):
        mock_corpus.reset()
        mock_corpus.use_path(None)

    def test_find_by_url_then_summarize(self):
        first = mock_corpus.search("quarterly planning", page_size=1)[0]
        doc = mock_corpus.find({"url": first["url"]})
        self.assertIsNotNone(doc)
        self.assertIn(doc["title"].split("—")[0].strip()[:10],
                      mock_corpus.summarize(doc))

    def test_find_by_id(self):
        self.assertIsNotNone(mock_corpus.find({"id": "doc_plan_charter"}))

    def test_find_unknown_returns_none(self):
        self.assertIsNone(mock_corpus.find({"url": "https://nope.example.com/x"}))

    def test_suggestions_contain_the_query(self):
        for s in mock_corpus.suggestions("plan"):
            self.assertIn("plan", s)


class TestEndpointsShareTheCorpus(unittest.TestCase):
    """The point of the corpus: search → summarize → docs.get agree."""

    def setUp(self):
        mock_corpus.reset()
        mock_corpus.use_path(None)

    def test_search_result_url_resolves_in_getdocuments(self):
        hit = _mock_response("/search", {"query": "oncall runbook", "pageSize": 1})["results"][0]
        doc = _mock_response("/getdocuments",
                             {"documentSpecs": [{"url": hit["url"]}]})["documents"][0]
        self.assertEqual(doc["title"], hit["title"])

    def test_search_result_url_summarizes_to_the_same_document(self):
        hit = _mock_response("/search", {"query": "pto policy", "pageSize": 1})["results"][0]
        summary = _mock_response("/summarize",
                                 {"documentSpec": {"url": hit["url"]}})["summary"]
        self.assertIn(hit["title"], summary)

    def test_chat_citations_track_the_question(self):
        body = {"messages": [{"fragments": [{"text": "how do we run quarterly planning?"}]}]}
        cites = _mock_response("/chat", body)["messages"][0]["citations"]
        self.assertTrue(any("planning" in c["sourceDocument"]["title"].lower()
                            for c in cites))

    def test_search_honours_datasource_filter(self):
        body = {"query": "planning", "pageSize": 5,
                "requestOptions": {"datasourceFilter": "confluence"}}
        results = _mock_response("/search", body)["results"]
        self.assertTrue(all(r["datasource"] == "confluence" for r in results))

    def test_search_honours_facet_filter_shape(self):
        body = {"query": "planning", "pageSize": 5,
                "requestOptions": {"facetFilters": [
                    {"fieldName": "datasource", "values": [{"value": "jira"}]}]}}
        results = _mock_response("/search", body)["results"]
        self.assertTrue(all(r["datasource"] == "jira" for r in results))

    def test_permissions_owner_is_the_document_author(self):
        doc = mock_corpus.find({"id": "doc_plan_charter"})
        perms = _mock_response("/getdocumentpermissions",
                               {"documentSpec": {"id": "doc_plan_charter"}})["permissions"]
        self.assertEqual(perms[0]["email"], doc["author"])
        self.assertEqual(perms[0]["role"], "owner")

    def test_people_lookup_uses_the_roster(self):
        resp = _mock_response("/people", {"email": "priya.raman@acme.com"})
        self.assertEqual(resp["name"], "Priya Raman")

    def test_no_endpoint_leaks_raw_placeholders(self):
        calls = [
            ("/search", {"query": "planning", "pageSize": 10}),
            ("/recommendations", {}),
            ("/summarize", {"documentSpec": {"id": "doc_plan_charter"}}),
            ("/getdocuments", {"documentSpecs": [{"id": "doc_plan_tracker"}]}),
            ("/listverifications", {}),
            ("/messages", {"id": "1719483920", "datasource": "slack"}),
            ("/chat", {"messages": [{"fragments": [{"text": "quarterly planning"}]}]}),
        ]
        for path, body in calls:
            with self.subTest(path=path):
                self.assertNotIn("{Q", json.dumps(_mock_response(path, body)))


class TestCustomCorpusFile(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        mock_corpus.reset()

    def tearDown(self):
        mock_corpus.use_path(None)
        os.environ.pop(mock_corpus.CORPUS_ENV_VAR, None)
        mock_corpus.reset()

    def _write(self, payload) -> str:
        path = Path(self.tmp) / "corpus.json"
        path.write_text(json.dumps(payload))
        return str(path)

    def test_custom_documents_replace_the_built_in_set(self):
        path = self._write({"documents": [
            {"title": "Widget Migration Plan", "body": "How the widget fleet migrates."}
        ]})
        mock_corpus.use_path(path)
        results = mock_corpus.search("widget", page_size=5)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["title"], "Widget Migration Plan")

    def test_bare_list_is_accepted(self):
        path = self._write([{"title": "Only Doc", "body": "Body text."}])
        mock_corpus.use_path(path)
        self.assertEqual(mock_corpus.search("only", page_size=1)[0]["title"], "Only Doc")

    def test_env_var_is_honoured(self):
        path = self._write([{"title": "From Env", "body": "Body text."}])
        os.environ[mock_corpus.CORPUS_ENV_VAR] = path
        mock_corpus.use_path(None)
        mock_corpus.reset()
        self.assertEqual(mock_corpus.search("env", page_size=1)[0]["title"], "From Env")

    def test_config_path_wins_over_env_var(self):
        env_path = self._write([{"title": "From Env", "body": "Body."}])
        cfg_path = str(Path(self.tmp) / "cfg.json")
        Path(cfg_path).write_text(json.dumps([{"title": "From Config", "body": "Body."}]))
        os.environ[mock_corpus.CORPUS_ENV_VAR] = env_path
        mock_corpus.use_path(cfg_path)
        mock_corpus.reset()
        self.assertEqual(mock_corpus.search("from", page_size=1)[0]["title"], "From Config")

    def test_missing_file_raises_corpus_error(self):
        mock_corpus.use_path(str(Path(self.tmp) / "nope.json"))
        with self.assertRaises(mock_corpus.CorpusError):
            mock_corpus.search("x", page_size=1)

    def test_invalid_json_raises_corpus_error(self):
        path = Path(self.tmp) / "bad.json"
        path.write_text("{not json")
        mock_corpus.use_path(str(path))
        with self.assertRaises(mock_corpus.CorpusError):
            mock_corpus.search("x", page_size=1)

    def test_document_without_title_raises_corpus_error(self):
        mock_corpus.use_path(self._write([{"body": "no title here"}]))
        with self.assertRaises(mock_corpus.CorpusError):
            mock_corpus.search("x", page_size=1)

    def test_empty_document_list_raises_corpus_error(self):
        mock_corpus.use_path(self._write({"documents": []}))
        with self.assertRaises(mock_corpus.CorpusError):
            mock_corpus.search("x", page_size=1)


if __name__ == "__main__":
    unittest.main()
