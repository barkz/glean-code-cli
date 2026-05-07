"""Extended command handler tests covering features not in test_commands.py.

Covers: status, clear, help, datasources.list/status, indexing.rotate-token,
autocomplete, recommendations, feedback, entities.list,
pins.delete, collections.delete, shortcuts.*, answers.*, summarize,
verification.*, messages.get, activity.report, insights,
scaffold (--output flag), _fmt_ts, _render_insights, _export_insights_csv,
_print_datasource_status, Session.refresh_client.
"""
import csv
import sys
import tempfile
import time
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from glean_code.commands import (
    HANDLERS, Session, _fmt_ts, _render_insights, _export_insights_csv,
    _print_datasource_status,
)
from glean_code.client import GleanError
from glean_code.config import Config


def _sess(**cfg):
    s = Session(Config(mode="mock", **cfg))
    s.client = MagicMock()
    return s


def _output(fn, *args, **kwargs):
    """Capture print output from a handler call."""
    lines = []
    with patch("builtins.print", side_effect=lambda *a, **k: lines.append(" ".join(str(x) for x in a))):
        fn(*args, **kwargs)
    return "\n".join(lines)


# ---- status ----

class TestCmdStatus(unittest.TestCase):
    def test_shows_instance(self):
        s = _sess(instance="acme-be.glean.com")
        out = _output(HANDLERS["status"], s, [], {})
        self.assertIn("acme-be.glean.com", out)

    def test_shows_mode(self):
        s = _sess()  # default is mock
        out = _output(HANDLERS["status"], s, [], {})
        self.assertIn("mock", out)

    def test_shows_current_chat_id(self):
        s = _sess()
        s.current_chat_id = "thread-abc"
        out = _output(HANDLERS["status"], s, [], {})
        self.assertIn("thread-abc", out)

    def test_token_shows_set_when_configured(self):
        s = _sess(api_token="supersecret")
        out = _output(HANDLERS["status"], s, [], {})
        self.assertIn("set", out)

    def test_no_token_shows_unset(self):
        s = _sess()
        out = _output(HANDLERS["status"], s, [], {})
        self.assertIn("unset", out)


# ---- clear ----

class TestCmdClear(unittest.TestCase):
    def test_prints_escape_sequence(self):
        s = _sess()
        captured = []
        with patch("builtins.print", side_effect=lambda *a, **k: captured.append(a)):
            HANDLERS["clear"](s, [], {})
        # Each element of captured is a tuple of positional args; check first arg of each call
        self.assertTrue(any("\033[2J" in args[0] for args in captured if args))


# ---- help ----

class TestCmdHelp(unittest.TestCase):
    def test_no_args_shows_all_groups(self):
        s = _sess()
        out = _output(HANDLERS["help"], s, [], {})
        self.assertIn("search", out.lower())

    def test_known_command_shows_usage(self):
        s = _sess()
        out = _output(HANDLERS["help"], s, ["search"], {})
        self.assertIn("search", out.lower())
        self.assertIn("Usage", out)

    def test_unknown_command_shows_error(self):
        s = _sess()
        out = _output(HANDLERS["help"], s, ["no_such_command_xyz"], {})
        self.assertIn("Unknown", out)

    def test_slash_prefix_stripped(self):
        s = _sess()
        # /help /search should work same as /help search
        out1 = _output(HANDLERS["help"], s, ["/search"], {})
        out2 = _output(HANDLERS["help"], s, ["search"], {})
        self.assertEqual(out1, out2)


# ---- datasources.list ----

class TestCmdDatasourcesList(unittest.TestCase):
    def test_calls_client(self):
        s = _sess()
        s.client.list_datasources.return_value = {"datasources": []}
        _output(HANDLERS["datasources.list"], s, [], {})
        s.client.list_datasources.assert_called_once()

    def test_empty_shows_message(self):
        s = _sess()
        s.client.list_datasources.return_value = {"datasources": []}
        out = _output(HANDLERS["datasources.list"], s, [], {})
        self.assertIn("no datasource", out.lower())

    def test_bullet_list_default(self):
        s = _sess()
        s.client.list_datasources.return_value = {
            "datasources": [{"name": "gdrive", "count": 100}, {"name": "slack", "count": 50}]
        }
        out = _output(HANDLERS["datasources.list"], s, [], {})
        self.assertIn("gdrive", out)
        self.assertIn("slack", out)

    def test_with_counts_flag_shows_counts(self):
        s = _sess()
        s.client.list_datasources.return_value = {
            "datasources": [{"name": "gdrive", "count": 842}]
        }
        out = _output(HANDLERS["datasources.list"], s, [], {"with-counts": True})
        self.assertIn("842", out)

    def test_with_status_requires_indexing_token(self):
        s = _sess()  # no indexing_token
        s.client.list_datasources.return_value = {
            "datasources": [{"name": "gdrive", "count": 10}]
        }
        out = _output(HANDLERS["datasources.list"], s, [], {"with-status": True})
        self.assertIn("indexing token", out.lower())

    def test_handles_glean_error(self):
        s = _sess()
        s.client.list_datasources.side_effect = GleanError("server error")
        out = _output(HANDLERS["datasources.list"], s, [], {})
        self.assertIn("server error", out)


