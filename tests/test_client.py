"""Tests for glean_code.client"""
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from glean_code.client import GleanClient, GleanError, _mock_response
from glean_code.config import Config


class TestMockResponse(unittest.TestCase):
    """Tests for _mock_response — no I/O, all offline."""

    def setUp(self):
        self.sleep_patcher = patch("time.sleep")
        self.sleep_patcher.start()

    def tearDown(self):
        self.sleep_patcher.stop()

    # --- /chat ---

    def test_chat_returns_chat_id(self):
        body = {"messages": [{"fragments": [{"text": "hello"}]}]}
        resp = _mock_response("/chat", body)
        self.assertIn("chatId", resp)
        self.assertTrue(resp["chatId"].startswith("chat_"))

    def test_chat_preserves_existing_chat_id(self):
        body = {"chatId": "existing-id", "messages": [{"fragments": [{"text": "hi"}]}]}
        resp = _mock_response("/chat", body)
        self.assertEqual(resp["chatId"], "existing-id")

    def test_chat_response_contains_message_text(self):
        body = {"messages": [{"fragments": [{"text": "what is pto?"}]}]}
        resp = _mock_response("/chat", body)
        text = resp["messages"][0]["fragments"][0]["text"]
        self.assertIn("what is pto?", text)

    def test_chat_includes_citations(self):
        body = {"messages": [{"fragments": [{"text": "q"}]}]}
        resp = _mock_response("/chat", body)
        cites = resp["messages"][0]["citations"]
        self.assertIsInstance(cites, list)
        self.assertGreater(len(cites), 0)
        self.assertIn("sourceDocument", cites[0])

    # --- /search ---

    def test_search_returns_results_list(self):
        resp = _mock_response("/search", {"query": "test", "pageSize": 5})
        self.assertIn("results", resp)
        self.assertLessEqual(len(resp["results"]), 5)

    def test_search_result_has_required_fields(self):
        resp = _mock_response("/search", {"query": "python", "pageSize": 1})
        r = resp["results"][0]
        for field in ("title", "url", "snippets", "datasource", "trackingToken"):
            self.assertIn(field, r)

    def test_search_with_facets_returns_facet_results(self):
        body = {
            "query": "*", "pageSize": 10,
            "requestOptions": {"facets": ["datasource"]},
        }
        resp = _mock_response("/search", body)
        self.assertIn("facetResults", resp)
        facet = resp["facetResults"][0]
        self.assertEqual(facet["sourceName"], "datasource")
        self.assertGreater(len(facet["buckets"]), 0)

    def test_search_without_facets_has_no_facet_results(self):
        resp = _mock_response("/search", {"query": "test", "pageSize": 5})
        self.assertNotIn("facetResults", resp)

    def test_search_page_size_respected_up_to_10(self):
        resp = _mock_response("/search", {"query": "x", "pageSize": 3})
        self.assertEqual(len(resp["results"]), 3)

    def test_search_page_size_capped_at_10(self):
        resp = _mock_response("/search", {"query": "x", "pageSize": 99})
        self.assertEqual(len(resp["results"]), 10)

    # --- /autocomplete ---

    def test_autocomplete_returns_suggestions(self):
        resp = _mock_response("/autocomplete", {"query": "eng"})
        self.assertIn("results", resp)
        suggestions = [r["suggestion"] for r in resp["results"]]
        self.assertTrue(all("eng" in s for s in suggestions))

    def test_autocomplete_three_suggestions(self):
        resp = _mock_response("/autocomplete", {"query": "q"})
        self.assertEqual(len(resp["results"]), 3)

    # --- /recommendations ---

    def test_recommendations_returns_results(self):
        resp = _mock_response("/recommendations", {})
        self.assertIn("results", resp)
        self.assertGreater(len(resp["results"]), 0)

    # --- /feedback ---

    def test_feedback_returns_ok_status(self):
        resp = _mock_response("/feedback", {"trackingToken": "t1", "category": "THUMBS_UP"})
        self.assertEqual(resp["status"], "ok")

    # --- /agents/search ---

    def test_agents_search_returns_agent_list(self):
        resp = _mock_response("/agents/search", {"query": ""})
        self.assertIn("agents", resp)
        self.assertGreater(len(resp["agents"]), 0)

    def test_agents_have_id_name_description(self):
        resp = _mock_response("/agents/search", {"query": ""})
        for agent in resp["agents"]:
            self.assertIn("id", agent)
            self.assertIn("name", agent)
            self.assertIn("description", agent)

    # --- /agents/runs/wait and /agents/runs/stream ---

    def test_agent_run_wait_returns_output(self):
        resp = _mock_response("/agents/runs/wait", {"agentId": "agt_research", "input": "hello"})
        self.assertIn("output", resp)
        self.assertIn("agt_research", resp["output"])

    def test_agent_run_stream_returns_output(self):
        resp = _mock_response("/agents/runs/stream", {"agentId": "agt_sales", "input": "hi"})
        self.assertIn("output", resp)
        self.assertIn("runId", resp)

    def test_agent_run_unique_run_ids(self):
        r1 = _mock_response("/agents/runs/wait", {"agentId": "a", "input": "x"})
        r2 = _mock_response("/agents/runs/wait", {"agentId": "a", "input": "x"})
        self.assertNotEqual(r1["runId"], r2["runId"])

    # --- /tools/list and /tools/call ---

    def test_tools_list_returns_tools(self):
        resp = _mock_response("/tools/list", {})
        self.assertIn("tools", resp)
        self.assertGreater(len(resp["tools"]), 0)

    def test_tools_each_has_name_and_description(self):
        resp = _mock_response("/tools/list", {})
        for t in resp["tools"]:
            self.assertIn("name", t)
            self.assertIn("description", t)

    def test_tools_call_echoes_name(self):
        resp = _mock_response("/tools/call", {"name": "search", "arguments": {"q": "x"}})
        self.assertEqual(resp["name"], "search")
        self.assertEqual(resp["result"], "ok")

    # --- /getdocuments ---

    def test_get_documents_by_id(self):
        resp = _mock_response("/getdocuments", {"documentSpecs": [{"id": "doc_123"}]})
        self.assertIn("documents", resp)
        self.assertEqual(resp["documents"][0]["id"], "doc_123")

    def test_get_documents_by_url(self):
        resp = _mock_response("/getdocuments", {"documentSpecs": [{"url": "https://example.com"}]})
        self.assertEqual(resp["documents"][0]["url"], "https://example.com")

    def test_get_multiple_documents(self):
        specs = [{"id": f"doc_{i}"} for i in range(3)]
        resp = _mock_response("/getdocuments", {"documentSpecs": specs})
        self.assertEqual(len(resp["documents"]), 3)

    # --- /getdocumentpermissions ---

    def test_document_permissions_returns_permissions_list(self):
        resp = _mock_response("/getdocumentpermissions", {"documentSpec": {"id": "d1"}})
        self.assertIn("permissions", resp)
        self.assertIsInstance(resp["permissions"], list)

    # --- /listentities ---

    def test_list_entities_returns_results(self):
        resp = _mock_response("/listentities", {"entityType": "PEOPLE", "pageSize": 10})
        self.assertIn("results", resp)
        self.assertGreater(len(resp["results"]), 0)

    def test_entity_has_name_and_email(self):
        resp = _mock_response("/listentities", {"entityType": "PEOPLE", "pageSize": 10})
        for e in resp["results"]:
            self.assertIn("name", e)
            self.assertIn("email", e)

    # --- /people ---

    def test_people_returns_profile(self):
        resp = _mock_response("/people", {"email": "alice@example.com"})
        self.assertEqual(resp["email"], "alice@example.com")
        self.assertIn("name", resp)

    # --- /announcements/* ---

    def test_announcements_list_returns_list(self):
        resp = _mock_response("/announcements/list", {})
        self.assertIn("announcements", resp)

    def test_announcements_create_returns_id_and_status(self):
        resp = _mock_response("/announcements/create", {"title": "Hi", "body": {"text": "hello"}})
        self.assertIn("id", resp)
        self.assertEqual(resp["status"], "created")

    def test_announcements_create_unique_ids(self):
        r1 = _mock_response("/announcements/create", {"title": "A", "body": {}})
        r2 = _mock_response("/announcements/create", {"title": "B", "body": {}})
        self.assertNotEqual(r1["id"], r2["id"])

    def test_announcements_delete_echoes_id(self):
        resp = _mock_response("/announcements/delete", {"id": "ann_42"})
        self.assertEqual(resp["id"], "ann_42")
        self.assertEqual(resp["status"], "deleted")

    # --- /listcollections and /createcollection ---

    def test_collections_list_returns_collections(self):
        resp = _mock_response("/listcollections", {})
        self.assertIn("collections", resp)

    def test_collection_create_echoes_name(self):
        resp = _mock_response("/createcollection", {"name": "My Collection"})
        self.assertEqual(resp["name"], "My Collection")
        self.assertIn("id", resp)

    # --- /listpins and /createpin ---

    def test_pins_list_returns_pins(self):
        resp = _mock_response("/listpins", {})
        self.assertIn("pins", resp)

    def test_pin_create_returns_id_and_status(self):
        resp = _mock_response("/createpin", {"url": "https://pto.com", "query": "pto"})
        self.assertIn("id", resp)
        self.assertEqual(resp["status"], "created")

    # --- unknown path passthrough ---

    def test_unknown_path_returns_mock_passthrough(self):
        resp = _mock_response("/some/unknown/path", {"key": "val"})
        self.assertTrue(resp.get("mock"))
        self.assertEqual(resp["path"], "/some/unknown/path")
        self.assertEqual(resp["body"]["key"], "val")


