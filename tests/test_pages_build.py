"""Tests for the GitHub Pages site builder (.github/pages/build.py).

The builder lives outside the package (it is release tooling, not part of the
REPL), so it is loaded from its path. Like the rest of the suite these tests
touch no network and write only into a temp directory.
"""

import importlib.util
import pathlib
import struct
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


ICONS_PY = REPO_ROOT / ".github" / "pages" / "make_icons.py"
FAVICON_SVG = REPO_ROOT / "assets" / "favicon.svg"
TOUCH_ICON = REPO_ROOT / "assets" / "apple-touch-icon.png"

build = _load("pages_build", BUILD_PY)
make_banner = _load("pages_make_banner", BANNER_PY)
make_icons = _load("pages_make_icons", ICONS_PY)


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

    def test_heading_links_to_itself(self):
        out = build.render("## Quickstart")
        self.assertEqual(
            out, '<h2 id="quickstart"><a class="anchor" href="#quickstart">Quickstart</a></h2>')

    def test_every_heading_level_gets_an_anchor(self):
        out = build.render("# One\n\n## Two\n\n### Three")
        self.assertEqual(out.count('class="anchor"'), 3)
        self.assertIn('href="#three"', out)

    def test_a_heading_that_already_holds_a_link_is_not_double_wrapped(self):
        out = build.render("## See [the docs](docs/COMMANDS.md)")
        self.assertNotIn('class="anchor"', out)
        self.assertEqual(out.count("<a "), 1)

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

    def test_command_table_is_tagged(self):
        out = build.render(
            "| Command | What it does |\n| --- | --- |\n"
            "| `/search \"x\"` | Search |\n| `/flow show` | Draw |")
        self.assertIn('<table class="cmd">', out)

    def test_a_prose_table_is_not_a_command_table(self):
        out = build.render("|  |  |\n| --- | --- |\n| ⚡ **Fast** | it is quick |")
        self.assertIn("<table>", out)
        self.assertNotIn('class="cmd"', out)

    def test_command_table_needs_every_row_to_lead_with_code(self):
        body = [["`/search`", "Search"], ["plain text", "Nope"]]
        self.assertFalse(build.is_command_table(body))
        self.assertTrue(build.is_command_table([["`/a`", "x"], ["`/b`", "y"]]))

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
        self.assertIn(
            '<h1 id="glean-code"><a class="anchor" href="#glean-code">Glean Code</a></h1>', out)
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
            # the tab shows the command you type; the hidden h1 keeps the product name
            self.assertIn("<title>glean_code_cli</title>", page)
            self.assertIn('<h1 class="sr-only">Glean Code</h1>', page)
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

    def test_no_code_block_is_wide_enough_to_overflow(self):
        """Long space-aligned listings used to force a horizontal scroll inside
        the card. Command listings belong in tables, which wrap; code blocks
        stay narrow enough to fit the content column."""
        import html as html_mod
        import re as re_mod

        with tempfile.TemporaryDirectory() as tmp:
            page = (build.build(out_dir=pathlib.Path(tmp) / "_site") / "index.html").read_text()
        widest = 0
        for block in re_mod.findall(r"<pre><code[^>]*>(.*?)</code></pre>", page, re_mod.S):
            for line in html_mod.unescape(block).split("\n"):
                widest = max(widest, len(line))
        self.assertLessEqual(widest, 80, "a code block is %d chars wide" % widest)

    def test_no_unresolved_repo_relative_links_remain(self):
        with tempfile.TemporaryDirectory() as tmp:
            page = (build.build(out_dir=pathlib.Path(tmp) / "_site") / "index.html").read_text()
            self.assertNotIn('href="docs/', page)
            self.assertNotIn('href="LICENSE"', page)


class TestTemplate(unittest.TestCase):
    """Guards for stylesheet rules that a render bug traced back to."""

    def setUp(self):
        self.css = (REPO_ROOT / ".github" / "pages" / "template.html").read_text()

    def _rule(self, selector):
        body = self.css[self.css.index(selector) + len(selector):]
        return body[:body.index("}")]

    def test_badge_height_is_pinned(self):
        # Without an explicit height the flex line stretched the badges and the
        # widest one, clamped by the space left, stayed shorter than the rest.
        rule = self._rule("p.badges img {")
        for decl in ("display: block", "height: 28px", "width: auto", "flex: 0 0 auto"):
            self.assertIn(decl, rule)

    def test_tagline_is_set_in_the_mono_face(self):
        rule = self.css[self.css.index('[align="center"] .banner + p {'):]
        self.assertIn("font-family: var(--mono)", rule[:rule.index("}")])

    def test_headings_carry_their_markdown_level(self):
        self.assertIn('h2 .anchor::before { content: "##"; }', self.css)
        self.assertIn('h3 .anchor::before { content: "###"; }', self.css)

    def test_headings_and_table_headers_use_the_mono_face(self):
        for selector in ("h1, h2, h3 {", ".doc thead th {"):
            rule = self.css[self.css.index(selector):]
            self.assertIn("font-family: var(--mono)", rule[:rule.index("}")], selector)

    def test_badge_links_are_not_leaded(self):
        # Two badges are wrapped in links. An inline image inside an <a> carries
        # line-box leading, which made those flex items 37.5px tall against the
        # bare images' 28px -- the row's cross size, and the misalignment.
        self.assertIn("line-height: 0", self._rule("p.badges {"))
        anchor = self._rule("p.badges a {")
        self.assertIn("display: flex", anchor)
        self.assertIn("flex: 0 0 auto", anchor)

    def test_image_rows_do_not_stretch_their_items(self):
        self.assertIn("align-items: center", self._rule("p.imgrow {"))


class TestIcons(unittest.TestCase):
    """Browser icons are generated by .github/pages/make_icons.py."""

    def test_committed_favicon_matches_the_generator(self):
        self.assertEqual(
            make_icons.svg(),
            FAVICON_SVG.read_text(encoding="utf-8"),
            "assets/favicon.svg is stale -- run python3 .github/pages/make_icons.py",
        )

    def test_committed_touch_icon_matches_the_generator(self):
        self.assertEqual(
            make_icons.png(),
            TOUCH_ICON.read_bytes(),
            "assets/apple-touch-icon.png is stale -- run python3 .github/pages/make_icons.py",
        )

    def test_favicon_is_well_formed_svg(self):
        ET.fromstring(make_icons.svg())

    def test_touch_icon_is_a_180px_png(self):
        data = make_icons.png()
        self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n")
        # IHDR width/height live at bytes 16..24
        width, height = struct.unpack(">II", data[16:24])
        self.assertEqual((width, height), (180, 180))

    def test_the_mark_covers_and_misses_the_right_pixels(self):
        rows = make_icons.png_rows(32)
        def pixel(x, y):
            return tuple(rows[y][x * 3:x * 3 + 3])
        # the cursor block is solid cyan; a far corner stays plate
        self.assertEqual(pixel(22, 21), make_icons.MARK)
        self.assertEqual(pixel(1, 1), make_icons.PLATE)

    def test_page_declares_both_icons(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = build.build(out_dir=pathlib.Path(tmp) / "_site")
            page = (out / "index.html").read_text()
            self.assertIn('rel="icon" type="image/svg+xml" href="assets/favicon.svg"', page)
            self.assertIn('rel="apple-touch-icon" href="assets/apple-touch-icon.png"', page)
            self.assertTrue((out / "assets" / "favicon.svg").is_file())
            self.assertTrue((out / "assets" / "apple-touch-icon.png").is_file())


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
