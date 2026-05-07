"""Tests for glean_code.commands"""
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from glean_code.commands import (
    parse_args, dispatch, Session, HANDLERS,
    _render_chat_response, _render_search, _render_json,
)
from glean_code.config import Config
from glean_code.client import GleanError


def _mock_session(**config_kwargs):
    """Return a Session with a mock GleanClient."""
    config = Config(mode="mock", **config_kwargs)
    session = Session(config)
    session.client = MagicMock()
    return session


# ---- parse_args ----

class TestParseArgs(unittest.TestCase):
    def test_empty_tokens(self):
        pos, flags = parse_args([])
        self.assertEqual(pos, [])
        self.assertEqual(flags, {})

    def test_positional_only(self):
        pos, flags = parse_args(["a", "b", "c"])
        self.assertEqual(pos, ["a", "b", "c"])
        self.assertEqual(flags, {})

    def test_flag_with_value(self):
        pos, flags = parse_args(["--name", "alice"])
        self.assertEqual(pos, [])
        self.assertEqual(flags, {"name": "alice"})

    def test_bare_flag_becomes_true(self):
        pos, flags = parse_args(["--verbose"])
        self.assertTrue(flags["verbose"])

    def test_mixed_positional_and_flags(self):
        pos, flags = parse_args(["query", "--page-size", "20", "--datasource", "gdrive"])
        self.assertEqual(pos, ["query"])
        self.assertEqual(flags["page-size"], "20")
        self.assertEqual(flags["datasource"], "gdrive")

    def test_consecutive_bare_flags(self):
        pos, flags = parse_args(["--a", "--b", "--c"])
        self.assertEqual(flags, {"a": True, "b": True, "c": True})

    def test_flag_followed_immediately_by_another_flag(self):
        pos, flags = parse_args(["--key", "--value"])
        self.assertTrue(flags["key"])
        self.assertTrue(flags["value"])

    def test_positional_after_flag_value(self):
        pos, flags = parse_args(["--flag", "val", "positional"])
        self.assertEqual(flags["flag"], "val")
        self.assertEqual(pos, ["positional"])


# ---- dispatch ----

class TestDispatch(unittest.TestCase):
    def test_empty_line_is_no_op(self):
        s = _mock_session()
        dispatch(s, "")
        self.assertEqual(s.command_history, [])

    def test_whitespace_only_is_no_op(self):
        s = _mock_session()
        dispatch(s, "   ")
        self.assertEqual(s.command_history, [])

    def test_bare_text_routes_to_chat(self):
        s = _mock_session()
        s.client.chat.return_value = {
            "chatId": "cid",
            "messages": [{"fragments": [{"text": "hi"}], "citations": []}],
        }
        with patch("builtins.print"):
            dispatch(s, "hello there")
        s.client.chat.assert_called_once_with("hello there", chat_id=None, agent=None, stream=False)

    def test_slash_command_dispatches_correctly(self):
        s = _mock_session()
        with patch("builtins.print"):
            dispatch(s, "/exit")
        self.assertFalse(s.running)

    def test_unknown_command_prints_error(self):
        s = _mock_session()
        with patch("builtins.print") as mock_print:
            dispatch(s, "/nonexistent_xyz_command")
        output = " ".join(str(a) for call in mock_print.call_args_list for a in call[0])
        self.assertIn("Unknown", output)

    def test_all_dispatched_commands_added_to_history(self):
        s = _mock_session()
        with patch("builtins.print"):
            dispatch(s, "/exit")
        self.assertIn("/exit", s.command_history)

    def test_bare_text_added_to_history(self):
        s = _mock_session()
        s.client.chat.return_value = {"messages": [{"fragments": [{"text": "r"}], "citations": []}]}
        with patch("builtins.print"):
            dispatch(s, "what is pto")
        self.assertIn("what is pto", s.command_history)

    def test_unclosed_quote_shows_parse_error(self):
        s = _mock_session()
        with patch("builtins.print") as mock_print:
            dispatch(s, "/chat 'unclosed")
        output = " ".join(str(a) for call in mock_print.call_args_list for a in call[0])
        self.assertIn("Parse error", output)


# ---- shell commands ----

