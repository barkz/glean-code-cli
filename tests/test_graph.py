"""Tests for the knowledge graph (glean_code/graph.py) and the /graph command.

The graph is synthesised from a search response, so the fixtures here are
search-response shaped — the same shape mock, local and live all return. No
network, no files outside a temp directory.
"""

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import MagicMock

from glean_code import graph
from glean_code.client import GleanError
from glean_code.commands import HANDLERS, Session
from glean_code.config import Config


def _result(doc_id, title, author_email=None, author_name=None, datasource="gdrive",
            container=None, snippet=""):
    meta = {"datasource": datasource, "documentType": "Document"}
    if author_email:
        meta["author"] = {"name": author_name or author_email, "email": author_email}
    if container:
        meta["container"] = container
    return {
        "id": doc_id,
        "title": title,
        "url": "https://example.com/" + doc_id,
        "datasource": datasource,
        "snippets": [{"text": snippet}] if snippet else [],
        "metadata": meta,
    }


RESULTS = [
    _result("d1", "Capacity model for planning", "priya@acme.com", "Priya Raman",
            "gdrive", "Platform Eng / Planning",
            "The capacity model feeds engineer-weeks into the tracker."),
    _result("d2", "PLAN-482 capacity model review", "priya@acme.com", "Priya Raman",
            "jira", "PLAN board",
            "Reviewing the capacity model and its engineer-weeks estimates."),
    _result("d3", "Security access review", "marcus@acme.com", "Marcus Webb",
            "confluence", "SEC space",
            "Quarterly service account rotation and audit evidence."),
]


def _session():
    session = Session(Config(mode="mock"))
    session.client = MagicMock()
    return session


class TestBuild(unittest.TestCase):
    def setUp(self):
        self.g = graph.build(RESULTS, query="planning", source_label="mock corpus")

    def _ids(self, kind):
        return {n["id"] for n in self.g["nodes"] if n["kind"] == kind}

    def _edges(self, kind):
        return [e for e in self.g["edges"] if e["kind"] == kind]

    def test_every_document_becomes_a_node(self):
        self.assertEqual(self._ids("doc"), {"doc:d1", "doc:d2", "doc:d3"})

    def test_authors_are_deduplicated_across_documents(self):
        # Priya wrote two of the three; she is one node with two edges.
        self.assertEqual(self._ids("person"), {"person:priya@acme.com", "person:marcus@acme.com"})
        priya = [e for e in self._edges("authored_by") if e["b"] == "person:priya@acme.com"]
        self.assertEqual(len(priya), 2)

    def test_person_label_prefers_the_display_name(self):
        person = next(n for n in self.g["nodes"] if n["id"] == "person:priya@acme.com")
        self.assertEqual(person["label"], "Priya Raman")
        self.assertEqual(person["meta"]["email"], "priya@acme.com")

    def test_sources_and_containers_become_nodes(self):
        self.assertEqual(self._ids("source"),
                         {"source:gdrive", "source:jira", "source:confluence"})
        self.assertEqual(len(self._ids("container")), 3)

    def test_shared_terms_link_the_two_related_documents(self):
        links = self._edges("shares_term")
        self.assertTrue(links)
        pairs = {(e["a"], e["b"]) for e in links}
        self.assertIn(("doc:d1", "doc:d2"), pairs)
        # the security document shares nothing distinctive with the planning pair
        self.assertNotIn(("doc:d1", "doc:d3"), pairs)

    def test_every_edge_carries_evidence_and_a_score(self):
        for edge in self.g["edges"]:
            self.assertTrue(edge["why"], edge)
            self.assertIsInstance(edge["score"], float)

    def test_shared_term_evidence_names_the_shared_words(self):
        link = next(e for e in self._edges("shares_term"))
        self.assertIn("capacity", link["why"])

    def test_a_string_author_is_accepted_as_well_as_an_object(self):
        g = graph.build([_result("d9", "Plain author", None) | {"author": "sam@acme.com"}])
        self.assertIn("person:sam@acme.com", {n["id"] for n in g["nodes"]})

    def test_results_without_an_id_are_skipped_not_crashed_on(self):
        g = graph.build([{"title": ""}, RESULTS[0]])
        self.assertEqual(len({n["id"] for n in g["nodes"] if n["kind"] == "doc"}), 1)

    def test_min_shared_raises_the_bar_for_a_link(self):
        loose = graph.build(RESULTS, min_shared=2)
        strict = graph.build(RESULTS, min_shared=8)
        self.assertTrue([e for e in loose["edges"] if e["kind"] == "shares_term"])
        self.assertEqual([e for e in strict["edges"] if e["kind"] == "shares_term"], [])

    def test_no_terms_leaves_only_structural_edges(self):
        g = graph.build(RESULTS, with_terms=False)
        kinds = {e["kind"] for g_edge in [g["edges"]] for e in g_edge}
        self.assertNotIn("shares_term", kinds)
        self.assertIn("authored_by", kinds)

    def test_a_term_in_every_document_is_not_evidence_of_anything(self):
        same = [_result("a", "planning planning", snippet="planning notes for planning"),
                _result("b", "planning planning", snippet="planning notes for planning")]
        g = graph.build(same, min_shared=1)
        self.assertEqual([e for e in g["edges"] if e["kind"] == "shares_term"], [])

    def test_empty_results_give_an_empty_graph(self):
        g = graph.build([])
        self.assertEqual(g["nodes"], [])
        self.assertEqual(g["edges"], [])