# ---- datasources.status ----

class TestCmdDatasourcesStatus(unittest.TestCase):
    def test_requires_datasource_name(self):
        s = _sess(indexing_token="tok")
        out = _output(HANDLERS["datasources.status"], s, [], {})
        self.assertIn("Usage", out)

    def test_requires_indexing_token(self):
        s = _sess()  # no indexing_token
        out = _output(HANDLERS["datasources.status"], s, ["gdrive"], {})
        self.assertIn("indexing token", out.lower())

    def test_calls_client_with_datasource(self):
        s = _sess(indexing_token="idx")
        s.client.datasource_status.return_value = {"documents": {}}
        _output(HANDLERS["datasources.status"], s, ["gdrive"], {})
        s.client.datasource_status.assert_called_once_with("gdrive")


# ---- indexing.rotate-token ----

class TestCmdIndexingRotateToken(unittest.TestCase):
    def test_requires_indexing_token(self):
        s = _sess()
        out = _output(HANDLERS["indexing.rotate-token"], s, [], {})
        self.assertIn("No indexing token", out)

    def test_calls_rotate_and_shows_secret(self):
        s = _sess(indexing_token="old_tok")
        s.client.rotate_indexing_token.return_value = {
            "rawSecret": "new_secret_abc",
            "createdAt": "2024-01-01",
            "rotationPeriodMinutes": 1440,
        }
        out = _output(HANDLERS["indexing.rotate-token"], s, [], {})
        self.assertIn("new_secret_abc", out)
        s.client.rotate_indexing_token.assert_called_once()


# ---- autocomplete ----

class TestCmdAutocomplete(unittest.TestCase):
    def test_requires_partial(self):
        s = _sess()
        out = _output(HANDLERS["autocomplete"], s, [], {})
        self.assertIn("Usage", out)

    def test_shows_suggestions(self):
        s = _sess()
        s.client.autocomplete.return_value = {
            "results": [{"suggestion": "eng report"}, {"suggestion": "eng metrics"}]
        }
        out = _output(HANDLERS["autocomplete"], s, ["eng"], {})
        self.assertIn("eng report", out)
        self.assertIn("eng metrics", out)

    def test_no_suggestions_message(self):
        s = _sess()
        s.client.autocomplete.return_value = {"results": []}
        out = _output(HANDLERS["autocomplete"], s, ["xyz"], {})
        self.assertIn("no suggestions", out.lower())


# ---- recommendations ----

class TestCmdRecommendations(unittest.TestCase):
    def test_calls_client(self):
        s = _sess()
        s.client.recommendations.return_value = {"results": []}
        _output(HANDLERS["recommendations"], s, [], {})
        s.client.recommendations.assert_called_once_with(user=None)

    def test_passes_user_flag(self):
        s = _sess()
        s.client.recommendations.return_value = {"results": []}
        _output(HANDLERS["recommendations"], s, [], {"user": "alice@example.com"})
        s.client.recommendations.assert_called_once_with(user="alice@example.com")


# ---- feedback ----

class TestCmdFeedback(unittest.TestCase):
    def test_requires_token_and_rating(self):
        s = _sess()
        out = _output(HANDLERS["feedback"], s, ["only-one-arg"], {})
        self.assertIn("Usage", out)

    def test_calls_client(self):
        s = _sess()
        s.client.feedback.return_value = {"status": "ok"}
        _output(HANDLERS["feedback"], s, ["tok_1", "THUMBS_UP"], {})
        s.client.feedback.assert_called_once_with("tok_1", "THUMBS_UP", comments=None)

    def test_passes_comment_flag(self):
        s = _sess()
        s.client.feedback.return_value = {"status": "ok"}
        _output(HANDLERS["feedback"], s, ["tok_1", "THUMBS_DOWN"], {"comment": "not helpful"})
        s.client.feedback.assert_called_once_with("tok_1", "THUMBS_DOWN", comments="not helpful")


# ---- entities.list ----

