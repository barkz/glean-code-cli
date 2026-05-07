"""Tests for the 4 MCP tool functions in glean_mcp.py.

The mcp package may or may not be installed.  We mock it so the module
imports cleanly regardless, then test the tool logic directly.
"""
import os
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

# -- mock the mcp package so glean_mcp can import without it ------------------
_mcp_mod     = types.ModuleType("mcp")
_mcp_server  = types.ModuleType("mcp.server")
_mcp_fastmcp = types.ModuleType("mcp.server.fastmcp")

_mcp_instance = MagicMock()


def _passthrough_tool(*a, **kw):
    """Decorator factory that leaves the wrapped function unchanged."""
    def wrap(fn):
        return fn
    return wrap


_mcp_instance.tool = _passthrough_tool
_mcp_fastmcp.FastMCP = MagicMock(return_value=_mcp_instance)

for _name, _mod in [
    ("mcp",               _mcp_mod),
    ("mcp.server",        _mcp_server),
    ("mcp.server.fastmcp", _mcp_fastmcp),
]:
    sys.modules.setdefault(_name, _mod)

import glean_mcp  # noqa: E402  (import after sys.modules setup)


def _client_mock():
    return MagicMock()


# ---------------------------------------------------------------------------
# _build_client
# ---------------------------------------------------------------------------

class TestBuildClient(unittest.TestCase):
    def _build(self, env=None):
        from glean_code.config import Config
        cfg = Config(mode="mock")
        with patch("glean_code.config.Config.load", return_value=cfg), \
             patch.dict("os.environ", env or {}, clear=False):
            from glean_mcp import _build_client
            return _build_client()

    def test_returns_config_and_client_tuple(self):
        from glean_code.client import GleanClient
        from glean_code.config import Config
        cfg, client = self._build()
        self.assertIsInstance(cfg, Config)
        self.assertIsInstance(client, GleanClient)

    def test_forces_live_mode(self):
        cfg, _ = self._build()
        self.assertEqual(cfg.mode, "live")

    def test_env_var_overrides_instance(self):
        cfg, _ = self._build(env={"GLEAN_INSTANCE": "env-be.glean.com"})
        self.assertEqual(cfg.instance, "env-be.glean.com")

    def test_env_var_overrides_token(self):
        cfg, _ = self._build(env={"GLEAN_TOKEN": "env_tok_xyz"})
        self.assertEqual(cfg.api_token, "env_tok_xyz")

    def test_env_var_overrides_act_as(self):
        cfg, _ = self._build(env={"GLEAN_ACT_AS": "alice@example.com"})
        self.assertEqual(cfg.act_as, "alice@example.com")

    def test_no_env_vars_leaves_config_values(self):
        from glean_code.config import Config
        base_cfg = Config(instance="base-be.glean.com", api_token="base_tok", mode="mock")
        clean_env = {k: v for k, v in os.environ.items()
                     if k not in ("GLEAN_INSTANCE", "GLEAN_TOKEN", "GLEAN_ACT_AS")}
        with patch("glean_code.config.Config.load", return_value=base_cfg), \
             patch.dict("os.environ", clean_env, clear=True):
            from glean_mcp import _build_client
            cfg, _ = _build_client()
        self.assertEqual(cfg.instance, "base-be.glean.com")
        self.assertEqual(cfg.api_token, "base_tok")


# ---------------------------------------------------------------------------
# search tool
# ---------------------------------------------------------------------------