class TestCmdExit(unittest.TestCase):
    def test_sets_running_false(self):
        s = _mock_session()
        with patch("builtins.print"):
            HANDLERS["exit"](s, [], {})
        self.assertFalse(s.running)

    def test_quit_also_sets_running_false(self):
        s = _mock_session()
        with patch("builtins.print"):
            HANDLERS["quit"](s, [], {})
        self.assertFalse(s.running)


class TestCmdMode(unittest.TestCase):
    def test_sets_mock_mode(self):
        s = _mock_session()
        with patch("builtins.print"), patch.object(s.config, "save"):
            HANDLERS["mode"](s, ["mock"], {})
        self.assertEqual(s.config.mode, "mock")

    def test_sets_live_mode(self):
        s = _mock_session()
        with patch("builtins.print"), patch.object(s.config, "save"):
            HANDLERS["mode"](s, ["live"], {})
        self.assertEqual(s.config.mode, "live")

    def test_sets_auto_mode(self):
        s = _mock_session()
        with patch("builtins.print"), patch.object(s.config, "save"):
            HANDLERS["mode"](s, ["auto"], {})
        self.assertEqual(s.config.mode, "auto")

    def test_rejects_invalid_mode(self):
        s = _mock_session()
        with patch("builtins.print") as mock_print:
            HANDLERS["mode"](s, ["invalid"], {})
        self.assertEqual(s.config.mode, "mock")  # unchanged
        output = " ".join(str(a) for call in mock_print.call_args_list for a in call[0])
        self.assertIn("Usage", output)

    def test_no_pos_args_shows_usage(self):
        s = _mock_session()
        with patch("builtins.print") as mock_print:
            HANDLERS["mode"](s, [], {})
        output = " ".join(str(a) for call in mock_print.call_args_list for a in call[0])
        self.assertIn("Usage", output)


class TestCmdLogin(unittest.TestCase):
    def test_sets_instance_and_token(self):
        s = _mock_session()
        with patch("builtins.print"), \
             patch.object(s.config, "save"), \
             patch.object(s, "refresh_client"):
            HANDLERS["login"](s, [], {"instance": "acme-be.glean.com", "token": "tok123"})
        self.assertEqual(s.config.instance, "acme-be.glean.com")
        self.assertEqual(s.config.api_token, "tok123")

    def test_strips_https_scheme(self):
        s = _mock_session()
        with patch("builtins.print"), \
             patch.object(s.config, "save"), \
             patch.object(s, "refresh_client"):
            HANDLERS["login"](s, [], {"instance": "https://acme-be.glean.com", "token": "t"})
        self.assertEqual(s.config.instance, "acme-be.glean.com")

    def test_sets_act_as(self):
        s = _mock_session()
        with patch("builtins.print"), \
             patch.object(s.config, "save"), \
             patch.object(s, "refresh_client"):
            HANDLERS["login"](s, [], {
                "instance": "acme-be.glean.com",
                "token": "t",
                "act-as": "user@example.com",
            })
        self.assertEqual(s.config.act_as, "user@example.com")

    def test_requires_instance(self):
        s = _mock_session()
        with patch("builtins.print") as mock_print:
            HANDLERS["login"](s, [], {"token": "tok"})
        output = " ".join(str(a) for call in mock_print.call_args_list for a in call[0])
        self.assertIn("Usage", output)

    def test_requires_token(self):
        s = _mock_session()
        with patch("builtins.print") as mock_print:
            HANDLERS["login"](s, [], {"instance": "acme-be.glean.com"})
        output = " ".join(str(a) for call in mock_print.call_args_list for a in call[0])
        self.assertIn("Usage", output)

    def test_rejects_invalid_hostname(self):
        s = _mock_session()
        with patch("builtins.print") as mock_print:
            HANDLERS["login"](s, [], {"instance": "notahost", "token": "tok"})
        output = " ".join(str(a) for call in mock_print.call_args_list for a in call[0])
        self.assertIn("hostname", output.lower())


