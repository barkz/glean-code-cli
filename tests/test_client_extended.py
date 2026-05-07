"""Extended client tests covering new endpoints added after initial suite.

Covers mock responses for: /unpin, /deletecollection, /listshortcuts,
/getshortcut, /createshortcut, /updateshortcut, /deleteshortcut,
/listanswers, /getanswer, /createanswer, /editanswer, /deleteanswer,
/summarize, /listverifications, /verify, /addverificationreminder,
/messages, /activity, /insights.

Also covers GleanClient method signatures for the same new endpoints.
"""
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from glean_code.client import GleanClient, _mock_response
from glean_code.config import Config


class TestMockResponseNewEndpoints(unittest.TestCase):
    def setUp(self):
        self.sleep_patcher = patch("time.sleep")
        self.sleep_patcher.start()

    def tearDown(self):
        self.sleep_patcher.stop()

    # --- /unpin ---

    def test_unpin_echoes_id(self):
        resp = _mock_response("/unpin", {"id": "pin_42"})
        self.assertEqual(resp["id"], "pin_42")
        self.assertEqual(resp["status"], "unpinned")

    # --- /deletecollection ---

    def test_deletecollection_echoes_ids(self):
        resp = _mock_response("/deletecollection", {"ids": [1, 2, 3]})
        self.assertEqual(resp["ids"], [1, 2, 3])
        self.assertEqual(resp["status"], "deleted")

    # --- /listshortcuts ---

    def test_listshortcuts_returns_shortcuts(self):
        resp = _mock_response("/listshortcuts", {"pageSize": 20})
        self.assertIn("shortcuts", resp)
        self.assertGreater(len(resp["shortcuts"]), 0)

    def test_listshortcuts_each_has_required_fields(self):
        resp = _mock_response("/listshortcuts", {"pageSize": 20})
        for sc in resp["shortcuts"]:
            self.assertIn("id", sc)
            self.assertIn("inputAlias", sc)
            self.assertIn("destinationUrl", sc)

    def test_listshortcuts_with_query_filters(self):
        resp = _mock_response("/listshortcuts", {"pageSize": 20, "query": "oncall"})
        self.assertGreater(len(resp["shortcuts"]), 0)
        self.assertIn("oncall", resp["shortcuts"][0]["inputAlias"])

    # --- /getshortcut ---

    def test_getshortcut_returns_shortcut(self):
        resp = _mock_response("/getshortcut", {"alias": "pto"})
        self.assertIn("shortcut", resp)
        sc = resp["shortcut"]
        self.assertEqual(sc["inputAlias"], "pto")

    # --- /createshortcut ---

    def test_createshortcut_returns_id(self):
        resp = _mock_response("/createshortcut",
                               {"data": {"inputAlias": "pto", "destinationUrl": "https://hr.com"}})
        self.assertIn("id", resp)
        self.assertEqual(resp["inputAlias"], "pto")
        self.assertEqual(resp["status"], "created")

    def test_createshortcut_unique_ids(self):
        r1 = _mock_response("/createshortcut",
                             {"data": {"inputAlias": "a", "destinationUrl": "https://a.com"}})
        r2 = _mock_response("/createshortcut",
                             {"data": {"inputAlias": "b", "destinationUrl": "https://b.com"}})
        self.assertNotEqual(r1["id"], r2["id"])

    # --- /updateshortcut ---

    def test_updateshortcut_echoes_id(self):
        resp = _mock_response("/updateshortcut", {"id": 7, "inputAlias": "newpto"})
        self.assertEqual(resp["id"], 7)
        self.assertEqual(resp["status"], "updated")

    # --- /deleteshortcut ---

    def test_deleteshortcut_echoes_id(self):
        resp = _mock_response("/deleteshortcut", {"id": 5})
        self.assertEqual(resp["id"], 5)
        self.assertEqual(resp["status"], "deleted")

    # --- /listanswers ---

    def test_listanswers_returns_answers(self):
        resp = _mock_response("/listanswers", {})
        self.assertIn("answers", resp)
        self.assertGreater(len(resp["answers"]), 0)

    def test_listanswers_each_has_question_and_body(self):
        resp = _mock_response("/listanswers", {})
        for a in resp["answers"]:
            self.assertIn("id", a)
            self.assertIn("question", a)
            self.assertIn("bodyText", a)

    # --- /getanswer ---

    def test_getanswer_returns_answer(self):
        resp = _mock_response("/getanswer", {"id": 1})
        self.assertIn("answer", resp)
        a = resp["answer"]
        self.assertEqual(a["id"], 1)
        self.assertIn("question", a)
        self.assertIn("bodyText", a)

    # --- /createanswer ---

    def test_createanswer_returns_id(self):
        resp = _mock_response("/createanswer",
                               {"data": {"question": "What is PTO?", "bodyText": "20 days"}})
        self.assertIn("id", resp)
        self.assertEqual(resp["question"], "What is PTO?")
        self.assertEqual(resp["status"], "created")

    def test_createanswer_unique_ids(self):
        r1 = _mock_response("/createanswer", {"data": {"question": "Q1?", "bodyText": "A1"}})
        r2 = _mock_response("/createanswer", {"data": {"question": "Q2?", "bodyText": "A2"}})
        self.assertNotEqual(r1["id"], r2["id"])

    # --- /editanswer ---

    def test_editanswer_echoes_id(self):
        resp = _mock_response("/editanswer", {"id": 3, "bodyText": "Updated."})
        self.assertEqual(resp["id"], 3)
        self.assertEqual(resp["status"], "updated")

    # --- /deleteanswer ---

    def test_deleteanswer_echoes_id(self):
        resp = _mock_response("/deleteanswer", {"id": 4})
        self.assertEqual(resp["id"], 4)
        self.assertEqual(resp["status"], "deleted")

    # --- /summarize ---

    def test_summarize_by_url_returns_summary(self):
        resp = _mock_response("/summarize",
                               {"documentSpec": {"url": "https://example.com/doc"}})
        self.assertIn("summary", resp)
        self.assertIn("https://example.com/doc", resp["summary"])

    def test_summarize_by_id_returns_summary(self):
        resp = _mock_response("/summarize", {"documentSpec": {"id": "doc_123"}})
        self.assertIn("summary", resp)
        self.assertIn("doc_123", resp["summary"])

    # --- /listverifications ---

    def test_listverifications_returns_items(self):
        resp = _mock_response("/listverifications", {})
        self.assertIn("verifications", resp)
        self.assertGreater(len(resp["verifications"]), 0)

    def test_listverifications_each_has_required_fields(self):
        resp = _mock_response("/listverifications", {})
        for v in resp["verifications"]:
            self.assertIn("documentId", v)
            self.assertIn("title", v)
            self.assertIn("status", v)

    def test_listverifications_has_verified_and_unverified(self):
        resp = _mock_response("/listverifications", {})
        statuses = {v["status"] for v in resp["verifications"]}
        self.assertIn("VERIFIED", statuses)
        self.assertIn("UNVERIFIED", statuses)

    # --- /verify ---

    def test_verify_echoes_document_id(self):
        resp = _mock_response("/verify", {"documentId": "doc_42"})
        self.assertEqual(resp["documentId"], "doc_42")
        self.assertEqual(resp["status"], "VERIFIED")

    # --- /addverificationreminder ---

    def test_addverificationreminder_echoes_doc_id(self):
        resp = _mock_response("/addverificationreminder",
                               {"documentId": "doc_99", "remindInDays": 7})
        self.assertEqual(resp["documentId"], "doc_99")
        self.assertEqual(resp["status"], "reminder_set")

    # --- /messages ---

    def test_messages_returns_message_list(self):
        resp = _mock_response("/messages",
                               {"id": "msg_1", "idType": "MESSAGE_ID", "datasource": "slack"})
        self.assertIn("messages", resp)
        self.assertGreater(len(resp["messages"]), 0)

    def test_messages_has_text_and_author(self):
        resp = _mock_response("/messages",
                               {"id": "msg_1", "idType": "MESSAGE_ID", "datasource": "slack"})
        m = resp["messages"][0]
        self.assertIn("text", m)
        self.assertIn("author", m)

    # --- /activity ---

    def test_activity_reports_processed_count(self):
        body = {"events": [{"url": "https://ex.com", "action": "VIEW"},
                            {"url": "https://ex2.com", "action": "EDIT"}]}
        resp = _mock_response("/activity", body)
        self.assertEqual(resp["processed"], 2)

    def test_activity_ok_status(self):
        resp = _mock_response("/activity", {"events": []})
        self.assertEqual(resp["status"], "ok")

    # --- /insights ---

    def test_insights_overview_only(self):
        resp = _mock_response("/insights", {"overviewRequest": {}})
        self.assertIn("overviewResponse", resp)
        self.assertNotIn("assistantResponse", resp)
        self.assertNotIn("agentsResponse", resp)

    def test_insights_overview_fields(self):
        resp = _mock_response("/insights", {"overviewRequest": {}})
        ov = resp["overviewResponse"]
        for field in ("monthlyActiveUsers", "weeklyActiveUsers", "employeeCount",
                      "totalSignups", "searchSessionSatisfaction"):
            self.assertIn(field, ov)

    def test_insights_assistant_section(self):
        resp = _mock_response("/insights", {"overviewRequest": {}, "assistantRequest": {}})
        self.assertIn("assistantResponse", resp)
        ar = resp["assistantResponse"]
        self.assertIn("monthlyActiveUsers", ar)

    def test_insights_agents_section(self):
        resp = _mock_response("/insights", {"agentsRequest": {}})
        self.assertIn("agentsResponse", resp)
        self.assertIn("monthlyActiveUsers", resp["agentsResponse"])

    def test_insights_all_sections(self):
        resp = _mock_response("/insights",
                               {"overviewRequest": {}, "assistantRequest": {}, "agentsRequest": {}})
        self.assertIn("overviewResponse", resp)
        self.assertIn("assistantResponse", resp)
        self.assertIn("agentsResponse", resp)

    def test_insights_datasource_counts_present(self):
        resp = _mock_response("/insights", {"overviewRequest": {}})
        counts = resp["overviewResponse"]["searchDatasourceCounts"]
        self.assertIsInstance(counts, dict)
        self.assertGreater(len(counts), 0)

    def test_insights_empty_request_returns_empty(self):
        resp = _mock_response("/insights", {})
        self.assertNotIn("overviewResponse", resp)


