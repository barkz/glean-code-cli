"""Every REST path in client.py must exist in Glean's published OpenAPI spec.

This is the guard the August 2026 audit recommended. Twelve Client API calls had
drifted from the spec — wrong paths, a POST where the spec says GET, misnamed
body fields — and nothing caught them, because the mock dispatcher is keyed on
the same path strings the live client posts to. A wrong path was wrong
consistently, so the suite passed while the calls would 404 against a tenant.

The check is structural: it reads client.py with `ast` and compares every
endpoint it calls against tests/spec_manifest.json, which is generated from the
published specs by tools/refresh_spec_manifest.py. No network access, per the
project's rule that tests make no network calls.

It deliberately does NOT require the client to cover every documented endpoint —
plenty are intentionally unimplemented. It only asserts that what the client
does call, exists.
"""
import ast
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

REPO = Path(__file__).resolve().parent.parent
CLIENT_PY = REPO / "glean_code" / "client.py"
MANIFEST = Path(__file__).resolve().parent / "spec_manifest.json"

# How each helper maps onto a surface in the manifest.
POST_HELPERS = {"_post": "client", "_indexing_post": "indexing"}
BASE_TO_SURFACE = {
    "effective_indexing_base_url": "indexing",
    "effective_metadata_base_url": "metadata",
    "effective_base_url": "client",
}


def _literal_path(node):
    """Render a path argument as the manifest spells it, or None.

    Handles plain strings and f-strings; an f-string's substitutions become {}
    so that f"/debug/{datasource}/status" matches /debug/{}/status.
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        out = []
        for part in node.values:
            if isinstance(part, ast.Constant) and isinstance(part.value, str):
                out.append(part.value)
            else:
                out.append("{}")
        return "".join(out)
    return None


def _kwarg(call, name):
    for kw in call.keywords:
        if kw.arg == name:
            return _literal_path(kw.value) or (
                kw.value.value if isinstance(kw.value, ast.Constant) else None
            )
    return None


def collect_calls():
    """Return {(surface, path, method)} for every endpoint client.py calls."""
    tree = ast.parse(CLIENT_PY.read_text(encoding="utf-8"))
    found = set()

    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        # Paths appearing anywhere in this function, for the case where the
        # call site passes a variable (agent_run picks wait vs stream).
        local_paths = [
            s.value for s in ast.walk(fn)
            if isinstance(s, ast.Constant) and isinstance(s.value, str)
            and s.value.startswith("/") and " " not in s.value
        ]

        for call in ast.walk(fn):
            if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Attribute):
                continue
            helper = call.func.attr

            if helper in POST_HELPERS:
                surface = POST_HELPERS[helper]
                if not call.args:
                    continue
                method = _kwarg(call, "method") or "POST"
                path = _literal_path(call.args[0])
                if path:
                    found.add((surface, path, method))
                elif isinstance(call.args[0], ast.Name):
                    # Variable path: attribute every literal in the function.
                    for p in local_paths:
                        found.add((surface, p, method))

            elif helper == "_indexing_request":
                # _indexing_request(method, base, path, body=...)
                if len(call.args) < 3:
                    continue
                method = _literal_path(call.args[0]) or "POST"
                base = call.args[1]
                surface = "indexing"
                if isinstance(base, ast.Attribute):
                    surface = BASE_TO_SURFACE.get(base.attr, "indexing")
                path = _literal_path(call.args[2])
                if path:
                    found.add((surface, path, method))

    return found


class TestSpecManifest(unittest.TestCase):
    def test_manifest_exists_and_is_populated(self):
        self.assertTrue(MANIFEST.exists(),
                        "run tools/refresh_spec_manifest.py to generate it")
        data = json.loads(MANIFEST.read_text())
        self.assertIn("surfaces", data)
        for surface in ("client", "indexing", "metadata"):
            self.assertGreater(len(data["surfaces"].get(surface, {})), 0,
                               f"{surface} surface is empty")

    def test_manifest_records_the_spec_version_it_came_from(self):
        data = json.loads(MANIFEST.read_text())
        self.assertRegex(data.get("spec_version", ""), r"^\d+\.\d+")
        self.assertRegex(data.get("spec_commit", ""), r"^[0-9a-f]{7,40}$")


class TestClientConformsToSpec(unittest.TestCase):
    """The regression guard itself."""

    @classmethod
    def setUpClass(cls):
        data = json.loads(MANIFEST.read_text())
        cls.surfaces = data["surfaces"]
        cls.undocumented = data.get("undocumented", {})
        cls.calls = collect_calls()

    def _is_undocumented(self, surface, path):
        return path in self.undocumented.get(surface, [])

    def test_extractor_found_the_calls(self):
        # A silent extraction failure would make every other test here vacuous.
        self.assertGreater(len(self.calls), 60,
                           "the AST extractor found suspiciously few calls")

    def test_every_path_exists_in_the_spec(self):
        """A path absent from the spec entirely is a hard failure.

        A path the spec declares but leaves undocumented is tracked separately
        (see test_undocumented_paths_are_still_undocumented) because the
        endpoint does exist in the document — Glean has simply stopped
        describing its operation.
        """
        missing = sorted(
            f"{surface}: {method} {path}"
            for surface, path, method in self.calls
            if path not in self.surfaces.get(surface, {})
            and not self._is_undocumented(surface, path)
        )
        self.assertEqual(missing, [], "paths not present in the published spec:\n  "
                                      + "\n  ".join(missing))

    def test_undocumented_paths_are_still_undocumented(self):
        """Self-cleaning exception list.

        The client calls /indexemployeelist, which the spec declares with no
        operation. If Glean documents it again this test fails, which is the
        signal to drop the exception and let the normal check cover it.
        """
        called = {(s, p) for s, p, _ in self.calls}
        for surface, paths in self.undocumented.items():
            for path in paths:
                if (surface, path) in called:
                    self.assertNotIn(
                        path, self.surfaces.get(surface, {}),
                        f"{surface}:{path} is now documented — remove the exception",
                    )

    def test_the_exception_list_stays_small(self):
        """Undocumented endpoints are a risk, not a pattern to grow."""
        exercised = [
            (s, p) for s, ps in self.undocumented.items() for p in ps
            if (s, p) in {(a, b) for a, b, _ in self.calls}
        ]
        self.assertLessEqual(
            len(exercised), 2,
            f"the client leans on too many undocumented endpoints: {exercised}",
        )

    def test_every_method_is_allowed_for_its_path(self):
        wrong = []
        for surface, path, method in sorted(self.calls):
            allowed = self.surfaces.get(surface, {}).get(path)
            if allowed and method not in allowed:
                wrong.append(f"{surface}: {method} {path} (spec allows {','.join(allowed)})")
        self.assertEqual(wrong, [], "methods the spec does not allow:\n  "
                                    + "\n  ".join(wrong))

    def test_the_three_surfaces_are_all_exercised(self):
        used = {surface for surface, _, _ in self.calls}
        self.assertEqual(used, {"client", "indexing", "metadata"})


if __name__ == "__main__":
    unittest.main()