class TestCmdLogout(unittest.TestCase):
    def test_clears_token(self):
        s = _mock_session()
        s.config.api_token = "tok"
        with patch("builtins.print"), \
             patch.object(s.config, "save"), \
             patch.object(s, "refresh_client"):
            HANDLERS["logout"](s, [], {})
        self.assertIsNone(s.config.api_token)

    def test_clears_act_as(self):
        s = _mock_session()
        s.config.act_as = "user@example.com"
        with patch("builtins.print"), \
             patch.object(s.config, "save"), \
             patch.object(s, "refresh_client"):
            HANDLERS["logout"](s, [], {})
        self.assertIsNone(s.config.act_as)


class TestCmdConfig(unittest.TestCase):
    def test_set_updates_value(self):
        s = _mock_session()
        with patch("builtins.print"), \
             patch.object(s.config, "save"), \
             patch.object(s, "refresh_client"):
            HANDLERS["config"](s, ["set", "instance", "new-host.glean.com"], {})
        self.assertEqual(s.config.instance, "new-host.glean.com")

    def test_set_default_page_size_converts_to_int(self):
        s = _mock_session()
        with patch("builtins.print"), \
             patch.object(s.config, "save"), \
             patch.object(s, "refresh_client"):
            HANDLERS["config"](s, ["set", "default_page_size", "25"], {})
        self.assertEqual(s.config.default_page_size, 25)

    def test_set_default_page_size_rejects_non_int(self):
        s = _mock_session()
        with patch("builtins.print") as mock_print:
            HANDLERS["config"](s, ["set", "default_page_size", "not_a_number"], {})
        output = " ".join(str(a) for call in mock_print.call_args_list for a in call[0])
        self.assertIn("integer", output)

    def test_set_unknown_key_errors(self):
        s = _mock_session()
        with patch("builtins.print") as mock_print:
            HANDLERS["config"](s, ["set", "nonexistent_key", "val"], {})
        output = " ".join(str(a) for call in mock_print.call_args_list for a in call[0])
        self.assertIn("Unknown", output)

    def test_get_returns_current_value(self):
        s = _mock_session()
        s.config.instance = "acme.glean.com"
        with patch("builtins.print") as mock_print:
            HANDLERS["config"](s, ["get", "instance"], {})
        printed = " ".join(str(a) for call in mock_print.call_args_list for a in call[0])
        self.assertIn("acme.glean.com", printed)

    def test_list_shows_config_json(self):
        s = _mock_session()
        s.config.instance = "test.glean.com"
        with patch("builtins.print") as mock_print:
            HANDLERS["config"](s, [], {})
        output = " ".join(str(a) for call in mock_print.call_args_list for a in call[0])
        self.assertIn("test.glean.com", output)

    def test_list_masks_api_token(self):
        s = _mock_session()
        s.config.api_token = "supersecrettoken"
        with patch("builtins.print") as mock_print:
            HANDLERS["config"](s, [], {})
        output = " ".join(str(a) for call in mock_print.call_args_list for a in call[0])
        self.assertNotIn("supersecrettoken", output)
        self.assertIn("***", output)


class TestCmdHistory(unittest.TestCase):
    def test_empty_history_says_no_history(self):
        s = _mock_session()
        with patch("builtins.print") as mock_print:
            HANDLERS["history"](s, [], {})
        output = " ".join(str(a) for call in mock_print.call_args_list for a in call[0])
        self.assertIn("no history", output.lower())

    def test_shows_recent_commands(self):
        s = _mock_session()
        s.command_history = ["/search foo", "/chat hello"]
        with patch("builtins.print") as mock_print:
            HANDLERS["history"](s, [], {})
        output = " ".join(str(a) for call in mock_print.call_args_list for a in call[0])
        self.assertIn("/search foo", output)
        self.assertIn("/chat hello", output)

    def test_limit_flag_restricts_output(self):
        s = _mock_session()
        s.command_history = [f"/cmd{i}" for i in range(30)]
        captured = []
        with patch("builtins.print", side_effect=lambda x: captured.append(str(x))):
            HANDLERS["history"](s, [], {"limit": "5"})
        output = "\n".join(captured)
        self.assertIn("/cmd29", output)   # last item included
        self.assertNotIn("/cmd0", output) # first items excluded


# ---- chat & search ----