class TestCmdEntitiesList(unittest.TestCase):
    def test_calls_client_defaults(self):
        s = _sess()
        s.client.list_entities.return_value = {"results": []}
        _output(HANDLERS["entities.list"], s, [], {})
        s.client.list_entities.assert_called_once_with(kind="PEOPLE", page_size=10, query=None)

    def test_passes_kind_flag(self):
        s = _sess()
        s.client.list_entities.return_value = {"results": []}
        _output(HANDLERS["entities.list"], s, [], {"kind": "TEAMS"})
        s.client.list_entities.assert_called_once_with(kind="TEAMS", page_size=10, query=None)

    def test_passes_query_flag(self):
        s = _sess()
        s.client.list_entities.return_value = {"results": []}
        _output(HANDLERS["entities.list"], s, [], {"query": "eng"})
        s.client.list_entities.assert_called_once_with(kind="PEOPLE", page_size=10, query="eng")


# ---- pins.delete ----

class TestCmdPinsDelete(unittest.TestCase):
    def test_requires_id(self):
        s = _sess()
        out = _output(HANDLERS["pins.delete"], s, [], {})
        self.assertIn("Usage", out)

    def test_calls_client(self):
        s = _sess()
        s.client.pin_delete.return_value = {"id": "pin_1", "status": "unpinned"}
        _output(HANDLERS["pins.delete"], s, ["pin_1"], {})
        s.client.pin_delete.assert_called_once_with("pin_1")


# ---- collections.delete ----

class TestCmdCollectionsDelete(unittest.TestCase):
    def test_requires_id(self):
        s = _sess()
        out = _output(HANDLERS["collections.delete"], s, [], {})
        self.assertIn("Usage", out)

    def test_rejects_non_integer_id(self):
        s = _sess()
        out = _output(HANDLERS["collections.delete"], s, ["not_int"], {})
        self.assertIn("integer", out.lower())

    def test_calls_client_with_int_ids(self):
        s = _sess()
        s.client.collection_delete.return_value = {"ids": [1, 2], "status": "deleted"}
        _output(HANDLERS["collections.delete"], s, ["1", "2"], {})
        s.client.collection_delete.assert_called_once_with([1, 2])


# ---- shortcuts.* ----

class TestCmdShortcuts(unittest.TestCase):
    def test_list_calls_client(self):
        s = _sess()
        s.client.shortcuts_list.return_value = {"shortcuts": []}
        _output(HANDLERS["shortcuts.list"], s, [], {})
        s.client.shortcuts_list.assert_called_once()

    def test_list_empty_shows_message(self):
        s = _sess()
        s.client.shortcuts_list.return_value = {"shortcuts": []}
        out = _output(HANDLERS["shortcuts.list"], s, [], {})
        self.assertIn("no shortcuts", out.lower())

    def test_list_shows_aliases(self):
        s = _sess()
        s.client.shortcuts_list.return_value = {
            "shortcuts": [{"id": 1, "inputAlias": "pto",
                           "destinationUrl": "https://hr.com/pto", "description": "PTO"}]
        }
        out = _output(HANDLERS["shortcuts.list"], s, [], {})
        self.assertIn("pto", out)

    def test_get_requires_alias(self):
        s = _sess()
        out = _output(HANDLERS["shortcuts.get"], s, [], {})
        self.assertIn("Usage", out)

    def test_get_calls_client(self):
        s = _sess()
        s.client.shortcut_get.return_value = {
            "shortcut": {"id": 1, "inputAlias": "pto",
                         "destinationUrl": "https://hr.com/pto", "description": "PTO"}
        }
        _output(HANDLERS["shortcuts.get"], s, ["pto"], {})
        s.client.shortcut_get.assert_called_once_with("pto")

    def test_create_requires_alias_and_url(self):
        s = _sess()
        out = _output(HANDLERS["shortcuts.create"], s, [], {"alias": "pto"})
        self.assertIn("Usage", out)

    def test_create_calls_client(self):
        s = _sess()
        s.client.shortcut_create.return_value = {"id": 42, "status": "created"}
        _output(HANDLERS["shortcuts.create"], s, [],
                {"alias": "pto", "url": "https://hr.com/pto"})
        s.client.shortcut_create.assert_called_once_with(
            alias="pto", url="https://hr.com/pto", description=None, unlisted=False
        )

    def test_create_passes_description(self):
        s = _sess()
        s.client.shortcut_create.return_value = {"id": 42}
        _output(HANDLERS["shortcuts.create"], s, [],
                {"alias": "pto", "url": "https://hr.com/pto", "description": "PTO docs"})
        call = s.client.shortcut_create.call_args
        self.assertEqual(call[1]["description"], "PTO docs")

    def test_create_passes_unlisted_flag(self):
        s = _sess()
        s.client.shortcut_create.return_value = {"id": 42}
        _output(HANDLERS["shortcuts.create"], s, [],
                {"alias": "pto", "url": "https://hr.com/pto", "unlisted": True})
        call = s.client.shortcut_create.call_args
        self.assertTrue(call[1]["unlisted"])

    def test_update_requires_id(self):
        s = _sess()
        out = _output(HANDLERS["shortcuts.update"], s, [], {})
        self.assertIn("Usage", out)

    def test_update_rejects_non_int_id(self):
        s = _sess()
        out = _output(HANDLERS["shortcuts.update"], s, ["not_int"], {"alias": "new"})
        self.assertIn("integer", out.lower())

    def test_update_calls_client(self):
        s = _sess()
        s.client.shortcut_update.return_value = {"id": 1, "status": "updated"}
        _output(HANDLERS["shortcuts.update"], s, ["1"], {"alias": "newpto", "url": "https://x.com"})
        s.client.shortcut_update.assert_called_once_with(
            shortcut_id=1, alias="newpto", url="https://x.com", description=None
        )

    def test_delete_requires_id(self):
        s = _sess()
        out = _output(HANDLERS["shortcuts.delete"], s, [], {})
        self.assertIn("Usage", out)

    def test_delete_rejects_non_int(self):
        s = _sess()
        out = _output(HANDLERS["shortcuts.delete"], s, ["abc"], {})
        self.assertIn("integer", out.lower())

    def test_delete_calls_client(self):
        s = _sess()
        s.client.shortcut_delete.return_value = {"id": 1, "status": "deleted"}
        _output(HANDLERS["shortcuts.delete"], s, ["1"], {})
        s.client.shortcut_delete.assert_called_once_with(1)