class TestMcpSearch(unittest.TestCase):
    def setUp(self):
        self.mock_client = _client_mock()
        self._patcher = patch.object(glean_mcp, "_client", self.mock_client)
        self._patcher.start()

    def tearDown(self):
        self._patcher.stop()

    def test_returns_results_string(self):
        self.mock_client.search.return_value = {
            "results": [{"title": "PTO Policy", "url": "https://hr.acme.com/pto",
                         "datasource": "confluence", "snippets": [{"text": "Take 20 days"}]}],
            "totalCount": 1,
        }
        result = glean_mcp.search("pto policy")
        self.assertIn("PTO Policy", result)
        self.assertIn("confluence", result)
        self.assertIn("Take 20 days", result)

    def test_no_results_returns_message(self):
        self.mock_client.search.return_value = {"results": []}
        result = glean_mcp.search("xyzzy")
        self.assertEqual(result, "No results found.")

    def test_glean_error_returns_error_string(self):
        from glean_code.client import GleanError
        self.mock_client.search.side_effect = GleanError("network failure")
        result = glean_mcp.search("anything")
        self.assertIn("Error", result)
        self.assertIn("network failure", result)

    def test_passes_page_size_to_client(self):
        self.mock_client.search.return_value = {"results": []}
        glean_mcp.search("q", page_size=5)
        _, kwargs = self.mock_client.search.call_args
        self.assertEqual(kwargs.get("page_size"), 5)

    def test_passes_datasource_to_client(self):
        self.mock_client.search.return_value = {"results": []}
        glean_mcp.search("q", datasource="gdrive")
        _, kwargs = self.mock_client.search.call_args
        self.assertEqual(kwargs.get("datasource"), "gdrive")

    def test_result_includes_total_count_header(self):
        self.mock_client.search.return_value = {
            "results": [{"title": "Doc", "url": "", "datasource": "", "snippets": []}],
            "totalCount": 42,
        }
        result = glean_mcp.search("query")
        self.assertIn("42", result)


# ---------------------------------------------------------------------------
# chat tool
# ---------------------------------------------------------------------------

class TestMcpChat(unittest.TestCase):
    def setUp(self):
        self.mock_client = _client_mock()
        self._patcher = patch.object(glean_mcp, "_client", self.mock_client)
        self._patcher.start()

    def tearDown(self):
        self._patcher.stop()

    def test_returns_response_text(self):
        self.mock_client.chat.return_value = {
            "chatId": "chat_abc",
            "messages": [{"fragments": [{"text": "Here is the answer."}], "citations": []}],
        }
        result = glean_mcp.chat("what is pto?")
        self.assertIn("Here is the answer.", result)

    def test_includes_chat_id_in_output(self):
        self.mock_client.chat.return_value = {
            "chatId": "chat_xyz",
            "messages": [{"fragments": [{"text": "hi"}], "citations": []}],
        }
        result = glean_mcp.chat("hello")
        self.assertIn("chat_xyz", result)

    def test_includes_citations(self):
        self.mock_client.chat.return_value = {
            "chatId": "c1",
            "messages": [{
                "fragments": [{"text": "answer"}],
                "citations": [{"sourceDocument": {"title": "HR Doc", "url": "https://hr.acme.com"}}],
            }],
        }
        result = glean_mcp.chat("q")
        self.assertIn("HR Doc", result)
        self.assertIn("Sources:", result)

    def test_empty_response_returns_no_response(self):
        self.mock_client.chat.return_value = {"messages": []}
        result = glean_mcp.chat("q")
        self.assertEqual(result, "(no response)")

    def test_glean_error_returns_error_string(self):
        from glean_code.client import GleanError
        self.mock_client.chat.side_effect = GleanError("auth failed")
        result = glean_mcp.chat("anything")
        self.assertIn("Error", result)
        self.assertIn("auth failed", result)

    def test_passes_chat_id_to_client(self):
        self.mock_client.chat.return_value = {"chatId": "c1", "messages": []}
        glean_mcp.chat("hello", chat_id="existing-id")
        _, kwargs = self.mock_client.chat.call_args
        self.assertEqual(kwargs.get("chat_id"), "existing-id")

    def test_passes_agent_to_client(self):
        self.mock_client.chat.return_value = {"chatId": "c1", "messages": []}
        glean_mcp.chat("hello", agent="sales")
        _, kwargs = self.mock_client.chat.call_args
        self.assertEqual(kwargs.get("agent"), "sales")