class TestCmdChat(unittest.TestCase):
    def test_requires_message(self):
        s = _mock_session()
        with patch("builtins.print") as mock_print:
            HANDLERS["chat"](s, [], {})
        output = " ".join(str(a) for call in mock_print.call_args_list for a in call[0])
        self.assertIn("Usage", output)

    def test_calls_client_with_message(self):
        s = _mock_session()
        s.client.chat.return_value = {
            "chatId": "cid1",
            "messages": [{"fragments": [{"text": "Answer"}], "citations": []}],
        }
        with patch("builtins.print"):
            HANDLERS["chat"](s, ["hello"], {})
        s.client.chat.assert_called_once()
        call_kwargs = s.client.chat.call_args
        self.assertEqual(call_kwargs[0][0], "hello")

    def test_stores_chat_id_from_response(self):
        s = _mock_session()
        s.client.chat.return_value = {
            "chatId": "new-chat-id",
            "messages": [{"fragments": [{"text": "hi"}], "citations": []}],
        }
        with patch("builtins.print"):
            HANDLERS["chat"](s, ["hi"], {})
        self.assertEqual(s.current_chat_id, "new-chat-id")

    def test_continues_thread_with_existing_chat_id(self):
        s = _mock_session()
        s.current_chat_id = "existing-thread"
        s.client.chat.return_value = {
            "chatId": "existing-thread",
            "messages": [{"fragments": [{"text": "r"}], "citations": []}],
        }
        with patch("builtins.print"):
            HANDLERS["chat"](s, ["follow up"], {})
        s.client.chat.assert_called_once_with(
            "follow up", chat_id="existing-thread", agent=None, stream=False
        )

    def test_new_flag_resets_chat_id(self):
        s = _mock_session()
        s.current_chat_id = "old-thread"
        s.client.chat.return_value = {
            "chatId": "fresh",
            "messages": [{"fragments": [{"text": "hi"}], "citations": []}],
        }
        with patch("builtins.print"):
            HANDLERS["chat"](s, ["new topic"], {"new": True})
        s.client.chat.assert_called_once_with(
            "new topic", chat_id=None, agent=None, stream=False
        )

    def test_explicit_chat_id_flag_overrides_session(self):
        s = _mock_session()
        s.current_chat_id = "session-thread"
        s.client.chat.return_value = {
            "chatId": "explicit-id",
            "messages": [{"fragments": [{"text": "r"}], "citations": []}],
        }
        with patch("builtins.print"):
            HANDLERS["chat"](s, ["msg"], {"chat-id": "explicit-id"})
        s.client.chat.assert_called_once_with(
            "msg", chat_id="explicit-id", agent=None, stream=False
        )

    def test_handles_glean_error(self):
        s = _mock_session()
        s.client.chat.side_effect = GleanError("connection refused")
        with patch("builtins.print") as mock_print:
            HANDLERS["chat"](s, ["hello"], {})
        output = " ".join(str(a) for call in mock_print.call_args_list for a in call[0])
        self.assertIn("connection refused", output)

    def test_multiword_message_joined(self):
        s = _mock_session()
        s.client.chat.return_value = {
            "chatId": "c1",
            "messages": [{"fragments": [{"text": "r"}], "citations": []}],
        }
        with patch("builtins.print"):
            HANDLERS["chat"](s, ["what", "is", "pto"], {})
        s.client.chat.assert_called_once_with(
            "what is pto", chat_id=None, agent=None, stream=False
        )