# ---- answers.* ----

class TestCmdAnswers(unittest.TestCase):
    def test_list_calls_client(self):
        s = _sess()
        s.client.answers_list.return_value = {"answers": []}
        _output(HANDLERS["answers.list"], s, [], {})
        s.client.answers_list.assert_called_once()

    def test_list_empty_shows_message(self):
        s = _sess()
        s.client.answers_list.return_value = {"answers": []}
        out = _output(HANDLERS["answers.list"], s, [], {})
        self.assertIn("no answers", out.lower())

    def test_list_shows_questions(self):
        s = _sess()
        s.client.answers_list.return_value = {
            "answers": [{"id": 1, "question": "What is PTO?", "bodyText": "20 days"}]
        }
        out = _output(HANDLERS["answers.list"], s, [], {})
        self.assertIn("What is PTO?", out)

    def test_get_requires_id(self):
        s = _sess()
        out = _output(HANDLERS["answers.get"], s, [], {})
        self.assertIn("Usage", out)

    def test_get_rejects_non_int(self):
        s = _sess()
        out = _output(HANDLERS["answers.get"], s, ["abc"], {})
        self.assertIn("integer", out.lower())

    def test_get_calls_client(self):
        s = _sess()
        s.client.answer_get.return_value = {
            "answer": {"id": 1, "question": "Q?", "bodyText": "A."}
        }
        _output(HANDLERS["answers.get"], s, ["1"], {})
        s.client.answer_get.assert_called_once_with(1)

    def test_create_requires_question_and_body(self):
        s = _sess()
        out = _output(HANDLERS["answers.create"], s, [], {"question": "Q?"})
        self.assertIn("Usage", out)

    def test_create_calls_client(self):
        s = _sess()
        s.client.answer_create.return_value = {"id": 5, "status": "created"}
        _output(HANDLERS["answers.create"], s, [],
                {"question": "What is PTO?", "body": "20 days"})
        s.client.answer_create.assert_called_once_with(
            "What is PTO?", "20 days", audience=None
        )

    def test_update_requires_id(self):
        s = _sess()
        out = _output(HANDLERS["answers.update"], s, [], {})
        self.assertIn("Usage", out)

    def test_update_rejects_non_int(self):
        s = _sess()
        out = _output(HANDLERS["answers.update"], s, ["xyz"], {})
        self.assertIn("integer", out.lower())

    def test_update_calls_client(self):
        s = _sess()
        s.client.answer_update.return_value = {"id": 1, "status": "updated"}
        _output(HANDLERS["answers.update"], s, ["1"], {"body": "Updated answer."})
        s.client.answer_update.assert_called_once_with(
            1, question=None, body_text="Updated answer."
        )

    def test_delete_requires_id(self):
        s = _sess()
        out = _output(HANDLERS["answers.delete"], s, [], {})
        self.assertIn("Usage", out)

    def test_delete_rejects_non_int(self):
        s = _sess()
        out = _output(HANDLERS["answers.delete"], s, ["abc"], {})
        self.assertIn("integer", out.lower())

    def test_delete_calls_client(self):
        s = _sess()
        s.client.answer_delete.return_value = {"id": 1, "status": "deleted"}
        _output(HANDLERS["answers.delete"], s, ["1"], {})
        s.client.answer_delete.assert_called_once_with(1)