# ---------------------------------------------------------------------------
# list_agents tool
# ---------------------------------------------------------------------------

class TestMcpListAgents(unittest.TestCase):
    def setUp(self):
        self.mock_client = _client_mock()
        self._patcher = patch.object(glean_mcp, "_client", self.mock_client)
        self._patcher.start()

    def tearDown(self):
        self._patcher.stop()

    def test_returns_agent_listing(self):
        self.mock_client.agents_search.return_value = {
            "agents": [
                {"id": "agt_sales", "name": "Sales", "description": "Sales assistant"},
            ]
        }
        result = glean_mcp.list_agents()
        self.assertIn("agt_sales", result)
        self.assertIn("Sales", result)

    def test_no_agents_returns_message(self):
        self.mock_client.agents_search.return_value = {"agents": []}
        result = glean_mcp.list_agents()
        self.assertEqual(result, "No agents found.")

    def test_glean_error_returns_error_string(self):
        from glean_code.client import GleanError
        self.mock_client.agents_search.side_effect = GleanError("oops")
        result = glean_mcp.list_agents()
        self.assertIn("Error", result)

    def test_empty_query_passes_none_to_client(self):
        self.mock_client.agents_search.return_value = {"agents": []}
        glean_mcp.list_agents(query="")
        _, kwargs = self.mock_client.agents_search.call_args
        self.assertIsNone(kwargs.get("query"))

    def test_nonempty_query_passed_to_client(self):
        self.mock_client.agents_search.return_value = {"agents": []}
        glean_mcp.list_agents(query="finance")
        _, kwargs = self.mock_client.agents_search.call_args
        self.assertEqual(kwargs.get("query"), "finance")

    def test_agent_id_only_still_listed(self):
        self.mock_client.agents_search.return_value = {
            "agents": [{"id": "agt_bare"}]
        }
        result = glean_mcp.list_agents()
        self.assertIn("agt_bare", result)


# ---------------------------------------------------------------------------
# run_agent tool
# ---------------------------------------------------------------------------

class TestMcpRunAgent(unittest.TestCase):
    def setUp(self):
        self.mock_client = _client_mock()
        self._patcher = patch.object(glean_mcp, "_client", self.mock_client)
        self._patcher.start()

    def tearDown(self):
        self._patcher.stop()

    def test_returns_output_text(self):
        self.mock_client.agent_run.return_value = {
            "output": "The market grew 20%.",
            "runId": "run_001",
        }
        result = glean_mcp.run_agent("agt_1", "summarise market")
        self.assertIn("The market grew 20%.", result)

    def test_includes_run_id(self):
        self.mock_client.agent_run.return_value = {
            "output": "done",
            "runId": "run_xyz",
        }
        result = glean_mcp.run_agent("agt_1", "task")
        self.assertIn("run_xyz", result)

    def test_empty_output_falls_back_to_json_dump(self):
        self.mock_client.agent_run.return_value = {"status": "ok", "runId": "r1"}
        result = glean_mcp.run_agent("agt_1", "task")
        self.assertIn("status", result)

    def test_glean_error_returns_error_string(self):
        from glean_code.client import GleanError
        self.mock_client.agent_run.side_effect = GleanError("timeout")
        result = glean_mcp.run_agent("agt_1", "task")
        self.assertIn("Error", result)
        self.assertIn("timeout", result)

    def test_passes_agent_id_and_input_to_client(self):
        self.mock_client.agent_run.return_value = {"output": "x", "runId": "r"}
        glean_mcp.run_agent("agt_research", "write a brief")
        args, _ = self.mock_client.agent_run.call_args
        self.assertEqual(args[0], "agt_research")
        self.assertEqual(args[1], "write a brief")


if __name__ == "__main__":
    unittest.main()
