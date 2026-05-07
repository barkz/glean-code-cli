"""Tests for glean_code.ui"""
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from glean_code import ui


class TestVisLen(unittest.TestCase):
    def test_plain_text(self):
        self.assertEqual(ui._vis("hello"), 5)

    def test_empty_string(self):
        self.assertEqual(ui._vis(""), 0)

    def test_single_ansi_code_ignored(self):
        self.assertEqual(ui._vis("\033[1mhello\033[0m"), 5)

    def test_multiple_ansi_codes_ignored(self):
        styled = f"\033[1m\033[38;5;33mhello\033[0m"
        self.assertEqual(ui._vis(styled), 5)

    def test_ansi_in_middle_of_text(self):
        s = "hi \033[1mbold\033[0m end"
        self.assertEqual(ui._vis(s), 11)

    def test_no_ansi(self):
        self.assertEqual(ui._vis("abc def"), 7)


class TestLjust(unittest.TestCase):
    def test_pads_short_string(self):
        self.assertEqual(ui._ljust("hi", 5), "hi   ")

    def test_no_pad_when_exact_width(self):
        self.assertEqual(ui._ljust("hello", 5), "hello")

    def test_no_pad_when_longer_than_width(self):
        self.assertEqual(ui._ljust("hello world", 5), "hello world")

    def test_pads_ansi_string_to_correct_visible_width(self):
        styled = "\033[1mhi\033[0m"  # visible len = 2
        result = ui._ljust(styled, 6)
        self.assertEqual(ui._vis(result), 6)


class TestSplitAt(unittest.TestCase):
    def test_split_plain_text(self):
        head, tail = ui._split_at("hello world", 5)
        self.assertEqual(head, "hello")
        self.assertEqual(tail, " world")

    def test_split_at_zero(self):
        head, tail = ui._split_at("abc", 0)
        self.assertEqual(head, "")
        self.assertEqual(tail, "abc")

    def test_split_past_end(self):
        head, tail = ui._split_at("abc", 100)
        self.assertEqual(head, "abc")
        self.assertEqual(tail, "")

    def test_split_with_ansi_preserves_visible_boundary(self):
        styled = "\033[1mhello\033[0m world"
        head, tail = ui._split_at(styled, 5)
        self.assertEqual(ui._vis(head), 5)


class TestSupportsColour(unittest.TestCase):
    def test_no_color_env_disables_colour(self):
        with patch.dict(os.environ, {"NO_COLOR": "1"}):
            self.assertFalse(ui.supports_colour())

    def test_non_tty_disables_colour(self):
        env = {k: v for k, v in os.environ.items() if k != "NO_COLOR"}
        with patch.dict(os.environ, env, clear=True), \
             patch("sys.stdout") as mock_stdout:
            mock_stdout.isatty.return_value = False
            self.assertFalse(ui.supports_colour())

    def test_tty_without_no_color_enables_colour(self):
        env = {k: v for k, v in os.environ.items() if k != "NO_COLOR"}
        with patch.dict(os.environ, env, clear=True), \
             patch("sys.stdout") as mock_stdout:
            mock_stdout.isatty.return_value = True
            self.assertTrue(ui.supports_colour())


class TestStyle(unittest.TestCase):
    def test_returns_plain_text_when_no_colour(self):
        with patch("glean_code.ui.supports_colour", return_value=False):
            self.assertEqual(ui.style("hello", ui.C.BOLD), "hello")

    def test_wraps_with_codes_when_colour_enabled(self):
        with patch("glean_code.ui.supports_colour", return_value=True):
            result = ui.style("hello", ui.C.BLUE)
        self.assertIn("hello", result)
        self.assertIn(ui.C.BLUE, result)
        self.assertIn(ui.C.RESET, result)

    def test_multiple_codes_all_applied(self):
        with patch("glean_code.ui.supports_colour", return_value=True):
            result = ui.style("text", ui.C.BOLD, ui.C.RED)
        self.assertIn(ui.C.BOLD, result)
        self.assertIn(ui.C.RED, result)

    def test_empty_string_returns_empty(self):
        with patch("glean_code.ui.supports_colour", return_value=False):
            self.assertEqual(ui.style("", ui.C.BOLD), "")


class TestKvTable(unittest.TestCase):
    def test_empty_rows_returns_empty_string(self):
        self.assertEqual(ui.kv_table([]), "")

    def test_single_row_contains_key_and_value(self):
        with patch("glean_code.ui.supports_colour", return_value=False):
            result = ui.kv_table([("key", "value")])
        self.assertIn("key", result)
        self.assertIn("value", result)

    def test_values_aligned_across_rows(self):
        with patch("glean_code.ui.supports_colour", return_value=False):
            result = ui.kv_table([("short", "v1"), ("much_longer_key", "v2")])
        lines = result.splitlines()
        self.assertEqual(len(lines), 2)
        pos0 = lines[0].index("v1")
        pos1 = lines[1].index("v2")
        self.assertEqual(pos0, pos1)

    def test_all_values_present(self):
        with patch("glean_code.ui.supports_colour", return_value=False):
            result = ui.kv_table([("a", "alpha"), ("b", "beta")])
        self.assertIn("alpha", result)
        self.assertIn("beta", result)


class TestBulletList(unittest.TestCase):
    def test_each_item_on_own_line(self):
        with patch("glean_code.ui.supports_colour", return_value=False):
            result = ui.bullet_list(["a", "b", "c"])
        self.assertEqual(len(result.splitlines()), 3)

    def test_items_present_in_output(self):
        with patch("glean_code.ui.supports_colour", return_value=False):
            result = ui.bullet_list(["alpha", "beta"])
        self.assertIn("alpha", result)
        self.assertIn("beta", result)

    def test_empty_list_returns_empty_string(self):
        self.assertEqual(ui.bullet_list([]), "")

    def test_default_marker_is_triangle(self):
        with patch("glean_code.ui.supports_colour", return_value=False):
            result = ui.bullet_list(["item"])
        self.assertIn("\u25b8", result)

    def test_custom_marker(self):
        with patch("glean_code.ui.supports_colour", return_value=False):
            result = ui.bullet_list(["item"], marker="-")
        self.assertIn("-", result)