# ---- summarize ----

class TestCmdSummarize(unittest.TestCase):
    def test_requires_url_or_id(self):
        s = _sess()
        out = _output(HANDLERS["summarize"], s, [], {})
        self.assertIn("Usage", out)

    def test_by_url_calls_client(self):
        s = _sess()
        s.client.summarize.return_value = {"summary": "A brief overview."}
        out = _output(HANDLERS["summarize"], s, [], {"url": "https://example.com/doc"})
        self.assertIn("A brief overview.", out)
        s.client.summarize.assert_called_once_with(
            url="https://example.com/doc", doc_id=None, query=None
        )

    def test_by_id_calls_client(self):
        s = _sess()
        s.client.summarize.return_value = {"summary": "Summary text."}
        _output(HANDLERS["summarize"], s, [], {"id": "doc_123"})
        s.client.summarize.assert_called_once_with(
            url=None, doc_id="doc_123", query=None
        )

    def test_passes_query_flag(self):
        s = _sess()
        s.client.summarize.return_value = {"summary": "Focused summary."}
        _output(HANDLERS["summarize"], s, [], {"url": "https://ex.com", "query": "key points"})
        s.client.summarize.assert_called_once_with(
            url="https://ex.com", doc_id=None, query="key points"
        )

    def test_handles_glean_error(self):
        s = _sess()
        s.client.summarize.side_effect = GleanError("not found")
        out = _output(HANDLERS["summarize"], s, [], {"url": "https://x.com"})
        self.assertIn("not found", out)


# ---- verification.* ----

class TestCmdVerification(unittest.TestCase):
    def test_list_calls_client(self):
        s = _sess()
        s.client.verification_list.return_value = {"verifications": []}
        _output(HANDLERS["verification.list"], s, [], {})
        s.client.verification_list.assert_called_once()

    def test_list_empty_shows_message(self):
        s = _sess()
        s.client.verification_list.return_value = {"verifications": []}
        out = _output(HANDLERS["verification.list"], s, [], {})
        self.assertIn("no documents", out.lower())

    def test_list_shows_documents(self):
        s = _sess()
        s.client.verification_list.return_value = {
            "verifications": [
                {"documentId": "doc_1", "title": "Q2 Plan",
                 "status": "UNVERIFIED", "lastVerifiedTs": None}
            ]
        }
        out = _output(HANDLERS["verification.list"], s, [], {})
        self.assertIn("Q2 Plan", out)

    def test_list_count_flag(self):
        s = _sess()
        s.client.verification_list.return_value = {"verifications": []}
        _output(HANDLERS["verification.list"], s, [], {"count": "5"})
        s.client.verification_list.assert_called_once_with(count=5)

    def test_verify_requires_doc_id(self):
        s = _sess()
        out = _output(HANDLERS["verification.verify"], s, [], {})
        self.assertIn("Usage", out)

    def test_verify_calls_client(self):
        s = _sess()
        s.client.verification_verify.return_value = {"documentId": "doc_1", "status": "VERIFIED"}
        _output(HANDLERS["verification.verify"], s, ["doc_1"], {})
        s.client.verification_verify.assert_called_once_with("doc_1", action=None)

    def test_verify_passes_action_flag(self):
        s = _sess()
        s.client.verification_verify.return_value = {"documentId": "doc_1", "status": "UNVERIFIED"}
        _output(HANDLERS["verification.verify"], s, ["doc_1"], {"action": "UNVERIFY"})
        s.client.verification_verify.assert_called_once_with("doc_1", action="UNVERIFY")

    def test_remind_requires_doc_id(self):
        s = _sess()
        out = _output(HANDLERS["verification.remind"], s, [], {})
        self.assertIn("Usage", out)

    def test_remind_calls_client_with_defaults(self):
        s = _sess()
        s.client.verification_remind.return_value = {"status": "reminder_set"}
        _output(HANDLERS["verification.remind"], s, ["doc_1"], {})
        s.client.verification_remind.assert_called_once_with(
            "doc_1", remind_in_days=30, assignee=None, reason=None
        )

    def test_remind_passes_all_flags(self):
        s = _sess()
        s.client.verification_remind.return_value = {"status": "reminder_set"}
        _output(HANDLERS["verification.remind"], s, ["doc_1"],
                {"days": "7", "assignee": "bob@example.com", "reason": "stale"})
        s.client.verification_remind.assert_called_once_with(
            "doc_1", remind_in_days=7, assignee="bob@example.com", reason="stale"
        )


