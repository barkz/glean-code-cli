"""Tests for glean_code.completion"""
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from glean_code.completion import _Completer, setup_readline, _FLAG_VALUES, _CONFIG_KEYS, _CONFIG_SUBCMDS


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _rl(buf, endidx=None):
    """Return a mock readline module with get_line_buffer/get_endidx set."""
    m = MagicMock()
    m.get_line_buffer.return_value = buf
    m.get_endidx.return_value = len(buf) if endidx is None else endidx
    return m


def _complete(buf, text="", endidx=None):
    """Run _Completer._complete with a faked readline state."""
    rl = _rl(buf, endidx)
    with patch("glean_code.completion._HAS_READLINE", True), \
         patch("glean_code.completion.readline", rl):
        return _Completer()._complete(text)


# ---------------------------------------------------------------------------
# __call__ state cycling
# ---------------------------------------------------------------------------

class TestCompleterCall(unittest.TestCase):
    def test_state_zero_returns_first_match(self):
        c = _Completer()
        rl = _rl("/sea")
        with patch("glean_code.completion._HAS_READLINE", True), \
             patch("glean_code.completion.readline", rl):
            result = c("/sea", 0)
        self.assertEqual(result, "/search")

    def test_state_one_returns_second_match(self):
        c = _Completer()
        rl = _rl("/s")
        with patch("glean_code.completion._HAS_READLINE", True), \
             patch("glean_code.completion.readline", rl):
            first  = c("/s", 0)
            second = c("/s", 1)
        self.assertIsNotNone(first)
        self.assertIsNotNone(second)
        self.assertNotEqual(first, second)

    def test_out_of_range_state_returns_none(self):
        c = _Completer()
        rl = _rl("/search")
        with patch("glean_code.completion._HAS_READLINE", True), \
             patch("glean_code.completion.readline", rl):
            c("/search", 0)        # populate matches (exactly 1)
            result = c("/search", 1)  # only 1 match, state=1 -> None
        self.assertIsNone(result)


# ---------------------------------------------------------------------------
# no readline
# ---------------------------------------------------------------------------

class TestCompleterNoReadline(unittest.TestCase):
    def test_returns_empty_when_no_readline(self):
        with patch("glean_code.completion._HAS_READLINE", False):
            result = _Completer()._complete("text")
        self.assertEqual(result, [])


# ---------------------------------------------------------------------------
# command completion
# ---------------------------------------------------------------------------

class TestCompleterCommandCompletion(unittest.TestCase):
    def test_empty_buffer_returns_all_slash_commands(self):
        results = _complete("", "")
        self.assertTrue(all(r.startswith("/") for r in results))
        self.assertIn("/search", results)
        self.assertIn("/chat", results)

    def test_partial_prefix_filters(self):
        results = _complete("/sea", "sea")
        self.assertIn("/search", results)
        self.assertNotIn("/chat", results)

    def test_slash_stripped_for_prefix_match(self):
        results = _complete("/ch", "ch")
        self.assertIn("/chat", results)

    def test_results_are_sorted(self):
        results = _complete("", "")
        self.assertEqual(results, sorted(results))

    def test_unclosed_quote_returns_empty(self):
        results = _complete('/search "unclosed', "")
        self.assertEqual(results, [])


# ---------------------------------------------------------------------------
# flag name completion
# ---------------------------------------------------------------------------

class TestCompleterFlagCompletion(unittest.TestCase):
    def test_dash_prefix_triggers_flag_completion(self):
        results = _complete("/search --p", "--p")
        self.assertIn("--page-size", results)

    def test_unknown_command_returns_empty_flags(self):
        results = _complete("/unknowncmd --p", "--p")
        self.assertEqual(results, [])

    def test_exact_flag_returned(self):
        results = _complete("/search --datasource", "--datasource")
        self.assertIn("--datasource", results)

    def test_double_dash_alone_returns_all_flags(self):
        results = _complete("/search --", "--")
        self.assertTrue(all(r.startswith("--") for r in results))


# ---------------------------------------------------------------------------
# enum value completion (after a known flag)
# ---------------------------------------------------------------------------

class TestCompleterEnumValues(unittest.TestCase):
    def test_mode_flag_returns_mode_values(self):
        results = _complete("/search --mode ", "")
        self.assertEqual(sorted(results), sorted(_FLAG_VALUES["mode"]))

    def test_mode_flag_partial_filters(self):
        results = _complete("/search --mode li", "li")
        self.assertIn("live", results)
        self.assertNotIn("mock", results)

    def test_kind_flag_returns_kind_values(self):
        results = _complete("/entities.list --kind ", "")
        self.assertEqual(sorted(results), sorted(_FLAG_VALUES["kind"]))


# ---------------------------------------------------------------------------
# /mode command completion
# ---------------------------------------------------------------------------