class TestCmdSearch(unittest.TestCase):
    def test_requires_query(self):
        s = _mock_session()
        with patch("builtins.print") as mock_print:
            HANDLERS["search"](s, [], {})
        output = " ".join(str(a) for call in mock_print.call_args_list for a in call[0])
        self.assertIn("Usage", output)

    def test_calls_client_with_joined_query(self):
        s = _mock_session()
        s.client.search.return_value = {"results": []}
        with patch("builtins.print"):
            HANDLERS["search"](s, ["python", "testing"], {})
        s.client.search.assert_called_once_with(
            "python testing", page_size=10, datasource=None
        )

    def test_respects_page_size_flag(self):
        s = _mock_session()
        s.client.search.return_value = {"results": []}
        with patch("builtins.print"):
            HANDLERS["search"](s, ["query"], {"page-size": "5"})
        s.client.search.assert_called_once_with("query", page_size=5, datasource=None)

    def test_respects_datasource_flag(self):
        s = _mock_session()
        s.client.search.return_value = {"results": []}
        with patch("builtins.print"):
            HANDLERS["search"](s, ["docs"], {"datasource": "gdrive"})
        s.client.search.assert_called_once_with("docs", page_size=10, datasource="gdrive")

    def test_uses_config_default_page_size(self):
        s = _mock_session(default_page_size=20)
        s.client.search.return_value = {"results": []}
        with patch("builtins.print"):
            HANDLERS["search"](s, ["q"], {})
        s.client.search.assert_called_once_with("q", page_size=20, datasource=None)

    def test_handles_glean_error(self):
        s = _mock_session()
        s.client.search.side_effect = GleanError("timeout")
        with patch("builtins.print") as mock_print:
            HANDLERS["search"](s, ["query"], {})
        output = " ".join(str(a) for call in mock_print.call_args_list for a in call[0])
        self.assertIn("timeout", output)


# ---- agents & tools ----

class TestCmdAgents(unittest.TestCase):
    def test_agents_list_calls_client(self):
        s = _mock_session()
        s.client.agents_search.return_value = {"agents": []}
        with patch("builtins.print"):
            HANDLERS["agents.list"](s, [], {})
        s.client.agents_search.assert_called_once()

    def test_agents_list_passes_query_flag(self):
        s = _mock_session()
        s.client.agents_search.return_value = {"agents": []}
        with patch("builtins.print"):
            HANDLERS["agents.list"](s, [], {"query": "sales"})
        s.client.agents_search.assert_called_once_with(query="sales")

    def test_agents_run_requires_agent_and_input(self):
        s = _mock_session()
        with patch("builtins.print") as mock_print:
            HANDLERS["agents.run"](s, ["only-one-arg"], {})
        output = " ".join(str(a) for call in mock_print.call_args_list for a in call[0])
        self.assertIn("Usage", output)

    def test_agents_run_calls_client_with_joined_input(self):
        s = _mock_session()
        s.client.agent_run.return_value = {"output": "done", "runId": "r1"}
        with patch("builtins.print"):
            HANDLERS["agents.run"](s, ["agt_1", "do", "the", "thing"], {})
        s.client.agent_run.assert_called_once_with("agt_1", "do the thing", stream=False)

    def test_agents_run_stream_flag(self):
        s = _mock_session()
        s.client.agent_run.return_value = {"output": "done", "runId": "r1"}
        with patch("builtins.print"):
            HANDLERS["agents.run"](s, ["agt_1", "task"], {"stream": True})
        s.client.agent_run.assert_called_once_with("agt_1", "task", stream=True)


class TestCmdTools(unittest.TestCase):
    def test_tools_list_calls_client(self):
        s = _mock_session()
        s.client.tools_list.return_value = {"tools": []}
        with patch("builtins.print"):
            HANDLERS["tools.list"](s, [], {})
        s.client.tools_list.assert_called_once()

    def test_tools_call_requires_name_and_args(self):
        s = _mock_session()
        with patch("builtins.print") as mock_print:
            HANDLERS["tools.call"](s, ["only-name"], {})
        output = " ".join(str(a) for call in mock_print.call_args_list for a in call[0])
        self.assertIn("Usage", output)

    def test_tools_call_rejects_invalid_json(self):
        s = _mock_session()
        with patch("builtins.print") as mock_print:
            HANDLERS["tools.call"](s, ["search", "not json"], {})
        output = " ".join(str(a) for call in mock_print.call_args_list for a in call[0])
        self.assertIn("JSON", output)

    def test_tools_call_valid_json(self):
        s = _mock_session()
        s.client.tools_call.return_value = {"result": "ok"}
        with patch("builtins.print"):
            HANDLERS["tools.call"](s, ["search", '{"query": "test"}'], {})
        s.client.tools_call.assert_called_once_with("search", {"query": "test"})


# ---- documents & people ----

