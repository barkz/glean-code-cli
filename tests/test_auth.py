"""Unit + local-integration tests for the OAuth (SSO) auth flow.

Standard library only (unittest + unittest.mock). No network calls: the OAuth
endpoints and the localhost callback are mocked.

Run:  python3 -m pytest tests/test_auth.py
  or: python3 -m unittest tests.test_auth
"""
from __future__ import annotations

import time
import unittest
from unittest import mock

from glean_code.auth import pkce
from glean_code.auth import token_store
from glean_code.auth import oauth
from glean_code.auth.manager import AuthManager, AuthError
from glean_code.config import Config


class TestPkce(unittest.TestCase):
    def test_verifier_and_challenge(self):
        pair = pkce.create_pkce_pair()
        self.assertTrue(43 <= len(pair.code_verifier) <= 128)
        self.assertEqual(pair.method, "S256")
        # Challenge is base64url with no padding.
        self.assertNotIn("=", pair.code_challenge)
        self.assertNotIn("+", pair.code_challenge)
        self.assertNotIn("/", pair.code_challenge)

    def test_pairs_are_unique(self):
        self.assertNotEqual(
            pkce.create_pkce_pair().code_verifier,
            pkce.create_pkce_pair().code_verifier,
        )

    def test_state_unique(self):
        self.assertNotEqual(pkce.generate_state(), pkce.generate_state())


class TestExpiry(unittest.TestCase):
    def test_no_expiry_is_not_expired(self):
        self.assertFalse(token_store.is_expired(None))

    def test_future_is_not_expired(self):
        self.assertFalse(token_store.is_expired(time.time() + 600))

    def test_past_is_expired(self):
        self.assertTrue(token_store.is_expired(time.time() - 10))

    def test_within_skew_is_expired(self):
        # 30s in the future but skew is 60s -> treated as expired.
        self.assertTrue(token_store.is_expired(time.time() + 30))


class TestTokensFromResponse(unittest.TestCase):
    def test_expires_in_becomes_absolute(self):
        before = time.time()
        toks = token_store.tokens_from_response(
            {"access_token": "a", "refresh_token": "r", "expires_in": 3600,
             "token_type": "Bearer", "scope": "SEARCH"}
        )
        self.assertEqual(toks.access_token, "a")
        self.assertEqual(toks.refresh_token, "r")
        self.assertGreaterEqual(toks.expires_at, before + 3599)

    def test_refresh_response_keeps_prior_refresh_token(self):
        toks = token_store.tokens_from_response(
            {"access_token": "new", "expires_in": 100}, prior_refresh_token="keepme"
        )
        self.assertEqual(toks.refresh_token, "keepme")


class TestTokenStoreRoundTrip(unittest.TestCase):
    def setUp(self):
        # Redirect the store to a temp path.
        import tempfile, pathlib
        self.tmp = tempfile.mkdtemp()
        self._patch = mock.patch.object(
            token_store, "AUTH_PATH", pathlib.Path(self.tmp) / "auth.json"
        )
        self._patch.start()
        mock.patch.object(token_store, "AUTH_DIR", pathlib.Path(self.tmp)).start()

    def tearDown(self):
        mock.patch.stopall()

    def test_save_load_clear(self):
        self.assertIsNone(token_store.load_tokens())
        toks = token_store.Tokens(access_token="abc", refresh_token="r",
                                   expires_at=time.time() + 100)
        token_store.save_tokens(toks)
        loaded = token_store.load_tokens()
        self.assertEqual(loaded.access_token, "abc")
        token_store.clear_tokens()
        self.assertIsNone(token_store.load_tokens())


class TestDynamicClientRegistration(unittest.TestCase):
    def test_registers_public_pkce_client(self):
        with mock.patch.object(
            oauth, "_http_post_json", return_value={"client_id": "dcr-client"}
        ) as post:
            client_id = oauth.register_dynamic_client(
                "https://acme-be.glean.com/register",
                "http://127.0.0.1:33389/callback",
                "SEARCH CHAT",
            )

        self.assertEqual(client_id, "dcr-client")
        payload = post.call_args.args[1]
        self.assertEqual(payload["client_name"], "Glean Code CLI")
        self.assertEqual(payload["redirect_uris"], ["http://127.0.0.1:33389/callback"])
        self.assertEqual(payload["token_endpoint_auth_method"], "none")
        self.assertEqual(payload["grant_types"], ["authorization_code", "refresh_token"])


class TestAuthorizeUrl(unittest.TestCase):
    def test_required_params_present(self):
        url = oauth.build_authorize_url(
            authorization_endpoint="https://acme-be.glean.com/authorize",
            client_id="cid",
            redirect_uri="http://127.0.0.1:33389/callback",
            code_challenge="chal",
            state="st",
            scopes="SEARCH CHAT",
        )
        for needle in ("response_type=code", "client_id=cid",
                       "code_challenge=chal", "code_challenge_method=S256",
                       "state=st"):
            self.assertIn(needle, url)


class _FakeCallback:
    def __init__(self, code, state):
        from glean_code.auth.callback_server import CallbackResult
        self._res = CallbackResult(code=code, state=state)
        self.redirect_uri = "http://127.0.0.1:33389/callback"

    def wait_for_code(self, timeout=300):
        return self._res

    def close(self):
        pass


