"""Tests for glean_code.config"""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from glean_code.config import Config


class TestConfigDefaults(unittest.TestCase):
    def test_default_values(self):
        c = Config()
        self.assertIsNone(c.instance)
        self.assertIsNone(c.api_token)
        self.assertIsNone(c.indexing_token)
        self.assertIsNone(c.act_as)
        self.assertIsNone(c.base_url)
        self.assertEqual(c.mode, "auto")
        self.assertEqual(c.theme, "glean")
        self.assertEqual(c.default_page_size, 10)
        self.assertEqual(c.history, [])

    def test_to_dict_includes_all_fields(self):
        c = Config(instance="test.glean.com", api_token="tok123")
        d = c.to_dict()
        self.assertEqual(d["instance"], "test.glean.com")
        self.assertEqual(d["api_token"], "tok123")
        self.assertIn("mode", d)
        self.assertIn("theme", d)
        self.assertIn("default_page_size", d)

    def test_history_default_is_empty_list_not_shared(self):
        a, b = Config(), Config()
        a.history.append("cmd")
        self.assertEqual(b.history, [])


class TestConfigLoad(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.config_path = Path(self.tmpdir.name) / "config.json"

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_load_returns_defaults_when_no_file(self):
        with patch("glean_code.config.CONFIG_PATH", self.config_path):
            c = Config.load()
        self.assertIsNone(c.instance)
        self.assertEqual(c.mode, "auto")

    def test_load_reads_saved_values(self):
        data = {"instance": "acme-be.glean.com", "api_token": "secret", "mode": "live"}
        self.config_path.write_text(json.dumps(data))
        with patch("glean_code.config.CONFIG_PATH", self.config_path):
            c = Config.load()
        self.assertEqual(c.instance, "acme-be.glean.com")
        self.assertEqual(c.api_token, "secret")
        self.assertEqual(c.mode, "live")

    def test_load_ignores_unknown_keys(self):
        data = {"instance": "test.glean.com", "future_unknown_key": "value"}
        self.config_path.write_text(json.dumps(data))
        with patch("glean_code.config.CONFIG_PATH", self.config_path):
            c = Config.load()
        self.assertEqual(c.instance, "test.glean.com")
        self.assertFalse(hasattr(c, "future_unknown_key"))

    def test_load_returns_defaults_on_corrupt_json(self):
        self.config_path.write_text("not json {{{{")
        with patch("glean_code.config.CONFIG_PATH", self.config_path):
            c = Config.load()
        self.assertIsNone(c.instance)

    def test_load_returns_defaults_on_empty_file(self):
        self.config_path.write_text("")
        with patch("glean_code.config.CONFIG_PATH", self.config_path):
            c = Config.load()
        self.assertIsNone(c.instance)


class TestConfigSave(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.config_dir = Path(self.tmpdir.name)
        self.config_path = self.config_dir / "config.json"

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_save_creates_file(self):
        with patch("glean_code.config.CONFIG_DIR", self.config_dir), \
             patch("glean_code.config.CONFIG_PATH", self.config_path):
            Config(instance="save-test.glean.com").save()
        self.assertTrue(self.config_path.exists())

    def test_save_writes_correct_values(self):
        with patch("glean_code.config.CONFIG_DIR", self.config_dir), \
             patch("glean_code.config.CONFIG_PATH", self.config_path):
            Config(instance="acme.glean.com", mode="mock").save()
        data = json.loads(self.config_path.read_text())
        self.assertEqual(data["instance"], "acme.glean.com")
        self.assertEqual(data["mode"], "mock")

    def test_save_creates_nested_directory(self):
        nested_dir = self.config_dir / "nested" / "deep"
        nested_path = nested_dir / "config.json"
        with patch("glean_code.config.CONFIG_DIR", nested_dir), \
             patch("glean_code.config.CONFIG_PATH", nested_path):
            Config(api_token="tok").save()
        self.assertTrue(nested_path.exists())

    def test_save_sets_restrictive_permissions(self):
        with patch("glean_code.config.CONFIG_DIR", self.config_dir), \
             patch("glean_code.config.CONFIG_PATH", self.config_path):
            Config(api_token="tok").save()
        mode = oct(os.stat(self.config_path).st_mode)[-3:]
        self.assertEqual(mode, "600")

    def test_roundtrip(self):
        c = Config(instance="rt.glean.com", api_token="abc", mode="mock", default_page_size=5)
        with patch("glean_code.config.CONFIG_DIR", self.config_dir), \
             patch("glean_code.config.CONFIG_PATH", self.config_path):
            c.save()
            loaded = Config.load()
        self.assertEqual(loaded.instance, "rt.glean.com")
        self.assertEqual(loaded.api_token, "abc")
        self.assertEqual(loaded.mode, "mock")
        self.assertEqual(loaded.default_page_size, 5)


class TestConfigEffectiveBaseUrl(unittest.TestCase):
    def test_uses_base_url_when_set(self):
        c = Config(base_url="https://custom.example.com/api")
        self.assertEqual(c.effective_base_url, "https://custom.example.com/api")

    def test_strips_trailing_slash_from_base_url(self):
        c = Config(base_url="https://custom.example.com/api/")
        self.assertEqual(c.effective_base_url, "https://custom.example.com/api")

    def test_computes_from_bare_host(self):
        c = Config(instance="acme-be.glean.com")
        self.assertEqual(c.effective_base_url, "https://acme-be.glean.com/rest/api/v1")

    def test_computes_from_https_url(self):
        c = Config(instance="https://acme-be.glean.com")
        self.assertEqual(c.effective_base_url, "https://acme-be.glean.com/rest/api/v1")

    def test_strips_path_from_instance(self):
        c = Config(instance="acme-be.glean.com/some/path")
        self.assertEqual(c.effective_base_url, "https://acme-be.glean.com/rest/api/v1")

    def test_returns_none_with_no_instance_or_base_url(self):
        self.assertIsNone(Config().effective_base_url)

    def test_base_url_takes_priority_over_instance(self):
        c = Config(instance="acme-be.glean.com", base_url="https://override.example.com/api")
        self.assertEqual(c.effective_base_url, "https://override.example.com/api")


class TestConfigEffectiveIndexingBaseUrl(unittest.TestCase):
    def test_computes_from_bare_instance(self):
        c = Config(instance="acme-be.glean.com")
        self.assertEqual(c.effective_indexing_base_url, "https://acme-be.glean.com/api/index/v1")

    def test_strips_https_prefix(self):
        c = Config(instance="https://acme-be.glean.com")
        self.assertEqual(c.effective_indexing_base_url, "https://acme-be.glean.com/api/index/v1")

    def test_returns_none_without_instance(self):
        self.assertIsNone(Config().effective_indexing_base_url)


class TestConfigIsLiveReady(unittest.TestCase):
    def test_ready_with_token_and_instance(self):
        c = Config(instance="acme-be.glean.com", api_token="tok")
        self.assertTrue(c.is_live_ready)

    def test_not_ready_without_token(self):
        self.assertFalse(Config(instance="acme-be.glean.com").is_live_ready)

    def test_not_ready_without_instance(self):
        self.assertFalse(Config(api_token="tok").is_live_ready)

    def test_not_ready_with_nothing(self):
        self.assertFalse(Config().is_live_ready)

    def test_ready_with_explicit_base_url_and_token(self):
        c = Config(base_url="https://custom.example.com/api", api_token="tok")
        self.assertTrue(c.is_live_ready)


class TestConfigEffectiveMode(unittest.TestCase):
    def test_explicit_live_stays_live(self):
        self.assertEqual(Config(mode="live").effective_mode, "live")

    def test_explicit_mock_stays_mock(self):
        self.assertEqual(Config(mode="mock").effective_mode, "mock")

    def test_auto_resolves_live_when_credentials_set(self):
        c = Config(instance="acme-be.glean.com", api_token="tok", mode="auto")
        self.assertEqual(c.effective_mode, "live")

    def test_auto_resolves_mock_without_credentials(self):
        self.assertEqual(Config(mode="auto").effective_mode, "mock")

    def test_auto_resolves_mock_missing_token(self):
        c = Config(instance="acme-be.glean.com", mode="auto")
        self.assertEqual(c.effective_mode, "mock")

    def test_auto_resolves_mock_missing_instance(self):
        c = Config(api_token="tok", mode="auto")
        self.assertEqual(c.effective_mode, "mock")


if __name__ == "__main__":
    unittest.main()
