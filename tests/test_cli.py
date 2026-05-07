"""Tests for glean_code.cli.main()"""
import sys
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch, MagicMock, call

sys.path.insert(0, str(Path(__file__).parent.parent))

from glean_code.config import Config


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _run_main(*, isatty=True, stdin_lines=None, input_side_effect=None,
              config=None):
    """Run cli.main() with mocked I/O.  Returns (printed_lines, session)."""
    if config is None:
        config = Config(mode="mock")

    captured = []

    # We use a mutable list so inner closures can append to it
    sessions_created = []

    _orig_session_init = None

    with patch("glean_code.cli.Config.load", return_value=config), \
         patch("glean_code.cli.setup_readline"), \
         patch("glean_code.ui.supports_colour", return_value=False), \
         patch("sys.stdin") as mock_stdin, \
         patch("builtins.print", side_effect=lambda *a, **k: captured.append(" ".join(str(x) for x in a))), \
         patch("builtins.input", side_effect=input_side_effect or [EOFError]):

        mock_stdin.isatty.return_value = isatty
        if stdin_lines is not None:
            mock_stdin.__iter__ = lambda self: iter(stdin_lines)

        from glean_code import cli
        with patch("glean_code.cli.dispatch") as mock_dispatch:
            cli.main()

    return captured, mock_dispatch


# ---------------------------------------------------------------------------
# non-interactive (piped) mode
# ---------------------------------------------------------------------------

class TestMainNonInteractive(unittest.TestCase):
    def test_dispatches_each_stdin_line(self):
        lines = ["/search foo\n", "/chat hello\n"]
        _, mock_dispatch = _run_main(isatty=False, stdin_lines=lines)
        self.assertEqual(mock_dispatch.call_count, 2)

    def test_dispatches_line_text_verbatim(self):
        _, mock_dispatch = _run_main(isatty=False, stdin_lines=["/status\n"])
        dispatched_line = mock_dispatch.call_args[0][1]
        self.assertEqual(dispatched_line, "/status\n")

    def test_empty_stdin_dispatches_nothing(self):
        _, mock_dispatch = _run_main(isatty=False, stdin_lines=[])
        mock_dispatch.assert_not_called()


# ---------------------------------------------------------------------------
# banner printed at startup
# ---------------------------------------------------------------------------

class TestMainBanner(unittest.TestCase):
    def test_banner_printed_on_startup(self):
        captured, _ = _run_main(input_side_effect=[EOFError])
        # banner contains the GLEAN wordmark block
        all_output = "\n".join(captured)
        # render_banner returns glean wordmark + meta; at minimum check version-ish content
        self.assertTrue(len(all_output) > 0)

    def test_setup_readline_called_in_interactive_mode(self):
        with patch("glean_code.cli.Config.load", return_value=Config(mode="mock")), \
             patch("glean_code.ui.supports_colour", return_value=False), \
             patch("sys.stdin") as mock_stdin, \
             patch("builtins.print"), \
             patch("builtins.input", side_effect=[EOFError]), \
             patch("glean_code.cli.dispatch"), \
             patch("glean_code.cli.setup_readline") as mock_setup:
            mock_stdin.isatty.return_value = True
            from glean_code import cli
            cli.main()
        mock_setup.assert_called_once()

    def test_setup_readline_not_called_in_pipe_mode(self):
        with patch("glean_code.cli.Config.load", return_value=Config(mode="mock")), \
             patch("glean_code.ui.supports_colour", return_value=False), \
             patch("sys.stdin") as mock_stdin, \
             patch("builtins.print"), \
             patch("glean_code.cli.dispatch"), \
             patch("glean_code.cli.setup_readline") as mock_setup:
            mock_stdin.isatty.return_value = False
            mock_stdin.__iter__ = lambda self: iter([])
            from glean_code import cli
            cli.main()
        mock_setup.assert_not_called()


# ---------------------------------------------------------------------------
# interactive REPL loop behaviour
# ---------------------------------------------------------------------------

class TestMainInteractiveLoop(unittest.TestCase):
    def test_eoferror_exits_loop(self):
        """EOFError from input() should exit cleanly (no crash)."""
        captured, _ = _run_main(input_side_effect=[EOFError])
        # No exception propagated; just verifying no crash

    def test_keyboardinterrupt_exits_loop(self):
        """KeyboardInterrupt from input() should exit cleanly."""
        captured, _ = _run_main(input_side_effect=[KeyboardInterrupt])
        # No exception propagated

    def test_dispatch_called_for_each_input_line(self):
        # Two normal inputs then EOFError to stop the loop
        with patch("glean_code.cli.Config.load", return_value=Config(mode="mock")), \
             patch("glean_code.cli.setup_readline"), \
             patch("glean_code.ui.supports_colour", return_value=False), \
             patch("sys.stdin") as mock_stdin, \
             patch("builtins.print"), \
             patch("builtins.input", side_effect=["/status", "/help", EOFError]):
            mock_stdin.isatty.return_value = True
            from glean_code import cli
            with patch("glean_code.cli.dispatch") as mock_dispatch:
                cli.main()
        self.assertEqual(mock_dispatch.call_count, 2)

    def test_unhandled_exception_in_dispatch_does_not_crash_repl(self):
        """An exception thrown by dispatch should be caught and printed, not propagated."""
        with patch("glean_code.cli.Config.load", return_value=Config(mode="mock")), \
             patch("glean_code.cli.setup_readline"), \
             patch("glean_code.ui.supports_colour", return_value=False), \
             patch("sys.stdin") as mock_stdin, \
             patch("builtins.print"), \
             patch("builtins.input", side_effect=["boom", EOFError]):
            mock_stdin.isatty.return_value = True
            from glean_code import cli

            def _raise(*a, **k):
                raise RuntimeError("test explosion")

            with patch("glean_code.cli.dispatch", side_effect=_raise):
                # Should complete without raising
                cli.main()

    def test_session_running_false_exits_loop(self):
        """If dispatch sets session.running=False, the loop should exit."""
        with patch("glean_code.cli.Config.load", return_value=Config(mode="mock")), \
             patch("glean_code.cli.setup_readline"), \
             patch("glean_code.ui.supports_colour", return_value=False), \
             patch("sys.stdin") as mock_stdin, \
             patch("builtins.print"), \
             patch("builtins.input", return_value="/exit"):
            mock_stdin.isatty.return_value = True
            from glean_code import cli
            # Let the real dispatch run; /exit sets session.running=False
            cli.main()
            # If we get here without hanging, the loop exited correctly


if __name__ == "__main__":
    unittest.main()