class TestSummary(unittest.TestCase):
    def setUp(self):
        self.g = graph.build(RESULTS, query="planning")
        self.s = graph.summarize(self.g)

    def test_counts_match_the_graph(self):
        self.assertEqual(self.s["nodes"], len(self.g["nodes"]))
        self.assertEqual(self.s["edges"], len(self.g["edges"]))
        self.assertEqual(self.s["by_kind"]["doc"], 3)
        self.assertEqual(self.s["by_kind"]["person"], 2)

    def test_hubs_are_ranked_by_degree(self):
        degrees = [h["degree"] for h in self.s["hubs"]]
        self.assertEqual(degrees, sorted(degrees, reverse=True))

    def test_clusters_find_the_disconnected_component(self):
        # the security document shares an author and source with nothing else
        sizes = [c["size"] for c in self.s["clusters"]]
        self.assertEqual(len(sizes), 2, self.s["clusters"])
        self.assertEqual(sum(sizes), len(self.g["nodes"]))

    def test_strongest_links_are_shared_term_edges_in_score_order(self):
        scores = [l["score"] for l in self.s["strongest"]]
        self.assertEqual(scores, sorted(scores, reverse=True))


class TestTerminalRender(unittest.TestCase):
    def test_render_names_counts_hubs_and_evidence(self):
        g = graph.build(RESULTS, query="planning")
        out = graph.render_terminal(g, width=100)
        self.assertIn("nodes", out)
        self.assertIn("hubs", out)
        self.assertIn("strongest content links", out)
        self.assertIn("capacity", out)

    def test_render_carries_no_ansi_so_it_stays_testable(self):
        out = graph.render_terminal(graph.build(RESULTS), width=80)
        self.assertNotIn("\x1b[", out)

    def test_empty_graph_says_so(self):
        self.assertIn("No graph", graph.render_terminal(graph.build([])))

    def test_long_labels_are_truncated_to_the_width(self):
        long_title = "x" * 400
        g = graph.build([_result("d1", long_title, "a@b.c")])
        for line in graph.render_terminal(g, width=60).split("\n"):
            self.assertLessEqual(len(line), 60, line)