class TestRule(unittest.TestCase):
    def test_rule_without_label_fills_width(self):
        with patch("glean_code.ui.supports_colour", return_value=False), \
             patch("glean_code.ui.term_width", return_value=40):
            result = ui.rule()
        self.assertEqual(len(result), 40)
        self.assertTrue(all(c == "\u2500" for c in result))

    def test_rule_with_label_contains_label(self):
        with patch("glean_code.ui.supports_colour", return_value=False):
            result = ui.rule("my section")
        self.assertIn("my section", result)

    def test_rule_with_label_has_dashes(self):
        with patch("glean_code.ui.supports_colour", return_value=False):
            result = ui.rule("label")
        self.assertIn("\u2500", result)


class TestBox(unittest.TestCase):
    def test_box_contains_title(self):
        with patch("glean_code.ui.supports_colour", return_value=False), \
             patch("glean_code.ui.term_width", return_value=60):
            result = ui.box("My Title", "Body text here")
        self.assertIn("My Title", result)

    def test_box_contains_body(self):
        with patch("glean_code.ui.supports_colour", return_value=False), \
             patch("glean_code.ui.term_width", return_value=60):
            result = ui.box("T", "the body content")
        self.assertIn("the body content", result)

    def test_box_has_unicode_corners(self):
        with patch("glean_code.ui.supports_colour", return_value=False), \
             patch("glean_code.ui.term_width", return_value=60):
            result = ui.box("T", "B")
        self.assertIn("\u256d", result)  # top-left corner
        self.assertIn("\u2570", result)  # bottom-left corner

    def test_box_multiline_body(self):
        with patch("glean_code.ui.supports_colour", return_value=False), \
             patch("glean_code.ui.term_width", return_value=60):
            result = ui.box("T", "line one\nline two\nline three")
        self.assertIn("line one", result)
        self.assertIn("line three", result)

    def test_box_empty_body(self):
        with patch("glean_code.ui.supports_colour", return_value=False), \
             patch("glean_code.ui.term_width", return_value=60):
            result = ui.box("Title", "")
        self.assertIn("Title", result)


class TestPrintHelpers(unittest.TestCase):
    def test_print_err_contains_message(self):
        with patch("glean_code.ui.supports_colour", return_value=False), \
             patch("builtins.print") as mock_print:
            ui.print_err("something broke")
        self.assertIn("something broke", mock_print.call_args[0][0])

    def test_print_ok_contains_message(self):
        with patch("glean_code.ui.supports_colour", return_value=False), \
             patch("builtins.print") as mock_print:
            ui.print_ok("all good")
        self.assertIn("all good", mock_print.call_args[0][0])

    def test_print_info_contains_message(self):
        with patch("glean_code.ui.supports_colour", return_value=False), \
             patch("builtins.print") as mock_print:
            ui.print_info("for your info")
        self.assertIn("for your info", mock_print.call_args[0][0])


class TestPromptStr(unittest.TestCase):
    def test_contains_glean_label(self):
        with patch("glean_code.ui.supports_colour", return_value=False):
            result = ui.prompt_str("live")
        self.assertIn("glean", result)

    def test_contains_arrow(self):
        with patch("glean_code.ui.supports_colour", return_value=False):
            result = ui.prompt_str("mock")
        self.assertIn("\u203a", result)  # ›


class TestStatusBar(unittest.TestCase):
    def test_returns_empty_when_no_colour(self):
        with patch("glean_code.ui.supports_colour", return_value=False):
            self.assertEqual(ui.status_bar("mock"), "")

    def test_contains_live_label(self):
        with patch("glean_code.ui.supports_colour", return_value=True), \
             patch("glean_code.ui.term_width", return_value=80):
            result = ui.status_bar("live")
        self.assertIn("LIVE", result)

    def test_contains_mock_label(self):
        with patch("glean_code.ui.supports_colour", return_value=True), \
             patch("glean_code.ui.term_width", return_value=80):
            result = ui.status_bar("mock")
        self.assertIn("MOCK", result)

    def test_contains_instance_when_set(self):
        with patch("glean_code.ui.supports_colour", return_value=True), \
             patch("glean_code.ui.term_width", return_value=120):
            result = ui.status_bar("live", instance="acme-be.glean.com")
        self.assertIn("acme-be.glean.com", result)

    def test_strips_https_scheme_from_instance(self):
        with patch("glean_code.ui.supports_colour", return_value=True), \
             patch("glean_code.ui.term_width", return_value=120):
            result = ui.status_bar("live", instance="https://acme-be.glean.com")
        self.assertIn("acme-be.glean.com", result)

    def test_truncates_long_chat_id(self):
        with patch("glean_code.ui.supports_colour", return_value=True), \
             patch("glean_code.ui.term_width", return_value=160):
            result = ui.status_bar("live", chat_id="a" * 20)
        self.assertIn("\u2026", result)  # ellipsis

    def test_short_chat_id_not_truncated(self):
        with patch("glean_code.ui.supports_colour", return_value=True), \
             patch("glean_code.ui.term_width", return_value=160):
            result = ui.status_bar("live", chat_id="short-id")
        self.assertIn("short-id", result)
        self.assertNotIn("\u2026", result)


if __name__ == "__main__":
    unittest.main()
