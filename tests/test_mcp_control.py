"""Tests for /mcp — server control and diagnostics.

Every test redirects the state file at a temporary directory, so the real
~/.gleancode/mcp.json is never touched. Nothing here spawns a server: the
refusal paths are what matter, and they're reachable without one.
"""
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent.parent))

from glean_code import mcp_control as mc
from glean_code.commands import HANDLERS, Session
from glean_code.config import Config


class _StateDir:
    """Point the module's state/log paths at a temp dir for one test."""

    def __enter__(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self._patches = [
            mock.patch.object(mc, "CONFIG_DIR", root),
            mock.patch.object(mc, "STATE_PATH", root / "mcp.json"),
            mock.patch.object(mc, "LOG_PATH", root / "mcp.log"),
        ]
        for p in self._patches:
            p.start()
        return root

    def __exit__(self, *exc):
        mock.patch.stopall()
        self.tmp.cleanup()
        return False


class TestPackageDiagnostics(unittest.TestCase):
    def test_returns_version_and_compat_flag(self):
        version, compatible = mc.mcp_package()
        self.assertTrue(version is None or isinstance(version, str))
        self.assertIsInstance(compatible, bool)

    def test_missing_package_is_not_compatible(self):
        with mock.patch.dict(sys.modules, {"mcp": None}):
            version, compatible = mc.mcp_package()
        self.assertIsNone(version)
        self.assertFalse(compatible)

    def test_required_pin_excludes_v2(self):
        self.assertIn("<2", mc.REQUIRED_MCP)


class TestState(unittest.TestCase):
    def test_roundtrip(self):
        with _StateDir():
            mc.write_state({"pid": 1234, "url": "http://x"})
            self.assertEqual(mc.read_state()["pid"], 1234)
            mc.clear_state()
            self.assertIsNone(mc.read_state())

    def test_unreadable_state_is_none(self):
        with _StateDir() as root:
            (root / "mcp.json").write_text("{not json")
            self.assertIsNone(mc.read_state())

    def test_running_clears_stale_state(self):
        with _StateDir():
            # A pid that cannot be alive — reaped and never reassigned mid-test.
            mc.write_state({"pid": 999999, "url": "http://x"})
            with mock.patch.object(mc, "_pid_alive", return_value=False):
                self.assertIsNone(mc.running())
            self.assertIsNone(mc.read_state(), "stale state should be removed")

    def test_running_rejects_a_reused_pid(self):
        with _StateDir():
            mc.write_state({"pid": os.getpid(), "url": "http://x"})
            with mock.patch.object(mc, "_pid_alive", return_value=True), \
                 mock.patch.object(mc, "_pid_is_ours", return_value=False):
                self.assertIsNone(mc.running())

    def test_running_returns_live_state(self):
        with _StateDir():
            mc.write_state({"pid": os.getpid(), "url": "http://x"})
            with mock.patch.object(mc, "_pid_alive", return_value=True), \
                 mock.patch.object(mc, "_pid_is_ours", return_value=True):
                self.assertEqual(mc.running()["url"], "http://x")


class TestStartRefusals(unittest.TestCase):
    """start() must refuse clearly rather than spawn something useless."""

    def _start(self, **kw):
        with _StateDir():
            with mock.patch.object(mc, "mcp_package", return_value=("1.29.0", True)), \
                 mock.patch.object(mc, "running", return_value=None):
                return mc.start(**kw)

    def test_stdio_is_refused_with_an_explanation(self):
        with self.assertRaises(RuntimeError) as cm:
            self._start(transport="stdio")
        self.assertIn("stdio", str(cm.exception))
        self.assertIn("client", str(cm.exception).lower())

    def test_unknown_transport_is_refused(self):
        with self.assertRaises(RuntimeError) as cm:
            self._start(transport="carrier-pigeon")
        self.assertIn("unknown transport", str(cm.exception))

    def test_missing_package_is_refused(self):
        with _StateDir():
            with mock.patch.object(mc, "mcp_package", return_value=(None, False)), \
                 mock.patch.object(mc, "running", return_value=None):
                with self.assertRaises(RuntimeError) as cm:
                    mc.start()
        self.assertIn(mc.REQUIRED_MCP, str(cm.exception))

    def test_incompatible_v2_is_refused_by_name(self):
        with _StateDir():
            with mock.patch.object(mc, "mcp_package", return_value=("2.0.0", False)), \
                 mock.patch.object(mc, "running", return_value=None):
                with self.assertRaises(RuntimeError) as cm:
                    mc.start()
        msg = str(cm.exception)
        self.assertIn("2.0.0", msg)
        self.assertIn("fastmcp", msg)

    def test_second_start_is_refused(self):
        with _StateDir():
            live = {"pid": 4242, "url": "http://127.0.0.1:8787/mcp"}
            with mock.patch.object(mc, "mcp_package", return_value=("1.29.0", True)), \
                 mock.patch.object(mc, "running", return_value=live):
                with self.assertRaises(RuntimeError) as cm:
                    mc.start()
        self.assertIn("already running", str(cm.exception))


class TestStop(unittest.TestCase):
    def test_stop_without_a_server_returns_none(self):
        with _StateDir():
            with mock.patch.object(mc, "running", return_value=None):
                self.assertIsNone(mc.stop())

    def test_stop_signals_and_clears(self):
        with _StateDir():
            mc.write_state({"pid": 4242, "url": "http://x"})
            with mock.patch.object(mc, "running", return_value={"pid": 4242, "url": "http://x"}), \
                 mock.patch.object(mc, "_pid_alive", return_value=False), \
                 mock.patch("os.kill") as killer:
                state = mc.stop()
            killer.assert_called_once()
            self.assertEqual(state["pid"], 4242)
            self.assertIsNone(mc.read_state())


class TestClientConfig(unittest.TestCase):
    def test_stdio_form_is_a_spawnable_command(self):
        cfg = mc.client_config()["mcpServers"]["glean"]
        self.assertIn("command", cfg)
        self.assertTrue(cfg["args"][0].endswith("glean_mcp.py"))
        self.assertNotIn("url", cfg)

    def test_url_form_points_at_the_running_server(self):
        cfg = mc.client_config("http://127.0.0.1:8787/mcp")["mcpServers"]["glean"]
        self.assertEqual(cfg["type"], "http")
        self.assertEqual(cfg["url"], "http://127.0.0.1:8787/mcp")
        self.assertNotIn("command", cfg)

    def test_config_is_json_serialisable(self):
        json.dumps(mc.client_config())
        json.dumps(mc.client_config("http://x"))

    def test_default_server_name_is_glean(self):
        self.assertEqual(mc.DEFAULT_SERVER_NAME, "glean")
        self.assertIn("glean", mc.client_config()["mcpServers"])

    def test_name_override_changes_the_key(self):
        """Glean's own hosted MCP server also wants the 'glean' key."""
        cfg = mc.client_config(name="glean-cli")["mcpServers"]
        self.assertIn("glean-cli", cfg)
        self.assertNotIn("glean", cfg)

    def test_name_override_applies_to_the_url_form_too(self):
        cfg = mc.client_config("http://x", name="glean-cli")["mcpServers"]
        self.assertEqual(list(cfg), ["glean-cli"])

    def test_known_clients_have_a_config_location(self):
        for name, where in mc.CLIENTS.items():
            self.assertTrue(where, name)


class TestUptime(unittest.TestCase):
    def test_formats_by_magnitude(self):
        import time
        now = int(time.time())
        self.assertTrue(mc.uptime({"started_at": now}).endswith("s"))
        self.assertIn("m", mc.uptime({"started_at": now - 300}))
        self.assertIn("h", mc.uptime({"started_at": now - 7200}))

    def test_missing_timestamp_is_not_a_crash(self):
        self.assertEqual(mc.uptime({}), "unknown")


class TestDefaults(unittest.TestCase):
    def test_binds_loopback_only(self):
        """A live server may hold real credentials — never default to 0.0.0.0."""
        self.assertEqual(mc.DEFAULT_HOST, "127.0.0.1")

    def test_default_transport_is_not_stdio(self):
        self.assertNotEqual(mc.DEFAULT_TRANSPORT, "stdio")
        self.assertIn(mc.DEFAULT_TRANSPORT, mc.TRANSPORTS)

    def test_tool_names_match_the_server(self):
        source = (Path(__file__).parent.parent / "glean_mcp.py").read_text()
        for name in mc.tool_names():
            self.assertIn(f"def {name}(", source)


class TestMcpCommand(unittest.TestCase):
    def setUp(self):
        self.session = Session(Config(mode="mock"))

    def _run(self, pos, flags=None):
        buf = io.StringIO()
        with redirect_stdout(buf):
            HANDLERS["mcp"](self.session, pos, flags or {})
        return buf.getvalue()

    def test_bare_mcp_shows_status(self):
        with _StateDir():
            out = self._run([])
        self.assertIn("mcp package", out)
        self.assertIn("tools", out)

    def test_unknown_subcommand_errors(self):
        out = self._run(["frobnicate"])
        self.assertIn("Usage: /mcp", out)

    def test_config_prints_the_stdio_block(self):
        with _StateDir():
            out = self._run(["config"])
        self.assertIn("mcpServers", out)
        self.assertIn("glean_mcp.py", out)

    def test_config_warns_about_overwriting_the_default_name(self):
        with _StateDir():
            out = self._run(["config"])
        self.assertIn("--name glean-cli", out)

    def test_config_name_flag_is_honoured_and_drops_the_warning(self):
        with _StateDir():
            out = self._run(["config"], {"name": "glean-cli"})
        self.assertIn('"glean-cli"', out)
        self.assertNotIn("--name glean-cli", out)

    def test_config_rejects_an_unknown_client(self):
        with _StateDir():
            out = self._run(["config", "emacs"])
        self.assertIn("Unknown client", out)

    def test_config_url_without_a_server_errors(self):
        with _StateDir():
            out = self._run(["config"], {"url": True})
        self.assertIn("No server is running", out)

    def test_start_rejects_a_non_numeric_port(self):
        with _StateDir():
            out = self._run(["start"], {"port": "eight-thousand"})
        self.assertIn("--port must be an integer", out)

    def test_stop_without_a_server_is_not_an_error(self):
        with _StateDir():
            out = self._run(["stop"])
        self.assertIn("No server was running", out)


if __name__ == "__main__":
    unittest.main()
