"""Tests for remaining untested functions:
  - glean_code.commands._sanitize_for_history
  - glean_code.commands._display_token
  - glean_code.commands.cmd_doctor
  - glean_code.ui.hyperlink
  - glean_code.ui.render_banner
"""
import os
import socket
import sys
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

from glean_code import ui
from glean_code.commands import (
    _sanitize_for_history,
    _display_token,
    cmd_doctor,
    Session,
)
from glean_code.config import Config


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _sess(**cfg_kwargs):
    s = Session(Config(mode="mock", **cfg_kwargs))
    s.client = MagicMock()
    return s


def _output(fn, *args, **kwargs):
    """Capture all print() calls made by fn and return as joined string."""
    lines = []
    with patch("builtins.print",
               side_effect=lambda *a, **k: lines.append(" ".join(str(x) for x in a))):
        fn(*args, **kwargs)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# _sanitize_for_history
# ---------------------------------------------------------------------------

class TestSanitizeForHistory(unittest.TestCase):
    def test_plain_command_not_masked(self):
        result = _sanitize_for_history("/search pto policy")
        self.assertIn("search", result)
        self.assertNotIn("***", result)

    def test_token_flag_value_masked(self):
        result = _sanitize_for_history("/login --instance acme.com --token glean_tok_ABCDEFGH")
        self.assertIn("***", result)
        self.assertNotIn("glean_tok_ABCDEFGH", result)

    def test_indexing_token_hyphen_variant_masked(self):
        result = _sanitize_for_history("/login --indexing-token idx_secret1234")
        self.assertIn("***", result)
        self.assertNotIn("idx_secret1234", result)

    def test_indexing_token_underscore_variant_masked(self):
        result = _sanitize_for_history("/login --indexing_token idx_secret1234")
        self.assertIn("***", result)
        self.assertNotIn("idx_secret1234", result)

    def test_config_set_api_token_masked(self):
        result = _sanitize_for_history("/config set api_token glean_tok_SECRETVALUE")
        self.assertIn("***", result)
        self.assertNotIn("glean_tok_SECRETVALUE", result)

    def test_config_set_indexing_token_masked(self):
        result = _sanitize_for_history("/config set indexing_token idx_SECRETVALUE")
        self.assertIn("***", result)
        self.assertNotIn("idx_SECRETVALUE", result)

    def test_secure_ref_kept_verbatim_in_token_flag(self):
        result = _sanitize_for_history("/login --token token.secure.client")
        self.assertIn("token.secure.client", result)
        self.assertNotIn("***", result)

    def test_secure_ref_kept_verbatim_in_config_set(self):
        result = _sanitize_for_history("/config set api_token token.secure.client")
        self.assertIn("token.secure.client", result)
        self.assertNotIn("***", result)

    def test_malformed_unclosed_quote_returned_as_is(self):
        line = '/login --token "unclosed'
        result = _sanitize_for_history(line)
        self.assertEqual(result, line)

    def test_other_flags_not_masked(self):
        result = _sanitize_for_history("/login --instance acme-be.glean.com")
        self.assertIn("acme-be.glean.com", result)
        self.assertNotIn("***", result)

    def test_empty_string_returns_empty(self):
        self.assertEqual(_sanitize_for_history(""), "")


# ---------------------------------------------------------------------------
# _display_token
# ---------------------------------------------------------------------------

class TestDisplayToken(unittest.TestCase):
    def test_none_returns_unset_indicator(self):
        with patch("glean_code.ui.supports_colour", return_value=False):
            result = _display_token(None)
        self.assertIn("unset", result.lower())

    def test_empty_string_returns_unset_indicator(self):
        with patch("glean_code.ui.supports_colour", return_value=False):
            result = _display_token("")
        self.assertIn("unset", result.lower())

    def test_regular_token_masked_to_last_four(self):
        with patch("glean_code.ui.supports_colour", return_value=False):
            result = _display_token("glean_tok_ABCD")
        self.assertIn("***ABCD", result)
        self.assertNotIn("glean_tok", result)

    def test_short_token_still_shows_last_four(self):
        with patch("glean_code.ui.supports_colour", return_value=False):
            result = _display_token("abcd")
        self.assertIn("***abcd", result)

    def test_secure_ref_with_env_set_shows_set(self):
        with patch("glean_code.ui.supports_colour", return_value=False), \
             patch.dict("os.environ", {"GLEAN_CLIENT_TOKEN": "real_tok"}):
            result = _display_token("token.secure.client")
        self.assertIn("token.secure.client", result)
        self.assertIn("set", result.lower())

    def test_secure_ref_without_env_shows_not_set(self):
        clean_env = {k: v for k, v in os.environ.items() if k != "GLEAN_CLIENT_TOKEN"}
        with patch("glean_code.ui.supports_colour", return_value=False), \
             patch.dict("os.environ", clean_env, clear=True):
            result = _display_token("token.secure.client")
        self.assertIn("token.secure.client", result)
        self.assertIn("not set", result.lower())