# ---- messages.get ----

class TestCmdMessagesGet(unittest.TestCase):
    def test_requires_id_and_datasource(self):
        s = _sess()
        out = _output(HANDLERS["messages.get"], s, [], {"id": "msg_1"})
        self.assertIn("Usage", out)

    def test_calls_client(self):
        s = _sess()
        s.client.messages_get.return_value = {"messages": []}
        _output(HANDLERS["messages.get"], s, [],
                {"id": "msg_1", "datasource": "slack"})
        s.client.messages_get.assert_called_once_with(
            msg_id="msg_1", id_type="MESSAGE_ID",
            datasource="slack", direction=None
        )

    def test_passes_direction_flag(self):
        s = _sess()
        s.client.messages_get.return_value = {"messages": []}
        _output(HANDLERS["messages.get"], s, [],
                {"id": "msg_1", "datasource": "slack", "direction": "BEFORE"})
        call = s.client.messages_get.call_args
        self.assertEqual(call[1]["direction"], "BEFORE")

    def test_no_messages_shows_message(self):
        s = _sess()
        s.client.messages_get.return_value = {"messages": []}
        out = _output(HANDLERS["messages.get"], s, [],
                      {"id": "msg_1", "datasource": "slack"})
        self.assertIn("no messages", out.lower())

    def test_shows_message_text(self):
        s = _sess()
        s.client.messages_get.return_value = {
            "messages": [{"id": "m1", "text": "hello world", "author": "alice@example.com"}]
        }
        out = _output(HANDLERS["messages.get"], s, [],
                      {"id": "m1", "datasource": "slack"})
        self.assertIn("hello world", out)


# ---- activity.report ----

class TestCmdActivityReport(unittest.TestCase):
    def test_requires_url(self):
        s = _sess()
        out = _output(HANDLERS["activity.report"], s, [], {})
        self.assertIn("Usage", out)

    def test_url_from_flag(self):
        s = _sess()
        s.client.activity_report.return_value = {"processed": 1}
        _output(HANDLERS["activity.report"], s, [], {"url": "https://example.com/doc"})
        s.client.activity_report.assert_called_once_with("https://example.com/doc", action="VIEW")

    def test_url_from_positional(self):
        s = _sess()
        s.client.activity_report.return_value = {"processed": 1}
        _output(HANDLERS["activity.report"], s, ["https://example.com/doc"], {})
        s.client.activity_report.assert_called_once_with("https://example.com/doc", action="VIEW")

    def test_action_flag(self):
        s = _sess()
        s.client.activity_report.return_value = {"processed": 1}
        _output(HANDLERS["activity.report"], s, [],
                {"url": "https://example.com", "action": "edit"})
        s.client.activity_report.assert_called_once_with("https://example.com", action="EDIT")

    def test_shows_processed_count(self):
        s = _sess()
        s.client.activity_report.return_value = {"processed": 3}
        out = _output(HANDLERS["activity.report"], s, [],
                      {"url": "https://example.com"})
        self.assertIn("3", out)


# ---- insights ----

class TestCmdInsights(unittest.TestCase):
    def _mock_resp(self):
        return {
            "overviewResponse": {
                "monthlyActiveUsers": 312, "weeklyActiveUsers": 148,
                "employeeCount": 520, "totalSignups": 401,
                "searchSessionSatisfaction": 0.87,
                "lastUpdatedTs": int(time.time()) - 3600,
                "searchDatasourceCounts": {"gdrive": 100, "slack": 50},
            }
        }

    def test_default_calls_overview(self):
        s = _sess()
        s.client.insights.return_value = self._mock_resp()
        _output(HANDLERS["insights"], s, [], {})
        call = s.client.insights.call_args
        self.assertTrue(call[1]["overview"])
        self.assertFalse(call[1]["assistant"])
        self.assertFalse(call[1]["agents"])

    def test_assistant_flag(self):
        s = _sess()
        s.client.insights.return_value = {}
        _output(HANDLERS["insights"], s, [], {"assistant": True})
        call = s.client.insights.call_args
        self.assertTrue(call[1]["assistant"])

    def test_all_flag_enables_all(self):
        s = _sess()
        s.client.insights.return_value = {}
        _output(HANDLERS["insights"], s, [], {"all": True})
        call = s.client.insights.call_args
        self.assertTrue(call[1]["assistant"])
        self.assertTrue(call[1]["agents"])

    def test_no_per_user_flag(self):
        s = _sess()
        s.client.insights.return_value = {}
        _output(HANDLERS["insights"], s, [], {"no-per-user": True})
        call = s.client.insights.call_args
        self.assertTrue(call[1]["disable_per_user"])

    def test_export_writes_csv(self):
        s = _sess()
        s.client.insights.return_value = self._mock_resp()
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            path = f.name
        _output(HANDLERS["insights"], s, [], {"export": path})
        with open(path) as f:
            reader = csv.reader(f)
            rows = list(reader)
        self.assertEqual(rows[0], ["section", "metric", "value"])
        self.assertGreater(len(rows), 1)

    def test_handles_glean_error(self):
        s = _sess()
        s.client.insights.side_effect = GleanError("forbidden")
        out = _output(HANDLERS["insights"], s, [], {})
        self.assertIn("forbidden", out)