class TestLoginIntegration(unittest.TestCase):
    def setUp(self):
        import tempfile, pathlib
        self.tmp = tempfile.mkdtemp()
        mock.patch.object(token_store, "AUTH_PATH", pathlib.Path(self.tmp) / "auth.json").start()
        mock.patch.object(token_store, "AUTH_DIR", pathlib.Path(self.tmp)).start()

    def tearDown(self):
        mock.patch.stopall()

    def test_login_stores_tokens(self):
        cfg = Config(instance="acme-be.glean.com", oauth_client_id="cid")
        # Pin state so the fake callback can echo it back (server starts before
        # build_authorize_url, so we cannot capture state from the URL builder).
        fixed_state = "fixed-state-123"

        with mock.patch.object(
            oauth, "discover_endpoints",
            return_value=oauth.Endpoints("https://a/authorize", "https://a/token", None)
        ), mock.patch("glean_code.auth.manager._pkce.generate_state",
                      return_value=fixed_state), \
             mock.patch("glean_code.auth.manager.webbrowser.open"), \
             mock.patch.object(oauth, "exchange_code_for_tokens",
                               return_value={"access_token": "AT", "refresh_token": "RT",
                                             "expires_in": 3600, "token_type": "Bearer"}), \
             mock.patch("glean_code.auth.manager.start_callback_server",
                        side_effect=lambda port: _FakeCallback("thecode", fixed_state)):
            status = AuthManager(cfg).login(open_browser=True)

        self.assertTrue(status.authenticated)
        loaded = token_store.load_tokens()
        self.assertEqual(loaded.access_token, "AT")
        self.assertEqual(loaded.refresh_token, "RT")

    def test_login_registers_client_with_dcr_when_no_client_id_is_configured(self):
        cfg = Config(instance="acme")
        fixed_state = "fixed-state-dcr"

        with mock.patch.object(
            oauth,
            "discover_endpoints",
            return_value=oauth.Endpoints(
                "https://a/authorize", "https://a/token", "https://a/register"
            ),
        ) as discover, mock.patch(
            "glean_code.auth.manager._pkce.generate_state", return_value=fixed_state
        ), mock.patch.object(
            oauth, "register_dynamic_client", return_value="dcr-client"
        ) as register, mock.patch.object(
            oauth,
            "exchange_code_for_tokens",
            return_value={"access_token": "AT", "expires_in": 3600},
        ), mock.patch(
            "glean_code.auth.manager.start_callback_server",
            side_effect=lambda port: _FakeCallback("thecode", fixed_state),
        ), mock.patch.object(cfg, "save"):
            status = AuthManager(cfg).login(open_browser=False)

        self.assertTrue(status.authenticated)
        discover.assert_called_once_with("https://acme-be.glean.com")
        register.assert_called_once_with(
            "https://a/register",
            "http://127.0.0.1:33389/callback",
            "SEARCH CHAT DOCUMENTS TOOLS ENTITIES offline_access",
        )
        self.assertEqual(cfg.oauth_client_id, "dcr-client")

    def test_state_mismatch_raises(self):
        cfg = Config(instance="acme-be.glean.com", oauth_client_id="cid")
        with mock.patch.object(
            oauth, "discover_endpoints",
            return_value=oauth.Endpoints("https://a/authorize", "https://a/token", None)
        ), mock.patch("glean_code.auth.manager.webbrowser.open"), \
             mock.patch("glean_code.auth.manager.start_callback_server",
                        side_effect=lambda port: _FakeCallback("code", "WRONG-STATE")):
            with self.assertRaises(AuthError):
                AuthManager(cfg).login(open_browser=True)

    def test_get_access_token_refreshes_when_expired(self):
        cfg = Config(instance="acme-be.glean.com", oauth_client_id="cid")
        token_store.save_tokens(token_store.Tokens(
            access_token="OLD", refresh_token="RT", expires_at=time.time() - 5))
        with mock.patch.object(
            oauth, "discover_endpoints",
            return_value=oauth.Endpoints("https://a/authorize", "https://a/token", None)
        ), mock.patch.object(oauth, "refresh_tokens",
                             return_value={"access_token": "NEW", "expires_in": 3600}):
            token = AuthManager(cfg).get_access_token()
        self.assertEqual(token, "NEW")
        self.assertEqual(token_store.load_tokens().access_token, "NEW")
        # Refresh token preserved across refresh.
        self.assertEqual(token_store.load_tokens().refresh_token, "RT")

    def test_logout_clears(self):
        cfg = Config(instance="acme-be.glean.com")
        token_store.save_tokens(token_store.Tokens(access_token="AT"))
        AuthManager(cfg).logout()
        self.assertIsNone(token_store.load_tokens())

    def test_not_logged_in_raises(self):
        cfg = Config(instance="acme-be.glean.com")
        with self.assertRaises(AuthError):
            AuthManager(cfg).get_access_token()


class TestConfigIntegration(unittest.TestCase):
    def setUp(self):
        import tempfile, pathlib
        self.tmp = tempfile.mkdtemp()
        mock.patch.object(token_store, "AUTH_PATH", pathlib.Path(self.tmp) / "auth.json").start()
        mock.patch.object(token_store, "AUTH_DIR", pathlib.Path(self.tmp)).start()

    def tearDown(self):
        mock.patch.stopall()

    def test_effective_api_token_prefers_oauth(self):
        cfg = Config(instance="acme-be.glean.com", api_token="legacy")
        token_store.save_tokens(token_store.Tokens(
            access_token="OAUTH", expires_at=time.time() + 600))
        self.assertEqual(cfg.effective_api_token, "OAUTH")
        self.assertTrue(cfg.is_live_ready)
        self.assertEqual(cfg.effective_mode, "live")

    def test_effective_api_token_falls_back_to_legacy(self):
        cfg = Config(instance="acme-be.glean.com", api_token="legacy")
        self.assertEqual(cfg.effective_api_token, "legacy")


if __name__ == "__main__":
    unittest.main()