class TestCompleterModeCommand(unittest.TestCase):
    def test_mode_command_blank_returns_all_values(self):
        results = _complete("/mode ", "")
        self.assertEqual(sorted(results), sorted(_FLAG_VALUES["mode"]))

    def test_mode_command_partial_filters(self):
        results = _complete("/mode mo", "mo")
        self.assertIn("mock", results)
        self.assertNotIn("live", results)


# ---------------------------------------------------------------------------
# /config completion
# ---------------------------------------------------------------------------

class TestCompleterConfigSubcmd(unittest.TestCase):
    def test_config_blank_returns_subcmds(self):
        results = _complete("/config ", "")
        self.assertEqual(sorted(results), sorted(_CONFIG_SUBCMDS))

    def test_config_partial_subcmd(self):
        results = _complete("/config s", "s")
        self.assertIn("set", results)
        self.assertNotIn("list", results)

    def test_config_set_blank_returns_keys(self):
        results = _complete("/config set ", "")
        self.assertEqual(sorted(results), sorted(_CONFIG_KEYS))

    def test_config_set_partial_key(self):
        results = _complete("/config set ap", "ap")
        self.assertIn("api_token", results)
        self.assertNotIn("instance", results)

    def test_config_set_mode_returns_mode_values(self):
        results = _complete("/config set mode ", "")
        self.assertEqual(sorted(results), sorted(_FLAG_VALUES["mode"]))

    def test_config_get_blank_returns_keys(self):
        results = _complete("/config get ", "")
        self.assertEqual(sorted(results), sorted(_CONFIG_KEYS))


# ---------------------------------------------------------------------------
# /help completion
# ---------------------------------------------------------------------------

class TestCompleterHelpCommand(unittest.TestCase):
    def test_help_blank_returns_command_names_without_slash(self):
        results = _complete("/help ", "")
        self.assertIn("search", results)
        self.assertIn("chat", results)
        self.assertFalse(any(r.startswith("/") for r in results))

    def test_help_partial_filters(self):
        results = _complete("/help sea", "sea")
        self.assertIn("search", results)
        self.assertNotIn("chat", results)


# ---------------------------------------------------------------------------
# /scaffold completion
# ---------------------------------------------------------------------------

class TestCompleterScaffoldCommand(unittest.TestCase):
    def test_scaffold_blank_returns_all_templates(self):
        results = _complete("/scaffold ", "")
        self.assertEqual(sorted(results), sorted(["chat", "search", "agent"]))

    def test_scaffold_partial_filters(self):
        results = _complete("/scaffold ch", "ch")
        self.assertIn("chat", results)
        self.assertNotIn("agent", results)


# ---------------------------------------------------------------------------
# fallback: blank slot shows available flags for known command
# ---------------------------------------------------------------------------

class TestCompleterFallback(unittest.TestCase):
    def test_blank_text_after_known_command_shows_flags(self):
        results = _complete("/search ", "")
        self.assertTrue(all(r.startswith("--") for r in results))

    def test_blank_text_after_unknown_command_returns_empty(self):
        results = _complete("/fakecommand ", "")
        self.assertEqual(results, [])


# ---------------------------------------------------------------------------
# setup_readline
# ---------------------------------------------------------------------------

class TestSetupReadline(unittest.TestCase):
    def test_does_nothing_when_no_readline(self):
        with patch("glean_code.completion._HAS_READLINE", False):
            setup_readline()  # should not raise

    def test_sets_completer_when_readline_available(self):
        mock_rl = MagicMock()
        mock_rl.__doc__ = "GNU readline"
        with patch("glean_code.completion._HAS_READLINE", True), \
             patch("glean_code.completion.readline", mock_rl):
            setup_readline()
        mock_rl.set_completer.assert_called_once()

    def test_sets_completer_delims(self):
        mock_rl = MagicMock()
        mock_rl.__doc__ = "GNU readline"
        with patch("glean_code.completion._HAS_READLINE", True), \
             patch("glean_code.completion.readline", mock_rl):
            setup_readline()
        mock_rl.set_completer_delims.assert_called_once_with(" \t")

    def test_libedit_uses_rl_complete_bind(self):
        mock_rl = MagicMock()
        mock_rl.__doc__ = "libedit wrapped by readline"
        with patch("glean_code.completion._HAS_READLINE", True), \
             patch("glean_code.completion.readline", mock_rl):
            setup_readline()
        calls = [str(c) for c in mock_rl.parse_and_bind.call_args_list]
        self.assertTrue(any("rl_complete" in c for c in calls))

    def test_gnu_readline_uses_menu_complete_bind(self):
        mock_rl = MagicMock()
        mock_rl.__doc__ = "GNU readline"
        with patch("glean_code.completion._HAS_READLINE", True), \
             patch("glean_code.completion.readline", mock_rl):
            setup_readline()
        calls = [str(c) for c in mock_rl.parse_and_bind.call_args_list]
        self.assertTrue(any("menu-complete" in c for c in calls))


if __name__ == "__main__":
    unittest.main()