# ---- scaffold (--output flag, EOFError cancel) ----

class TestCmdScaffoldExtended(unittest.TestCase):
    def test_invalid_template_shows_error(self):
        s = _sess()
        out = _output(HANDLERS["scaffold"], s, ["invalid_template"], {})
        self.assertIn("Usage", out)

    def test_output_flag_skips_prompt(self):
        s = _sess()
        with tempfile.TemporaryDirectory() as tmpdir:
            _output(HANDLERS["scaffold"], s, ["chat"], {"output": tmpdir})
            self.assertTrue((Path(tmpdir) / "glean_chat.py").exists())

    def test_eoferror_on_dir_prompt_cancels(self):
        s = _sess()
        with patch("builtins.input", side_effect=EOFError):
            out = _output(HANDLERS["scaffold"], s, ["chat"], {})
        self.assertIn("Cancelled", out)

    def test_n_response_to_create_dir_cancels(self):
        s = _sess()
        with tempfile.TemporaryDirectory() as tmpdir:
            nonexistent = str(Path(tmpdir) / "newdir")
            with patch("builtins.input", side_effect=["n"]):
                out = _output(HANDLERS["scaffold"], s, ["chat"], {"output": nonexistent})
        self.assertIn("Cancelled", out)


# ---- _fmt_ts ----

class TestFmtTs(unittest.TestCase):
    def test_none_returns_dash(self):
        self.assertEqual(_fmt_ts(None), "—")

    def test_zero_returns_dash(self):
        self.assertEqual(_fmt_ts(0), "—")

    def test_valid_timestamp_returns_formatted(self):
        # Use a known timestamp
        result = _fmt_ts(1700000000)
        self.assertRegex(result, r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}")

    def test_recent_timestamp_not_dash(self):
        ts = int(time.time()) - 3600
        result = _fmt_ts(ts)
        self.assertNotEqual(result, "—")


# ---- _render_insights ----

class TestRenderInsights(unittest.TestCase):
    def test_shows_mau_from_overview(self):
        resp = {
            "overviewResponse": {
                "monthlyActiveUsers": 500, "weeklyActiveUsers": 200,
                "employeeCount": 1000, "totalSignups": 800,
                "searchSessionSatisfaction": 0.9,
                "lastUpdatedTs": None,
                "searchDatasourceCounts": {},
            }
        }
        with patch("glean_code.ui.supports_colour", return_value=False):
            out = _output(_render_insights, resp)
        self.assertIn("500", out)
        self.assertIn("Overview", out)

    def test_shows_assistant_section(self):
        resp = {
            "assistantResponse": {
                "monthlyActiveUsers": 100, "weeklyActiveUsers": 50,
                "lastUpdatedTs": None,
            }
        }
        with patch("glean_code.ui.supports_colour", return_value=False):
            out = _output(_render_insights, resp)
        self.assertIn("Assistant", out)

    def test_shows_agents_section(self):
        resp = {
            "agentsResponse": {
                "monthlyActiveUsers": 30, "weeklyActiveUsers": 10,
                "lastUpdatedTs": None,
            }
        }
        with patch("glean_code.ui.supports_colour", return_value=False):
            out = _output(_render_insights, resp)
        self.assertIn("Agents", out)

    def test_empty_response_shows_no_data(self):
        with patch("glean_code.ui.supports_colour", return_value=False):
            out = _output(_render_insights, {})
        self.assertIn("no insights", out.lower())

    def test_datasource_counts_shown(self):
        resp = {
            "overviewResponse": {
                "monthlyActiveUsers": 100, "weeklyActiveUsers": 50,
                "employeeCount": 200, "totalSignups": 180,
                "searchSessionSatisfaction": None,
                "lastUpdatedTs": None,
                "searchDatasourceCounts": {"gdrive": 840, "slack": 600},
            }
        }
        with patch("glean_code.ui.supports_colour", return_value=False):
            out = _output(_render_insights, resp)
        self.assertIn("gdrive", out)
        self.assertIn("840", out)