class TestGleanClientHeaders(unittest.TestCase):
    def test_content_type_always_set(self):
        h = GleanClient(Config())._headers()
        self.assertEqual(h["Content-Type"], "application/json")
        self.assertEqual(h["Accept"], "application/json")

    def test_no_auth_header_without_token(self):
        self.assertNotIn("Authorization", GleanClient(Config())._headers())

    def test_auth_header_with_token(self):
        h = GleanClient(Config(api_token="mytoken"))._headers()
        self.assertEqual(h["Authorization"], "Bearer mytoken")

    def test_no_act_as_header_by_default(self):
        self.assertNotIn("X-Glean-ActAs", GleanClient(Config())._headers())

    def test_act_as_header_when_configured(self):
        h = GleanClient(Config(api_token="tok", act_as="user@example.com"))._headers()
        self.assertEqual(h["X-Glean-ActAs"], "user@example.com")

    def test_indexing_headers_include_indexing_token(self):
        h = GleanClient(Config(indexing_token="idx_tok"))._indexing_headers()
        self.assertEqual(h["Authorization"], "Bearer idx_tok")


class TestGleanClientMockMode(unittest.TestCase):
    """GleanClient in mock mode delegates to _mock_response."""

    def setUp(self):
        self.sleep_patcher = patch("time.sleep")
        self.sleep_patcher.start()
        self.client = GleanClient(Config(mode="mock"))

    def tearDown(self):
        self.sleep_patcher.stop()

    def test_chat_returns_chat_id(self):
        resp = self.client.chat("hello world")
        self.assertIn("chatId", resp)

    def test_chat_with_explicit_chat_id(self):
        resp = self.client.chat("follow-up", chat_id="existing-cid")
        self.assertEqual(resp["chatId"], "existing-cid")

    def test_chat_with_agent_sets_agent_config(self):
        # Verify the right body is built (mock just echoes via response)
        with patch("glean_code.client._mock_response") as mock_fn:
            mock_fn.return_value = {"chatId": "c1", "messages": []}
            self.client.chat("hi", agent="my_agent")
        body = mock_fn.call_args[0][1]
        self.assertEqual(body["agentConfig"]["agent"], "my_agent")

    def test_search_returns_results(self):
        resp = self.client.search("test query", page_size=5)
        self.assertIn("results", resp)

    def test_search_with_datasource_filter(self):
        with patch("glean_code.client._mock_response") as mock_fn:
            mock_fn.return_value = {"results": []}
            self.client.search("query", datasource="gdrive")
        body = mock_fn.call_args[0][1]
        self.assertEqual(body["requestOptions"]["datasourceFilter"], "gdrive")

    def test_autocomplete_returns_suggestions(self):
        resp = self.client.autocomplete("eng")
        self.assertIn("results", resp)

    def test_recommendations_no_user(self):
        with patch("glean_code.client._mock_response") as mock_fn:
            mock_fn.return_value = {"results": []}
            self.client.recommendations()
        body = mock_fn.call_args[0][1]
        self.assertNotIn("user", body)

    def test_recommendations_with_user(self):
        with patch("glean_code.client._mock_response") as mock_fn:
            mock_fn.return_value = {"results": []}
            self.client.recommendations(user="alice@example.com")
        body = mock_fn.call_args[0][1]
        self.assertEqual(body["user"], "alice@example.com")

    def test_agents_search_no_query(self):
        with patch("glean_code.client._mock_response") as mock_fn:
            mock_fn.return_value = {"agents": []}
            self.client.agents_search()
        body = mock_fn.call_args[0][1]
        self.assertEqual(body["query"], "")

    def test_agents_search_with_query(self):
        with patch("glean_code.client._mock_response") as mock_fn:
            mock_fn.return_value = {"agents": []}
            self.client.agents_search(query="sales")
        body = mock_fn.call_args[0][1]
        self.assertEqual(body["query"], "sales")

    def test_agent_run_wait_path(self):
        with patch("glean_code.client._mock_response") as mock_fn:
            mock_fn.return_value = {"output": "done", "runId": "r1"}
            self.client.agent_run("agt_1", "do something", stream=False)
        self.assertEqual(mock_fn.call_args[0][0], "/agents/runs/wait")

    def test_agent_run_stream_path(self):
        with patch("glean_code.client._mock_response") as mock_fn:
            mock_fn.return_value = {"output": "done", "runId": "r1"}
            self.client.agent_run("agt_1", "do something", stream=True)
        self.assertEqual(mock_fn.call_args[0][0], "/agents/runs/stream")

    def test_get_documents_by_ids(self):
        with patch("glean_code.client._mock_response") as mock_fn:
            mock_fn.return_value = {"documents": []}
            self.client.get_documents(ids=["id_1", "id_2"])
        body = mock_fn.call_args[0][1]
        self.assertEqual(body["documentSpecs"], [{"id": "id_1"}, {"id": "id_2"}])

    def test_get_documents_by_urls(self):
        with patch("glean_code.client._mock_response") as mock_fn:
            mock_fn.return_value = {"documents": []}
            self.client.get_documents(urls=["https://example.com"])
        body = mock_fn.call_args[0][1]
        self.assertEqual(body["documentSpecs"], [{"url": "https://example.com"}])

    def test_feedback_body(self):
        with patch("glean_code.client._mock_response") as mock_fn:
            mock_fn.return_value = {"status": "ok"}
            self.client.feedback("tok_1", "THUMBS_UP", comments="great")
        body = mock_fn.call_args[0][1]
        self.assertEqual(body["trackingToken"], "tok_1")
        self.assertEqual(body["category"], "THUMBS_UP")
        self.assertEqual(body["comments"], "great")

    def test_feedback_no_comments(self):
        with patch("glean_code.client._mock_response") as mock_fn:
            mock_fn.return_value = {"status": "ok"}
            self.client.feedback("tok_1", "THUMBS_DOWN")
        body = mock_fn.call_args[0][1]
        self.assertNotIn("comments", body)

    def test_list_datasources_uses_facets(self):
        resp = self.client.list_datasources()
        self.assertIn("datasources", resp)
        self.assertGreater(len(resp["datasources"]), 0)
        for ds in resp["datasources"]:
            self.assertIn("name", ds)
            self.assertIn("count", ds)

    def test_announcement_create_body(self):
        with patch("glean_code.client._mock_response") as mock_fn:
            mock_fn.return_value = {"id": "ann_1", "status": "created"}
            self.client.announcement_create("Title", "Body text", audience="engineering")
        body = mock_fn.call_args[0][1]
        self.assertEqual(body["title"], "Title")
        self.assertEqual(body["body"]["text"], "Body text")
        self.assertIn("audienceFilters", body)

    def test_collection_create_with_description(self):
        with patch("glean_code.client._mock_response") as mock_fn:
            mock_fn.return_value = {"id": "col_1", "name": "Onboarding"}
            self.client.collection_create("Onboarding", description="New hire docs")
        body = mock_fn.call_args[0][1]
        self.assertEqual(body["name"], "Onboarding")
        self.assertEqual(body["description"], "New hire docs")

    def test_pin_create_body(self):
        with patch("glean_code.client._mock_response") as mock_fn:
            mock_fn.return_value = {"id": "pin_1", "status": "created"}
            self.client.pin_create("https://example.com/pto", "pto policy")
        body = mock_fn.call_args[0][1]
        self.assertEqual(body["url"], "https://example.com/pto")
        self.assertEqual(body["query"], "pto policy")


class TestGleanClientIndexingErrors(unittest.TestCase):
    def test_indexing_post_raises_without_token(self):
        c = GleanClient(Config(instance="acme-be.glean.com"))
        with self.assertRaises(GleanError) as ctx:
            c._indexing_post("/rotatetoken", {})
        self.assertIn("indexing token", str(ctx.exception).lower())

    def test_indexing_post_raises_without_instance(self):
        c = GleanClient(Config(indexing_token="tok", mode="live"))
        with self.assertRaises(GleanError) as ctx:
            c._indexing_post("/rotatetoken", {})
        self.assertIn("instance", str(ctx.exception).lower())

    def test_post_raises_without_base_url_in_live_mode(self):
        c = GleanClient(Config(mode="live"))
        with self.assertRaises(GleanError) as ctx:
            c._post("/search", {})
        self.assertIn("base url", str(ctx.exception).lower())


if __name__ == "__main__":
    unittest.main()
