"""Tests for the GitHub Pages site builder (.github/pages/build.py).

The builder lives outside the package (it is release tooling, not part of the
REPL), so it is loaded from its path. Like the rest of the suite these tests
touch no network and write only into a temp directory.
"""

import importlib.util
import pathlib
import sys
import tempfile
import unittest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
BUILD_PY = REPO_ROOT / ".github" / "pages" / "build.py"


def _load_builder():
    spec = importlib.util.spec_from_file_location("pages_build", BUILD_PY)
    module = importlib.util.module_from_spec(spec)
    sys.modules["pages_build"] = module
    spec.loader.exec_module(module)
    return module


build = _load_builder()


class TestInline(unittest.TestCase):
    def test_relative_md_link_points_at_github(self):
        self.assertEqual(
            build.resolve_href("docs/INSTALL.md"),
            "https://github.com/barkz/glean-code-cli/blob/main/docs/INSTALL.md",
        )

    def test_leading_dot_slash_is_stripped(self):
        self.assertEqual(
            build.resolve_href("./LICENSE"),
            "https://github.com/barkz/glean-code-cli/blob/main/LICENSE",
        )

    def test_absolute_and_anchor_hrefs_are_untouched(self):
        for href in ("https://example.com/x", "#documentation", "mailto:a@b.c"):
            self.assertEqual(build.resolve_href(href), href)

    def test_link_bold_and_code(self):
        out = build.inline("see **the** [docs](docs/COMMANDS.md) for `/search`")
        self.assertIn("<strong>the</strong>", out)
        self.assertIn('href="https://github.com/barkz/glean-code-cli/blob/main/docs/COMMANDS.md"', out)
        self.assertIn("<code>/search</code>", out)

    def test_image_src_stays_relative(self):
        out = build.inline("![shot](assets/glean_code_cli_example.png)")
        self.assertIn('src="assets/glean_code_cli_example.png"', out)
        self.assertIn('alt="shot"', out)

    def test_markdown_inside_a_code_span_is_not_converted(self):
        out = build.inline("`**not bold** [not a link](x.md)`")
        self.assertNotIn("<strong>", out)
        self.assertNotIn("<a ", out)

    def test_angle_brackets_in_code_span_are_escaped(self):
        self.assertIn("&lt;agent-id&gt;", build.inline("`<agent-id>`"))


class TestSlug(unittest.TestCase):
    def test_plain_heading(self):
        self.assertEqual(build.slug("Why Glean Code"), "why-glean-code")

    def test_emoji_and_punctuation_are_dropped(self):
        self.assertEqual(build.slug("🔎 Search &amp; chat"), "search-amp-chat")

    def test_code_and_bold_markers_are_dropped(self):
        self.assertEqual(build.slug("**`/flow`** mapper"), "flow-mapper")


class TestBlocks(unittest.TestCase):
    def test_heading_gets_an_anchor_id(self):
        self.assertIn('<h2 id="quickstart">', build.render("## Quickstart"))

    def test_fenced_code_is_escaped_and_tagged(self):
        out = build.render("```bash\necho '<a>' && x\n```")
        self.assertIn('<pre><code class="language-bash">', out)
        self.assertIn("'&lt;a&gt;' &amp;&amp; x", out)

    def test_fenced_code_keeps_markdown_literal(self):
        out = build.render("```text\n**stars** and [brackets](x.md)\n```")
        self.assertIn("**stars**", out)
        self.assertNotIn("<strong>", out)

    def test_table_with_empty_header_drops_the_thead(self):
        out = build.render("|  |  |\n| --- | --- |\n| a | b |")
        self.assertNotIn("<thead>", out)
        self.assertIn("<td>a</td><td>b</td>", out)

    def test_table_with_a_real_header_keeps_it(self):
        out = build.render("| Flag | Effect |\n| --- | --- |\n| `--dev` | live |")
        self.assertIn("<thead><tr><th>Flag</th><th>Effect</th></tr></thead>", out)
        self.assertIn("<code>--dev</code>", out)

    def test_divider_detection(self):
        self.assertTrue(build.is_table_divider(["---", ":---:"]))
        self.assertFalse(build.is_table_divider(["Flag", "Effect"]))

    def test_note_alert(self):
        out = build.render("> [!NOTE]\n> Careful **here**.")
        self.assertIn('class="alert alert-note"', out)
        self.assertIn("<strong>here</strong>", out)

    def test_raw_html_passes_through_untouched(self):
        out = build.render('<div align="center">\n\n# Glean Code\n\n</div>')
        self.assertIn('<div align="center">', out)
        self.assertIn('<h1 id="glean-code">Glean Code</h1>', out)
        self.assertIn("</div>", out)

    def test_horizontal_rule(self):
        self.assertIn("<hr>", build.render("---"))

    def test_paragraph_of_only_images_is_flagged(self):
        out = build.render("![a](x.png)\n![b](y.png)")
        self.assertIn('<p class="imgrow">', out)

    def test_paragraph_with_text_is_not_flagged(self):
        out = build.render("![a](x.png) and words")
        self.assertNotIn("imgrow", out)

    def test_consecutive_lines_join_into_one_paragraph(self):
        out = build.render("one\ntwo")
        self.assertEqual(out.count("<p>"), 1)
        self.assertIn("one two", out)


class TestBuild(unittest.TestCase):
    def test_title_comes_from_the_first_h1(self):
        self.assertEqual(build.page_title("intro\n\n# Glean Code\n"), "Glean Code")

    def test_title_falls_back(self):
        self.assertEqual(build.page_title("no heading here"), "Glean Code")

    def test_build_writes_a_site(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = build.build(out_dir=pathlib.Path(tmp) / "_site")
            index = out / "index.html"
            self.assertTrue(index.is_file())
            self.assertTrue((out / ".nojekyll").is_file())
            self.assertTrue((out / "assets" / "glean_code_cli_example.png").is_file())

            page = index.read_text(encoding="utf-8")
            self.assertIn("<title>Glean Code</title>", page)
            self.assertNotIn("{{CONTENT}}", page)
            self.assertNotIn("{{TITLE}}", page)
            self.assertNotIn("{{REPO_URL}}", page)
            # the real README's own content made it through
            self.assertIn('<h2 id="why-glean-code">', page)
            self.assertIn('<h2 id="documentation">', page)

    def test_build_replaces_a_previous_output_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = pathlib.Path(tmp) / "_site"
            out_dir.mkdir()
            stale = out_dir / "stale.html"
            stale.write_text("old", encoding="utf-8")
            build.build(out_dir=out_dir)
            self.assertFalse(stale.exists())

    def test_no_unresolved_repo_relative_links_remain(self):
        with tempfile.TemporaryDirectory() as tmp:
            page = (build.build(out_dir=pathlib.Path(tmp) / "_site") / "index.html").read_text()
            self.assertNotIn('href="docs/', page)
            self.assertNotIn('href="LICENSE"', page)


if __name__ == "__main__":
    unittest.main()