# ---- _export_insights_csv ----

class TestExportInsightsCsv(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.path = str(Path(self.tmpdir.name) / "insights.csv")

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_creates_csv_with_header(self):
        _export_insights_csv({}, self.path)
        with open(self.path) as f:
            rows = list(csv.reader(f))
        self.assertEqual(rows[0], ["section", "metric", "value"])

    def test_overview_rows_written(self):
        resp = {
            "overviewResponse": {
                "monthlyActiveUsers": 312, "weeklyActiveUsers": 148,
                "employeeCount": 520, "totalSignups": 401,
                "searchSessionSatisfaction": 0.87,
                "lastUpdatedTs": None,
                "searchDatasourceCounts": {"gdrive": 100},
            }
        }
        _export_insights_csv(resp, self.path)
        with open(self.path) as f:
            content = f.read()
        self.assertIn("monthly_active_users", content)
        self.assertIn("312", content)

    def test_datasource_clicks_written(self):
        resp = {
            "overviewResponse": {
                "monthlyActiveUsers": 0, "weeklyActiveUsers": 0,
                "employeeCount": 0, "totalSignups": 0,
                "searchSessionSatisfaction": None,
                "lastUpdatedTs": None,
                "searchDatasourceCounts": {"gdrive": 500, "slack": 300},
            }
        }
        _export_insights_csv(resp, self.path)
        with open(self.path) as f:
            content = f.read()
        self.assertIn("datasource_clicks", content)
        self.assertIn("gdrive", content)

    def test_assistant_rows_written(self):
        resp = {
            "assistantResponse": {
                "monthlyActiveUsers": 99, "weeklyActiveUsers": 44,
                "lastUpdatedTs": None,
            }
        }
        _export_insights_csv(resp, self.path)
        with open(self.path) as f:
            content = f.read()
        self.assertIn("assistant", content)
        self.assertIn("99", content)

    def test_agents_rows_written(self):
        resp = {
            "agentsResponse": {
                "monthlyActiveUsers": 20, "weeklyActiveUsers": 8,
                "lastUpdatedTs": None,
            }
        }
        _export_insights_csv(resp, self.path)
        with open(self.path) as f:
            content = f.read()
        self.assertIn("agents", content)


# ---- _print_datasource_status ----

class TestPrintDatasourceStatus(unittest.TestCase):
    def test_shows_visibility(self):
        st = {"datasourceVisibility": "ENABLED_FOR_ALL"}
        with patch("glean_code.ui.supports_colour", return_value=False):
            out = _output(_print_datasource_status, st)
        self.assertIn("ENABLED_FOR_ALL", out)

    def test_shows_counts(self):
        st = {
            "documents": {
                "counts": {
                    "uploaded": [{"count": 1000}],
                    "indexed": [{"count": 950}],
                }
            }
        }
        with patch("glean_code.ui.supports_colour", return_value=False):
            out = _output(_print_datasource_status, st)
        self.assertIn("1,000", out)
        self.assertIn("950", out)
        self.assertIn("95.0%", out)

    def test_coverage_colour_green_above_95(self):
        st = {
            "documents": {
                "counts": {
                    "uploaded": [{"count": 100}],
                    "indexed": [{"count": 100}],
                }
            }
        }
        with patch("glean_code.ui.supports_colour", return_value=False):
            out = _output(_print_datasource_status, st)
        self.assertIn("100.0%", out)

    def test_shows_last_event(self):
        st = {
            "documents": {
                "processing_history": [
                    {"eventType": "FULL_CRAWL_COMPLETED", "timestamp": "2024-01-01"}
                ]
            }
        }
        with patch("glean_code.ui.supports_colour", return_value=False):
            out = _output(_print_datasource_status, st)
        self.assertIn("FULL_CRAWL_COMPLETED", out)

    def test_empty_status_no_crash(self):
        with patch("glean_code.ui.supports_colour", return_value=False):
            _output(_print_datasource_status, {})  # should not raise


# ---- Session.refresh_client ----

class TestSessionRefreshClient(unittest.TestCase):
    def test_refresh_creates_new_client(self):
        s = Session(Config(mode="mock"))
        original = s.client
        s.refresh_client()
        self.assertIsNot(s.client, original)

    def test_refresh_uses_current_config(self):
        from glean_code.client import GleanClient
        s = Session(Config(mode="mock"))
        s.config.instance = "updated.glean.com"
        s.refresh_client()
        self.assertIsInstance(s.client, GleanClient)
        self.assertIs(s.client.config, s.config)


if __name__ == "__main__":
    unittest.main()