class TestCmdDocs(unittest.TestCase):
    def test_get_requires_id_or_url(self):
        s = _mock_session()
        with patch("builtins.print") as mock_print:
            HANDLERS["docs.get"](s, [], {})
        output = " ".join(str(a) for call in mock_print.call_args_list for a in call[0])
        self.assertIn("Usage", output)

    def test_get_by_id(self):
        s = _mock_session()
        s.client.get_documents.return_value = {"documents": []}
        with patch("builtins.print"):
            HANDLERS["docs.get"](s, [], {"id": "doc_123"})
        s.client.get_documents.assert_called_once_with(ids=["doc_123"], urls=None)

    def test_get_by_url(self):
        s = _mock_session()
        s.client.get_documents.return_value = {"documents": []}
        with patch("builtins.print"):
            HANDLERS["docs.get"](s, [], {"url": "https://example.com"})
        s.client.get_documents.assert_called_once_with(ids=None, urls=["https://example.com"])

    def test_permissions_requires_doc_id(self):
        s = _mock_session()
        with patch("builtins.print") as mock_print:
            HANDLERS["docs.permissions"](s, [], {})
        output = " ".join(str(a) for call in mock_print.call_args_list for a in call[0])
        self.assertIn("Usage", output)

    def test_permissions_calls_client(self):
        s = _mock_session()
        s.client.document_permissions.return_value = {"permissions": []}
        with patch("builtins.print"):
            HANDLERS["docs.permissions"](s, ["doc_42"], {})
        s.client.document_permissions.assert_called_once_with("doc_42")


class TestCmdPeople(unittest.TestCase):
    def test_people_get_requires_email(self):
        s = _mock_session()
        with patch("builtins.print") as mock_print:
            HANDLERS["people.get"](s, [], {})
        output = " ".join(str(a) for call in mock_print.call_args_list for a in call[0])
        self.assertIn("Usage", output)

    def test_people_get_calls_client(self):
        s = _mock_session()
        s.client.person.return_value = {"name": "Alice", "email": "alice@example.com"}
        with patch("builtins.print"):
            HANDLERS["people.get"](s, ["alice@example.com"], {})
        s.client.person.assert_called_once_with("alice@example.com")


# ---- announcements ----

class TestCmdAnnouncements(unittest.TestCase):
    def test_create_requires_title_and_body(self):
        s = _mock_session()
        with patch("builtins.print") as mock_print:
            HANDLERS["announcements.create"](s, [], {"title": "only title"})
        output = " ".join(str(a) for call in mock_print.call_args_list for a in call[0])
        self.assertIn("Usage", output)

    def test_create_calls_client(self):
        s = _mock_session()
        s.client.announcement_create.return_value = {"id": "ann_1", "status": "created"}
        with patch("builtins.print"):
            HANDLERS["announcements.create"](s, [], {"title": "Hi", "body": "Hello all"})
        s.client.announcement_create.assert_called_once_with("Hi", "Hello all", audience=None)

    def test_create_passes_audience(self):
        s = _mock_session()
        s.client.announcement_create.return_value = {"id": "ann_1", "status": "created"}
        with patch("builtins.print"):
            HANDLERS["announcements.create"](
                s, [], {"title": "Hi", "body": "Text", "audience": "engineering"}
            )
        s.client.announcement_create.assert_called_once_with(
            "Hi", "Text", audience="engineering"
        )

    def test_delete_requires_id(self):
        s = _mock_session()
        with patch("builtins.print") as mock_print:
            HANDLERS["announcements.delete"](s, [], {})
        output = " ".join(str(a) for call in mock_print.call_args_list for a in call[0])
        self.assertIn("Usage", output)

    def test_delete_calls_client(self):
        s = _mock_session()
        s.client.announcement_delete.return_value = {"id": "ann_1", "status": "deleted"}
        with patch("builtins.print"):
            HANDLERS["announcements.delete"](s, ["ann_1"], {})
        s.client.announcement_delete.assert_called_once_with("ann_1")


# ---- collections ----