# ---------------------------------------------------------------------------
# cmd_doctor helpers
# ---------------------------------------------------------------------------

_GOOD_ADDRINFO = [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("1.2.3.4", 443))]


class _MockConn:
    """Context manager mimicking socket.create_connection."""
    def __enter__(self): return self
    def __exit__(self, *a): pass


class _MockResp:
    """Context manager mimicking urllib.request.urlopen."""
    def __init__(self, status=200): self.status = status
    def __enter__(self): return self
    def __exit__(self, *a): pass


# ---------------------------------------------------------------------------
# cmd_doctor
# ---------------------------------------------------------------------------

class TestCmdDoctor(unittest.TestCase):
    def _doctor(self, **cfg_kwargs):
        s = _sess(**cfg_kwargs)
        with patch("glean_code.ui.supports_colour", return_value=False):
            out = _output(cmd_doctor, s, [], {})
        return out

    def test_no_instance_prints_warn(self):
        out = self._doctor()
        self.assertIn("WARN", out)

    def test_no_token_prints_warn(self):
        out = self._doctor(instance="acme-be.glean.com")
        self.assertIn("WARN", out)

    def test_no_base_url_prints_fail_and_stops(self):
        # no instance -> effective_base_url is None -> FAIL, returns early
        out = self._doctor()
        self.assertIn("FAIL", out)

    def test_instance_shown_in_ok_line(self):
        with patch("glean_code.commands.socket.getaddrinfo", return_value=_GOOD_ADDRINFO), \
             patch("glean_code.commands.socket.create_connection", return_value=_MockConn()), \
             patch("glean_code.ui.supports_colour", return_value=False):
            s = _sess(instance="acme-be.glean.com", api_token="tok", mode="mock")
            out = _output(cmd_doctor, s, [], {})
        self.assertIn("acme-be.glean.com", out)

    def test_dns_failure_prints_fail(self):
        with patch("glean_code.commands.socket.getaddrinfo",
                   side_effect=socket.gaierror("NXDOMAIN")), \
             patch("glean_code.ui.supports_colour", return_value=False):
            s = _sess(instance="bad.glean.com", api_token="tok", mode="mock")
            out = _output(cmd_doctor, s, [], {})
        self.assertIn("FAIL", out)
        self.assertIn("dns", out.lower())

    def test_tcp_failure_prints_fail(self):
        with patch("glean_code.commands.socket.getaddrinfo", return_value=_GOOD_ADDRINFO), \
             patch("glean_code.commands.socket.create_connection",
                   side_effect=OSError("connection refused")), \
             patch("glean_code.ui.supports_colour", return_value=False):
            s = _sess(instance="acme-be.glean.com", api_token="tok", mode="mock")
            out = _output(cmd_doctor, s, [], {})
        self.assertIn("FAIL", out)
        self.assertIn("tcp", out.lower())

    def test_mock_mode_skips_auth_probe(self):
        with patch("glean_code.commands.socket.getaddrinfo", return_value=_GOOD_ADDRINFO), \
             patch("glean_code.commands.socket.create_connection", return_value=_MockConn()), \
             patch("glean_code.ui.supports_colour", return_value=False):
            s = _sess(instance="acme-be.glean.com", api_token="tok", mode="mock")
            out = _output(cmd_doctor, s, [], {})
        self.assertIn("SKIP", out)
        self.assertIn("auth probe", out.lower())

    def test_auth_probe_success_prints_ok(self):
        with patch("glean_code.commands.socket.getaddrinfo", return_value=_GOOD_ADDRINFO), \
             patch("glean_code.commands.socket.create_connection", return_value=_MockConn()), \
             patch("glean_code.commands.urllib.request.urlopen",
                   return_value=_MockResp(200)), \
             patch("glean_code.ui.supports_colour", return_value=False):
            s = _sess(instance="acme-be.glean.com", api_token="tok", mode="live")
            out = _output(cmd_doctor, s, [], {})
        self.assertIn("OK", out)
        self.assertIn("auth probe", out.lower())

    def test_auth_probe_401_prints_fail(self):
        http_err = urllib.error.HTTPError("url", 401, "Unauthorized", {}, None)
        with patch("glean_code.commands.socket.getaddrinfo", return_value=_GOOD_ADDRINFO), \
             patch("glean_code.commands.socket.create_connection", return_value=_MockConn()), \
             patch("glean_code.commands.urllib.request.urlopen", side_effect=http_err), \
             patch("glean_code.ui.supports_colour", return_value=False):
            s = _sess(instance="acme-be.glean.com", api_token="tok", mode="live")
            out = _output(cmd_doctor, s, [], {})
        self.assertIn("FAIL", out)
        self.assertIn("401", out)

    def test_auth_probe_404_prints_fail_with_endpoint_hint(self):
        http_err = urllib.error.HTTPError("url", 404, "Not Found", {}, None)
        with patch("glean_code.commands.socket.getaddrinfo", return_value=_GOOD_ADDRINFO), \
             patch("glean_code.commands.socket.create_connection", return_value=_MockConn()), \
             patch("glean_code.commands.urllib.request.urlopen", side_effect=http_err), \
             patch("glean_code.ui.supports_colour", return_value=False):
            s = _sess(instance="acme-be.glean.com", api_token="tok", mode="live")
            out = _output(cmd_doctor, s, [], {})
        self.assertIn("FAIL", out)
        self.assertIn("404", out)

    def test_auth_probe_url_error_prints_fail(self):
        url_err = urllib.error.URLError("SSL error")
        with patch("glean_code.commands.socket.getaddrinfo", return_value=_GOOD_ADDRINFO), \
             patch("glean_code.commands.socket.create_connection", return_value=_MockConn()), \
             patch("glean_code.commands.urllib.request.urlopen", side_effect=url_err), \
             patch("glean_code.ui.supports_colour", return_value=False):
            s = _sess(instance="acme-be.glean.com", api_token="tok", mode="live")
            out = _output(cmd_doctor, s, [], {})
        self.assertIn("FAIL", out)

    def test_secure_ref_token_with_env_shows_ok(self):
        with patch("glean_code.commands.socket.getaddrinfo", return_value=_GOOD_ADDRINFO), \
             patch("glean_code.commands.socket.create_connection", return_value=_MockConn()), \
             patch("glean_code.ui.supports_colour", return_value=False), \
             patch.dict("os.environ", {"GLEAN_CLIENT_TOKEN": "real_tok"}):
            s = _sess(instance="acme-be.glean.com", api_token="token.secure.client", mode="mock")
            out = _output(cmd_doctor, s, [], {})
        self.assertIn("OK", out)

    def test_secure_ref_token_missing_env_shows_fail(self):
        clean_env = {k: v for k, v in os.environ.items() if k != "GLEAN_CLIENT_TOKEN"}
        with patch("glean_code.ui.supports_colour", return_value=False), \
             patch.dict("os.environ", clean_env, clear=True):
            s = _sess(instance="acme-be.glean.com", api_token="token.secure.client", mode="mock")
            out = _output(cmd_doctor, s, [], {})
        self.assertIn("FAIL", out)


