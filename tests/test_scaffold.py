"""Tests for glean_code.scaffold"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from glean_code.scaffold import TEMPLATES, write_scaffold, default_dir


class TestTemplates(unittest.TestCase):
    def test_all_three_templates_exist(self):
        self.assertIn("chat", TEMPLATES)
        self.assertIn("search", TEMPLATES)
        self.assertIn("agent", TEMPLATES)

    def test_chat_template_is_valid_python_syntax(self):
        compile(TEMPLATES["chat"], "<chat>", "exec")

    def test_search_template_is_valid_python_syntax(self):
        compile(TEMPLATES["search"], "<search>", "exec")

    def test_agent_template_is_valid_python_syntax(self):
        compile(TEMPLATES["agent"], "<agent>", "exec")

    def test_templates_import_only_stdlib(self):
        for name, code in TEMPLATES.items():
            # No third-party imports
            self.assertNotIn("import anthropic", code)
            self.assertNotIn("import requests", code)
            self.assertNotIn("import httpx", code)

    def test_templates_load_glean_config(self):
        for name, code in TEMPLATES.items():
            self.assertIn(".gleancode", code, f"Template {name} should reference config dir")

    def test_templates_support_env_vars(self):
        for name, code in TEMPLATES.items():
            self.assertIn("GLEAN_INSTANCE", code)
            self.assertIn("GLEAN_TOKEN", code)

    def test_chat_template_has_main_function(self):
        self.assertIn("def main()", TEMPLATES["chat"])

    def test_search_template_has_search_function(self):
        self.assertIn("def search(", TEMPLATES["search"])

    def test_agent_template_has_list_and_run(self):
        self.assertIn("def list_agents(", TEMPLATES["agent"])
        self.assertIn("def run_agent(", TEMPLATES["agent"])


class TestDefaultDir(unittest.TestCase):
    def test_chat_default_dir(self):
        self.assertEqual(default_dir("chat"), "./glean-chat")

    def test_search_default_dir(self):
        self.assertEqual(default_dir("search"), "./glean-search")

    def test_agent_default_dir(self):
        self.assertEqual(default_dir("agent"), "./glean-agent")


class TestWriteScaffold(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_chat_creates_file(self):
        path = write_scaffold("chat", self.tmpdir.name)
        self.assertTrue(Path(path).exists())
        self.assertTrue(path.endswith("glean_chat.py"))

    def test_search_creates_file(self):
        path = write_scaffold("search", self.tmpdir.name)
        self.assertTrue(Path(path).exists())
        self.assertTrue(path.endswith("glean_search.py"))

    def test_agent_creates_file(self):
        path = write_scaffold("agent", self.tmpdir.name)
        self.assertTrue(Path(path).exists())
        self.assertTrue(path.endswith("glean_agent.py"))

    def test_file_content_matches_template(self):
        path = write_scaffold("search", self.tmpdir.name)
        content = Path(path).read_text(encoding="utf-8")
        self.assertEqual(content, TEMPLATES["search"])

    def test_creates_output_directory_if_missing(self):
        nested = str(Path(self.tmpdir.name) / "new" / "nested")
        path = write_scaffold("chat", nested)
        self.assertTrue(Path(path).exists())

    def test_file_is_executable(self):
        import os
        import stat
        path = write_scaffold("chat", self.tmpdir.name)
        mode = os.stat(path).st_mode
        # Should have at least owner execute bit
        self.assertTrue(mode & stat.S_IXUSR)

    def test_returns_absolute_path(self):
        path = write_scaffold("agent", self.tmpdir.name)
        self.assertTrue(Path(path).is_absolute())

    def test_all_templates_written_correctly(self):
        for template_name in ("chat", "search", "agent"):
            path = write_scaffold(template_name, self.tmpdir.name)
            content = Path(path).read_text(encoding="utf-8")
            self.assertEqual(content, TEMPLATES[template_name])


if __name__ == "__main__":
    unittest.main()