class TestHtmlRender(unittest.TestCase):
    def setUp(self):
        self.html = graph.render_html(graph.build(RESULTS, query="planning",
                                                  source_label="mock corpus"))

    def test_page_is_self_contained(self):
        # the same rule flow.render_timeline works under: no CDN, no framework
        for forbidden in ("<script src=", "<link rel=\"stylesheet\"", "cdn.", "unpkg"):
            self.assertNotIn(forbidden, self.html)

    def test_page_carries_the_graph_as_json(self):
        payload = self.html.split('id="data" type="application/json">')[1].split("</script>")[0]
        data = json.loads(payload)
        self.assertEqual(len(data["nodes"]), len(graph.build(RESULTS)["nodes"]))
        self.assertTrue(all("x" in n and "y" in n for n in data["nodes"]))

    def test_layout_is_deterministic(self):
        again = graph.render_html(graph.build(RESULTS, query="planning",
                                              source_label="mock corpus"))
        self.assertEqual(self.html, again)

    def test_query_and_source_reach_the_page(self):
        self.assertIn("graph: planning", self.html)
        self.assertIn("mock corpus", self.html)

    def test_closing_script_tags_in_data_are_escaped(self):
        html = graph.render_html(graph.build([_result("d1", "</script><b>x</b>")]))
        self.assertNotIn("</script><b>", html)

    def test_titles_are_escaped_in_the_markup(self):
        html = graph.render_html(graph.build([], query="<img src=x onerror=1>"))
        # the raw string may sit inside the inert JSON payload, but must never
        # reach the markup itself
        markup = html.split('id="data"')[0] + html.split("</script>", 1)[1]
        self.assertNotIn("<img src=x", markup)
        self.assertIn("&lt;img src=x", html)

    def test_panel_escapes_tenant_content_before_using_innerhtml(self):
        # document titles and evidence come from the tenant and land in innerHTML
        html = graph.render_html(graph.build(RESULTS))
        self.assertIn("function esc(value)", html)
        self.assertIn("esc(n.label)", html)
        self.assertIn("esc(e.why)", html)
        self.assertIn("function safeUrl(value)", html)

    def test_only_http_urls_are_linked(self):
        html = graph.render_html(graph.build(RESULTS))
        self.assertIn("/^https?:", html)

    def test_write_html_creates_missing_parents(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "nested" / "graph.html"
            written = graph.write_html(target, graph.build(RESULTS))
            self.assertTrue(written.is_file())
            self.assertIn("<canvas", written.read_text())


class TestGraphCommand(unittest.TestCase):
    def _run(self, pos, flags, results=RESULTS, extra=None):
        session = _session()
        resp = {"results": list(results)}
        if extra:
            resp.update(extra)
        session.client.search.return_value = resp
        buf = io.StringIO()
        with redirect_stdout(buf):
            HANDLERS["graph"](session, pos, flags)
        return session, buf.getvalue()

    def test_requires_a_query(self):
        session = _session()
        buf = io.StringIO()
        with redirect_stdout(buf):
            HANDLERS["graph"](session, [], {})
        self.assertIn("Usage", buf.getvalue())
        session.client.search.assert_not_called()

    def test_searches_then_renders(self):
        session, out = self._run(["quarterly", "planning"], {})
        session.client.search.assert_called_once()
        self.assertIn("quarterly planning", session.client.search.call_args[0][0])
        self.assertIn("nodes", out)
        self.assertIn("mock corpus", out)

    def test_page_size_and_datasource_reach_the_client(self):
        session, _ = self._run(["planning"], {"page-size": "5", "datasource": "jira"})
        kwargs = session.client.search.call_args.kwargs
        self.assertEqual(kwargs["page_size"], 5)
        self.assertEqual(kwargs["datasource"], "jira")

    def test_html_flag_writes_the_page(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "g.html"
            _, out = self._run(["planning"], {"html": str(target)})
            self.assertTrue(target.is_file())
            self.assertIn("Wrote", out)

    def test_html_flag_without_a_path_is_refused(self):
        _, out = self._run(["planning"], {"html": True})
        self.assertIn("needs a path", out)

    def test_no_results_is_reported_not_graphed(self):
        _, out = self._run(["nothing"], {}, results=[])
        self.assertIn("nothing to graph", out)

    def test_search_error_is_surfaced(self):
        session = _session()
        session.client.search.side_effect = GleanError("boom")
        buf = io.StringIO()
        with redirect_stdout(buf):
            HANDLERS["graph"](session, ["planning"], {})
        self.assertIn("boom", buf.getvalue())

    def test_local_index_banner_is_carried_through(self):
        _, out = self._run(["planning"], {}, extra={"localIndex": True})
        self.assertIn("LOCAL", out.upper())

    def test_registered_with_help_docs(self):
        from glean_code.help_docs import DOCS
        self.assertIn("graph", DOCS)
        self.assertIn("--html", DOCS["graph"]["usage"])


if __name__ == "__main__":
    unittest.main()