class TestCmdCollections(unittest.TestCase):
    def test_list_calls_client(self):
        s = _mock_session()
        s.client.collections_list.return_value = {"collections": []}
        with patch("builtins.print"):
            HANDLERS["collections.list"](s, [], {})
        s.client.collections_list.assert_called_once()

    def test_create_requires_name(self):
        s = _mock_session()
        with patch("builtins.print") as mock_print:
            HANDLERS["collections.create"](s, [], {})
        output = " ".join(str(a) for call in mock_print.call_args_list for a in call[0])
        self.assertIn("Usage", output)

    def test_create_calls_client(self):
        s = _mock_session()
        s.client.collection_create.return_value = {"id": "col_1", "name": "Onboarding"}
        with patch("builtins.print"):
            HANDLERS["collections.create"](s, [], {"name": "Onboarding"})
        s.client.collection_create.assert_called_once_with("Onboarding", description=None)


# ---- pins ----

class TestCmdPins(unittest.TestCase):
    def test_create_requires_url_and_query(self):
        s = _mock_session()
        with patch("builtins.print") as mock_print:
            HANDLERS["pins.create"](s, [], {"url": "https://example.com"})
        output = " ".join(str(a) for call in mock_print.call_args_list for a in call[0])
        self.assertIn("Usage", output)

    def test_create_calls_client(self):
        s = _mock_session()
        s.client.pin_create.return_value = {"id": "pin_1", "status": "created"}
        with patch("builtins.print"):
            HANDLERS["pins.create"](
                s, [], {"url": "https://example.com/pto", "query": "pto policy"}
            )
        s.client.pin_create.assert_called_once_with(
            "https://example.com/pto", "pto policy"
        )

    def test_list_calls_client(self):
        s = _mock_session()
        s.client.pins_list.return_value = {"pins": []}
        with patch("builtins.print"):
            HANDLERS["pins.list"](s, [], {})
        s.client.pins_list.assert_called_once()


# ---- rendering helpers ----

class TestRenderHelpers(unittest.TestCase):
    def test_render_json_formats_dict(self):
        result = _render_json({"key": "value", "num": 42})
        self.assertIn('"key"', result)
        self.assertIn('"value"', result)
        self.assertIn("42", result)

    def test_render_json_formats_list(self):
        result = _render_json([1, 2, 3])
        self.assertIn("1", result)

    def test_render_search_no_results(self):
        with patch("glean_code.ui.supports_colour", return_value=False):
            result = _render_search({"results": []})
        self.assertIn("No results", result)

    def test_render_search_with_results(self):
        resp = {
            "results": [{
                "title": "Test Doc",
                "url": "https://ex.com",
                "datasource": "gdrive",
                "snippets": [{"text": "relevant snippet"}],
            }]
        }
        with patch("glean_code.ui.supports_colour", return_value=False):
            result = _render_search(resp)
        self.assertIn("Test Doc", result)
        self.assertIn("relevant snippet", result)

    def test_render_search_without_snippet(self):
        resp = {
            "results": [{
                "title": "Doc", "url": "https://ex.com",
                "datasource": "gdrive", "snippets": [],
            }]
        }
        with patch("glean_code.ui.supports_colour", return_value=False):
            result = _render_search(resp)
        self.assertIn("Doc", result)

    def test_render_chat_extracts_text(self):
        resp = {"messages": [{"fragments": [{"text": "Hello, world!"}], "citations": []}]}
        with patch("glean_code.ui.supports_colour", return_value=False):
            result = _render_chat_response(resp)
        self.assertIn("Hello, world!", result)

    def test_render_chat_shows_citations(self):
        resp = {"messages": [{
            "fragments": [{"text": "Answer"}],
            "citations": [{"sourceDocument": {"title": "Doc A", "url": "https://example.com/a"}}],
        }]}
        with patch("glean_code.ui.supports_colour", return_value=False):
            result = _render_chat_response(resp)
        self.assertIn("Doc A", result)
        self.assertIn("Citations", result)

    def test_render_chat_empty_messages(self):
        with patch("glean_code.ui.supports_colour", return_value=False):
            result = _render_chat_response({"messages": []})
        self.assertEqual(result, "(no content)")

    def test_render_chat_multiple_fragments(self):
        resp = {"messages": [{
            "fragments": [{"text": "Part one. "}, {"text": "Part two."}],
            "citations": [],
        }]}
        with patch("glean_code.ui.supports_colour", return_value=False):
            result = _render_chat_response(resp)
        self.assertIn("Part one.", result)
        self.assertIn("Part two.", result)


if __name__ == "__main__":
    unittest.main()
