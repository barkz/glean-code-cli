"""Tests for glean_code.help_docs -- structure validation."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from glean_code.help_docs import DOCS, COMMAND_GROUPS
from glean_code.commands import HANDLERS


_REQUIRED_KEYS = {"summary", "usage", "params", "examples", "endpoint"}


class TestDocsStructure(unittest.TestCase):
    """Every entry in DOCS must have the required shape."""

    def test_docs_is_not_empty(self):
        self.assertGreater(len(DOCS), 0)

    def test_all_commands_have_required_keys(self):
        for cmd, doc in DOCS.items():
            with self.subTest(cmd=cmd):
                missing = _REQUIRED_KEYS - set(doc.keys())
                self.assertEqual(missing, set(), f"{cmd} missing keys: {missing}")

    def test_summary_is_nonempty_string(self):
        for cmd, doc in DOCS.items():
            with self.subTest(cmd=cmd):
                self.assertIsInstance(doc["summary"], str)
                self.assertTrue(doc["summary"].strip(), f"{cmd}.summary is blank")

    def test_usage_is_nonempty_string(self):
        for cmd, doc in DOCS.items():
            with self.subTest(cmd=cmd):
                self.assertIsInstance(doc["usage"], str)
                self.assertTrue(doc["usage"].strip(), f"{cmd}.usage is blank")

    def test_endpoint_is_nonempty_string(self):
        for cmd, doc in DOCS.items():
            with self.subTest(cmd=cmd):
                self.assertIsInstance(doc["endpoint"], str)
                self.assertTrue(doc["endpoint"].strip(), f"{cmd}.endpoint is blank")

    def test_params_is_a_list(self):
        for cmd, doc in DOCS.items():
            with self.subTest(cmd=cmd):
                self.assertIsInstance(doc["params"], list)

    def test_each_param_has_name_and_description(self):
        for cmd, doc in DOCS.items():
            for i, param in enumerate(doc["params"]):
                with self.subTest(cmd=cmd, param_index=i):
                    self.assertGreaterEqual(
                        len(param), 2,
                        f"{cmd}.params[{i}] needs at least (name, description)"
                    )
                    self.assertIsInstance(param[0], str)

    def test_examples_is_a_list(self):
        for cmd, doc in DOCS.items():
            with self.subTest(cmd=cmd):
                self.assertIsInstance(doc["examples"], list)

    def test_each_example_is_a_string(self):
        for cmd, doc in DOCS.items():
            for i, ex in enumerate(doc["examples"]):
                with self.subTest(cmd=cmd, example_index=i):
                    self.assertIsInstance(ex, str)

    def test_all_docs_keys_are_strings(self):
        for key in DOCS.keys():
            self.assertIsInstance(key, str)


class TestCommandGroups(unittest.TestCase):
    """COMMAND_GROUPS must reference only commands that exist in DOCS."""

    def test_command_groups_is_not_empty(self):
        self.assertGreater(len(COMMAND_GROUPS), 0)

    def test_every_group_has_a_name_and_list(self):
        for entry in COMMAND_GROUPS:
            self.assertEqual(len(entry), 2)
            name, cmds = entry
            self.assertIsInstance(name, str)
            self.assertIsInstance(cmds, list)

    def test_all_group_commands_exist_in_docs(self):
        for group_name, cmds in COMMAND_GROUPS:
            for cmd in cmds:
                with self.subTest(group=group_name, cmd=cmd):
                    self.assertIn(
                        cmd, DOCS,
                        f"COMMAND_GROUPS['{group_name}'] references '{cmd}' "
                        f"which is not in DOCS"
                    )

    def test_group_names_are_nonempty(self):
        for group_name, _ in COMMAND_GROUPS:
            self.assertTrue(group_name.strip(), "Group name is blank")


class TestHandlerAndDocsCoverage(unittest.TestCase):
    """Every registered handler should have a DOCS entry and vice versa."""

    def test_every_handler_has_a_doc(self):
        for cmd in HANDLERS:
            if cmd in _UNDOCUMENTED_ALIASES:
                continue
            with self.subTest(cmd=cmd):
                self.assertIn(
                    cmd, DOCS,
                    f"Handler '{cmd}' has no DOCS entry"
                )

    def test_every_doc_has_a_handler(self):
        for cmd in DOCS:
            with self.subTest(cmd=cmd):
                self.assertIn(
                    cmd, HANDLERS,
                    f"DOCS entry '{cmd}' has no registered handler"
                )


if __name__ == "__main__":
    unittest.main()

# 'quit' is a registered alias for 'exit' — intentionally undocumented
_UNDOCUMENTED_ALIASES = {"quit"}
