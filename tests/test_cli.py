"""Tests for glean_code.cli.main()"""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

from glean_code.config import Config


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _run_main(*, isatty=True, stdin_lines=None, input_side_effect=None, config=None):
    """Run cli.main() with mocked I/O.  Returns (captured_lines, mock_dispatch)."""
    if config is None:
        config = Config(mode="mock")

    captured = []

    with patch("glean_code.cli.Config.load", return_value=config), \
         patch("glean_code.cli.setup_readline"), \
         patch("glean_code.ui.supports_colour", return_value=False), \
         patch("sys.stdin") as mock_stdin, \
         patch("builtins.print",
               side_effect=lambda *a, **k: captured.append(" ".join(str(x) for x in a))), \
         patch("builtins.input",
               side_effect=input_side_effect if input_side_effect is not None else [EOFError]):

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
# setup_readline called in interactive mode only
# ---------------------------------------------------------------------------

class TestMainReadlineSetup(unittest.TestCase):
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
    def test_eoferror_exits_loop_cleanly(self):
        # Should not raise; just exits
        _run_main(input_side_effect=[EOFError])

    def test_keyboardinterrupt_exits_loop_cleanly(self):
        _run_main(input_side_effect=[KeyboardInterrupt])

    def test_dispatch_called_for_each_input_line(self):
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
        """An exception thrown by dispatch is caught; the REPL continues."""
        def _raise(*a, **k):
            raise RuntimeError("test explosion")

        with patch("glean_code.cli.Config.load", return_value=Config(mode="mock")), \
             patch("glean_code.cli.setup_readline"), \
             patch("glean_code.ui.supports_colour", return_value=False), \
             patch("sys.stdin") as mock_stdin, \
             patch("builtins.print"), \
             patch("builtins.input", side_effect=["boom", EOFError]):
            mock_stdin.isatty.return_value = True
            from glean_code import cli
            with patch("glean_code.cli.dispatch", side_effect=_raise):
                cli.main()  # must not raise

    def test_session_running_false_exits_loop(self):
        """/exit sets session.running=False which stops the REPL."""
        with patch("glean_code.cli.Config.load", return_value=Config(mode="mock")), \
             patch("glean_code.cli.setup_readline"), \
             patch("glean_code.ui.supports_colour", return_value=False), \
             patch("sys.stdin") as mock_stdin, \
             patch("builtins.print"), \
             patch("builtins.input", return_value="/exit"):
            mock_stdin.isatty.return_value = True
            from glean_code import cli
            cli.main()
            # Getting here without hanging means the loop exited

    def test_banner_printed_at_startup(self):
        captured, _ = _run_main(input_side_effect=[EOFError])
        all_output = "\n".join(captured)
        self.assertTrue(len(all_output) > 0)


if __name__ == "__main__":
    unittest.main()
