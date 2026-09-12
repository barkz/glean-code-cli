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
import xml.etree.ElementTree as ET

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
BUILD_PY = REPO_ROOT / ".github" / "pages" / "build.py"
BANNER_PY = REPO_ROOT / ".github" / "pages" / "make_banner.py"
BANNER_SVG = REPO_ROOT / "assets" / "glean-code-banner.svg"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


build = _load("pages_build", BUILD_PY)
make_banner = _load("pages_make_banner", BANNER_PY)


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

    def test_screenshot_paragraph_is_classified(self):
        out = build.render("words first\n\n![shot](assets/a.png)")
        self.assertIn('<p class="imgrow shot">', out)

    def test_badge_row_is_classified_even_when_it_leads_the_page(self):
        # A README that opens with shields must not get them styled as a header.
        out = build.render(
            "![a](https://img.shields.io/badge/a-b)\n![b](https://img.shields.io/badge/c-d)")
        self.assertIn('<p class="imgrow badges">', out)
        self.assertNotIn("banner", out)

    def test_diagram_paragraph_is_classified(self):
        out = build.render("words first\n\n![flow](assets/request-flow.svg)")
        self.assertIn('<p class="imgrow diagram">', out)

    def test_linked_badge_still_counts_as_a_badge_row(self):
        out = build.render("[![r](https://img.shields.io/badge/r-x)](https://example.com)")
        self.assertIn('<p class="imgrow badges">', out)

    def test_leading_image_is_the_page_header(self):
        out = build.render("![Glean Code](assets/glean-code-banner.svg)")
        self.assertIn('<p class="imgrow banner">', out)

    def test_an_image_after_prose_is_not_a_header(self):
        out = build.render("intro words\n\n![flow](assets/request-flow.svg)")
        self.assertIn('<p class="imgrow diagram">', out)
        self.assertNotIn("banner", out)

    def test_an_image_after_a_heading_is_not_a_header(self):
        out = build.render("## How it works\n\n![flow](assets/x.svg)")
        self.assertIn('<p class="imgrow diagram">', out)

    def test_paragraph_with_text_is_not_flagged(self):
        out = build.render("![a](x.png) and words")
        self.assertNotIn("imgrow", out)

    def test_bare_line_breaks_are_dropped(self):
        # The README uses them for spacing on github.com; the site sets its own.
        for spacer in ("<br>", "<br/>", "<br />", "<BR>"):
            out = build.render("text\n\n%s\n\nmore" % spacer)
            self.assertNotIn("<br", out, spacer)
            self.assertIn("<p>text</p>", out)
            self.assertIn("<p>more</p>", out)

    def test_a_real_html_block_is_still_passed_through(self):
        out = build.render('<table>\n<tr><td width="50%">\n\ncell\n\n</td></tr>\n</table>')
        self.assertIn('<td width="50%">', out)
        self.assertIn("<p>cell</p>", out)

    def test_consecutive_lines_join_into_one_paragraph(self):
        out = build.render("one\ntwo")
        self.assertEqual(out.count("<p>"), 1)
        self.assertIn("one two", out)


class TestBuild(unittest.TestCase):
    def test_title_comes_from_the_first_h1(self):
        self.assertEqual(build.page_title("intro\n\n# Glean Code\n"), "Glean Code")

    def test_title_falls_back(self):
        self.assertEqual(build.page_title("no heading here"), "Glean Code")

    def test_title_ignores_hash_comments_in_code_fences(self):
        # The README's quickstart contains a bash "# or" comment; it is not a title.
        markdown = "```bash\npython3 -m glean_code\n# or\npython3 install.py\n```\n"
        self.assertEqual(build.page_title(markdown), "Glean Code")

    def test_a_page_led_by_an_image_still_gets_one_h1(self):
        with tempfile.TemporaryDirectory() as tmp:
            page = (build.build(out_dir=pathlib.Path(tmp) / "_site") / "index.html").read_text()
            self.assertIn('<h1 class="sr-only">Glean Code</h1>', page)
            self.assertEqual(page.count("<h1"), 1)

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
            self.assertIn('<h2 id="how-it-works">', page)
            # the README's <br> spacers must not survive into the site
            self.assertNotIn("\n<br>\n", page)

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


class TestBanner(unittest.TestCase):
    """The header image is generated from glean_code.ui.GLEAN_WORDMARK."""

    def test_committed_svg_matches_the_generator(self):
        self.assertEqual(
            make_banner.build_svg(),
            BANNER_SVG.read_text(encoding="utf-8"),
            "assets/glean-code-banner.svg is stale -- "
            "run python3 .github/pages/make_banner.py",
        )

    def test_every_wordmark_character_is_drawable(self):
        drawn = set()
        for line in make_banner.wordmark_lines():
            drawn.update(line)
        drawn.discard(" ")
        for char in drawn:
            self.assertTrue(make_banner.cell_shapes(char, 0, 0), "no shape for %r" % char)

    def test_svg_is_well_formed_and_carries_the_meta_line(self):
        svg = make_banner.build_svg()
        ET.fromstring(svg)
        self.assertIn("mode: mock", svg)
        self.assertIn('role="img"', svg)

    def test_banner_is_published_with_the_site(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = build.build(out_dir=pathlib.Path(tmp) / "_site")
            self.assertTrue((out / "assets" / "glean-code-banner.svg").is_file())


if __name__ == "__main__":
    unittest.main()