class TestGleanClientNewMethods(unittest.TestCase):
    def setUp(self):
        self.sleep_patcher = patch("time.sleep")
        self.sleep_patcher.start()
        self.client = GleanClient(Config(mode="mock"))

    def tearDown(self):
        self.sleep_patcher.stop()

    def test_pin_delete_sends_correct_path(self):
        with patch("glean_code.client._mock_response") as mock_fn:
            mock_fn.return_value = {"id": "pin_1", "status": "unpinned"}
            self.client.pin_delete("pin_1")
        self.assertEqual(mock_fn.call_args[0][0], "/unpin")
        self.assertEqual(mock_fn.call_args[0][1]["id"], "pin_1")

    def test_collection_delete_sends_ids(self):
        with patch("glean_code.client._mock_response") as mock_fn:
            mock_fn.return_value = {"ids": [1, 2], "status": "deleted"}
            self.client.collection_delete([1, 2])
        self.assertEqual(mock_fn.call_args[0][1]["ids"], [1, 2])

    def test_shortcuts_list_no_query(self):
        with patch("glean_code.client._mock_response") as mock_fn:
            mock_fn.return_value = {"shortcuts": []}
            self.client.shortcuts_list()
        body = mock_fn.call_args[0][1]
        self.assertNotIn("query", body)
        self.assertEqual(body["pageSize"], 20)

    def test_shortcuts_list_with_query(self):
        with patch("glean_code.client._mock_response") as mock_fn:
            mock_fn.return_value = {"shortcuts": []}
            self.client.shortcuts_list(query="oncall")
        self.assertEqual(mock_fn.call_args[0][1]["query"], "oncall")

    def test_shortcut_get_sends_alias(self):
        with patch("glean_code.client._mock_response") as mock_fn:
            mock_fn.return_value = {"shortcut": {}}
            self.client.shortcut_get("pto")
        self.assertEqual(mock_fn.call_args[0][1]["alias"], "pto")

    def test_shortcut_create_body(self):
        with patch("glean_code.client._mock_response") as mock_fn:
            mock_fn.return_value = {"id": 1}
            self.client.shortcut_create("pto", "https://hr.com/pto",
                                         description="PTO policy", unlisted=True)
        body = mock_fn.call_args[0][1]
        data = body["data"]
        self.assertEqual(data["inputAlias"], "pto")
        self.assertEqual(data["destinationUrl"], "https://hr.com/pto")
        self.assertEqual(data["description"], "PTO policy")
        self.assertTrue(data["unlisted"])

    def test_shortcut_create_no_description(self):
        with patch("glean_code.client._mock_response") as mock_fn:
            mock_fn.return_value = {"id": 1}
            self.client.shortcut_create("x", "https://x.com")
        data = mock_fn.call_args[0][1]["data"]
        self.assertNotIn("description", data)

    def test_shortcut_update_only_alias(self):
        with patch("glean_code.client._mock_response") as mock_fn:
            mock_fn.return_value = {"id": 1}
            self.client.shortcut_update(1, alias="newpto")
        body = mock_fn.call_args[0][1]
        self.assertEqual(body["id"], 1)
        self.assertEqual(body["inputAlias"], "newpto")
        self.assertNotIn("destinationUrl", body)

    def test_shortcut_delete_sends_id(self):
        with patch("glean_code.client._mock_response") as mock_fn:
            mock_fn.return_value = {"id": 5}
            self.client.shortcut_delete(5)
        self.assertEqual(mock_fn.call_args[0][1]["id"], 5)

    def test_answers_list_calls_endpoint(self):
        with patch("glean_code.client._mock_response") as mock_fn:
            mock_fn.return_value = {"answers": []}
            self.client.answers_list()
        self.assertEqual(mock_fn.call_args[0][0], "/listanswers")

    def test_answer_get_sends_id(self):
        with patch("glean_code.client._mock_response") as mock_fn:
            mock_fn.return_value = {"answer": {}}
            self.client.answer_get(42)
        self.assertEqual(mock_fn.call_args[0][1]["id"], 42)

    def test_answer_create_body(self):
        with patch("glean_code.client._mock_response") as mock_fn:
            mock_fn.return_value = {"id": 1}
            self.client.answer_create("Q?", "A.", audience="eng")
        data = mock_fn.call_args[0][1]["data"]
        self.assertEqual(data["question"], "Q?")
        self.assertEqual(data["bodyText"], "A.")
        self.assertIn("audienceFilters", data)

    def test_answer_create_no_audience(self):
        with patch("glean_code.client._mock_response") as mock_fn:
            mock_fn.return_value = {"id": 1}
            self.client.answer_create("Q?", "A.")
        data = mock_fn.call_args[0][1]["data"]
        self.assertNotIn("audienceFilters", data)

    def test_answer_update_partial(self):
        with patch("glean_code.client._mock_response") as mock_fn:
            mock_fn.return_value = {"id": 1}
            self.client.answer_update(1, body_text="Updated answer.")
        body = mock_fn.call_args[0][1]
        self.assertEqual(body["id"], 1)
        self.assertEqual(body["bodyText"], "Updated answer.")
        self.assertNotIn("question", body)

    def test_answer_delete_sends_id(self):
        with patch("glean_code.client._mock_response") as mock_fn:
            mock_fn.return_value = {"id": 1}
            self.client.answer_delete(7)
        self.assertEqual(mock_fn.call_args[0][1]["id"], 7)

    def test_summarize_by_url(self):
        with patch("glean_code.client._mock_response") as mock_fn:
            mock_fn.return_value = {"summary": "..."}
            self.client.summarize(url="https://example.com/doc")
        body = mock_fn.call_args[0][1]
        self.assertEqual(body["documentSpec"]["url"], "https://example.com/doc")

    def test_summarize_by_id(self):
        with patch("glean_code.client._mock_response") as mock_fn:
            mock_fn.return_value = {"summary": "..."}
            self.client.summarize(doc_id="doc_123")
        body = mock_fn.call_args[0][1]
        self.assertEqual(body["documentSpec"]["id"], "doc_123")

    def test_summarize_with_query(self):
        with patch("glean_code.client._mock_response") as mock_fn:
            mock_fn.return_value = {"summary": "..."}
            self.client.summarize(url="https://x.com", query="key findings")
        body = mock_fn.call_args[0][1]
        self.assertEqual(body["query"], "key findings")

    def test_verification_list_default(self):
        with patch("glean_code.client._mock_response") as mock_fn:
            mock_fn.return_value = {"verifications": []}
            self.client.verification_list()
        body = mock_fn.call_args[0][1]
        self.assertNotIn("count", body)

    def test_verification_list_with_count(self):
        with patch("glean_code.client._mock_response") as mock_fn:
            mock_fn.return_value = {"verifications": []}
            self.client.verification_list(count=10)
        self.assertEqual(mock_fn.call_args[0][1]["count"], 10)

    def test_verification_verify_body(self):
        with patch("glean_code.client._mock_response") as mock_fn:
            mock_fn.return_value = {"status": "VERIFIED"}
            self.client.verification_verify("doc_1", action="VERIFY")
        body = mock_fn.call_args[0][1]
        self.assertEqual(body["documentId"], "doc_1")
        self.assertEqual(body["action"], "VERIFY")

    def test_verification_verify_no_action(self):
        with patch("glean_code.client._mock_response") as mock_fn:
            mock_fn.return_value = {"status": "VERIFIED"}
            self.client.verification_verify("doc_1")
        body = mock_fn.call_args[0][1]
        self.assertNotIn("action", body)

    def test_verification_remind_full(self):
        with patch("glean_code.client._mock_response") as mock_fn:
            mock_fn.return_value = {"status": "reminder_set"}
            self.client.verification_remind("doc_1", remind_in_days=7,
                                             assignee="bob@example.com", reason="stale")
        body = mock_fn.call_args[0][1]
        self.assertEqual(body["documentId"], "doc_1")
        self.assertEqual(body["remindInDays"], 7)
        self.assertEqual(body["assignee"], "bob@example.com")
        self.assertEqual(body["reason"], "stale")

    def test_messages_get_body(self):
        with patch("glean_code.client._mock_response") as mock_fn:
            mock_fn.return_value = {"messages": []}
            self.client.messages_get("msg_1", "MESSAGE_ID", "slack", direction="BEFORE")
        body = mock_fn.call_args[0][1]
        self.assertEqual(body["id"], "msg_1")
        self.assertEqual(body["idType"], "MESSAGE_ID")
        self.assertEqual(body["datasource"], "slack")
        self.assertEqual(body["direction"], "BEFORE")

    def test_activity_report_includes_event(self):
        with patch("glean_code.client._mock_response") as mock_fn:
            mock_fn.return_value = {"processed": 1}
            self.client.activity_report("https://example.com/doc", action="EDIT")
        events = mock_fn.call_args[0][1]["events"]
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["url"], "https://example.com/doc")
        self.assertEqual(events[0]["action"], "EDIT")
        self.assertIn("timestamp", events[0])

    def test_insights_overview_only(self):
        with patch("glean_code.client._mock_response") as mock_fn:
            mock_fn.return_value = {}
            self.client.insights(overview=True, assistant=False, agents=False)
        body = mock_fn.call_args[0][1]
        self.assertIn("overviewRequest", body)
        self.assertNotIn("assistantRequest", body)
        self.assertNotIn("agentsRequest", body)

    def test_insights_all_sections(self):
        with patch("glean_code.client._mock_response") as mock_fn:
            mock_fn.return_value = {}
            self.client.insights(overview=True, assistant=True, agents=True)
        body = mock_fn.call_args[0][1]
        self.assertIn("overviewRequest", body)
        self.assertIn("assistantRequest", body)
        self.assertIn("agentsRequest", body)

    def test_insights_disable_per_user(self):
        with patch("glean_code.client._mock_response") as mock_fn:
            mock_fn.return_value = {}
            self.client.insights(disable_per_user=True)
        body = mock_fn.call_args[0][1]
        self.assertTrue(body["disablePerUserInsights"])

    def test_insights_locale(self):
        with patch("glean_code.client._mock_response") as mock_fn:
            mock_fn.return_value = {}
            self.client.insights(locale="en-US")
        body = mock_fn.call_args[0][1]
        self.assertEqual(body["locale"], "en-US")


if __name__ == "__main__":
    unittest.main()