# ---------------------------------------------------------------------------
# ui.hyperlink
# ---------------------------------------------------------------------------

class TestHyperlink(unittest.TestCase):
    def test_colour_enabled_returns_osc8_format(self):
        with patch("glean_code.ui.supports_colour", return_value=True):
            result = ui.hyperlink("https://example.com", "Click here")
        self.assertIn("\033]8;;", result)
        self.assertIn("https://example.com", result)
        self.assertIn("Click here", result)

    def test_colour_disabled_returns_plain_text_only(self):
        with patch("glean_code.ui.supports_colour", return_value=False):
            result = ui.hyperlink("https://example.com", "Click here")
        self.assertEqual(result, "Click here")

    def test_osc8_contains_closing_sequence(self):
        with patch("glean_code.ui.supports_colour", return_value=True):
            result = ui.hyperlink("https://example.com", "text")
        # Closing sequence is ESC ] 8 ; ; ESC backslash
        self.assertIn("\033]8;;\033\\", result)


# ---------------------------------------------------------------------------
# ui.render_banner
# ---------------------------------------------------------------------------

class TestRenderBanner(unittest.TestCase):
    def test_contains_version(self):
        with patch("glean_code.ui.supports_colour", return_value=False):
            result = ui.render_banner("1.2.3", "mock")
        self.assertIn("1.2.3", result)

    def test_contains_mode(self):
        with patch("glean_code.ui.supports_colour", return_value=False):
            result = ui.render_banner("0.1", "live")
        self.assertIn("live", result)

    def test_returns_nonempty_string(self):
        with patch("glean_code.ui.supports_colour", return_value=False):
            result = ui.render_banner("0.0.1", "mock")
        self.assertTrue(result.strip())

    def test_contains_block_char_from_wordmark(self):
        with patch("glean_code.ui.supports_colour", return_value=False):
            result = ui.render_banner("0.0.1", "mock")
        # GLEAN_WORDMARK contains \u2588 (full block) characters
        self.assertIn("\u2588", result)

    def test_contains_help_hint(self):
        with patch("glean_code.ui.supports_colour", return_value=False):
            result = ui.render_banner("0.0.1", "mock")
        self.assertIn("help", result.lower())


if __name__ == "__main__":
    unittest.main()
