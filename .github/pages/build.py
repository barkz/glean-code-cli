#!/usr/bin/env python3
"""Render README.md as the project's GitHub Pages site.

Standard library only, like the rest of the repo: no Jekyll, no Markdown
package, no build step beyond `python3 .github/pages/build.py`.

The converter handles exactly the Markdown the README uses -- headings,
paragraphs, GFM tables, fenced code, images, links, `> [!NOTE]` alerts and
horizontal rules -- and passes raw HTML blocks straight through, which is how
the centred header and the two-column feature table survive intact. Relative
links to repository files (`docs/INSTALL.md`, `LICENSE`) are rewritten to
github.com, since the site publishes one page and not the whole tree.

Usage:
    python3 .github/pages/build.py [output_dir]    # default: _site
"""

import html
import pathlib
import re
import shutil
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
HERE = pathlib.Path(__file__).resolve().parent

REPO_URL = "https://github.com/barkz/glean-code-cli"
# What the browser tab says. Deliberately the command you type, not the prose
# title -- the hidden <h1> below still carries the product name.
SITE_TITLE = "glean_code_cli"
BLOB_URL = REPO_URL + "/blob/main/"

# Directories copied next to index.html so relative image paths keep working.
ASSET_DIRS = ("assets",)

_FENCE = "```"
_BLOCK_STARTS = ("#", _FENCE, "|", "<", ">", "---")


# --------------------------------------------------------------------------
# inline markup
# --------------------------------------------------------------------------

_CODE_SPAN = re.compile(r"`([^`]+)`")
_IMAGE = re.compile(r"!\[([^\]]*)\]\(([^)\s]+)\)")
_LINK = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")
_BOLD = re.compile(r"\*\*([^*]+)\*\*")
_PLACEHOLDER = "\x00%d\x00"


def resolve_href(target):
    """Point a relative repository path at github.com; leave URLs alone."""
    if target.startswith(("http://", "https://", "mailto:", "#")):
        return target
    return BLOB_URL + target.lstrip("./")


def inline(text):
    """Convert inline Markdown. Raw HTML in the source is trusted, not escaped."""
    spans = []

    def stash(match):
        spans.append("<code>%s</code>" % html.escape(match.group(1), quote=False))
        return _PLACEHOLDER % (len(spans) - 1)

    text = _CODE_SPAN.sub(stash, text)
    text = _IMAGE.sub(
        lambda m: '<img src="%s" alt="%s">' % (m.group(2), html.escape(m.group(1), quote=True)),
        text,
    )
    text = _LINK.sub(
        lambda m: '<a href="%s">%s</a>' % (resolve_href(m.group(2)), m.group(1)),
        text,
    )
    text = _BOLD.sub(r"<strong>\1</strong>", text)
    for index, span in enumerate(spans):
        text = text.replace(_PLACEHOLDER % index, span)
    return text


def slug(text):
    """GitHub-style heading anchor: lowercased, punctuation and emoji dropped."""
    bare = re.sub(r"`|\*\*", "", text)
    bare = re.sub(r"[^\w\s-]", "", bare, flags=re.UNICODE)
    return re.sub(r"\s+", "-", bare.strip().lower()).strip("-")


def is_image_only(markup):
    """True for a paragraph holding nothing but images (badge rows, screenshots)."""
    if "<img" not in markup:
        return False
    return re.sub(r"<a [^>]*>|</a>|<img [^>]*>", "", markup).strip() == ""


def image_paragraph_class(markup):
    """Classify an image-only paragraph so the stylesheet can treat each kind
    differently: badge strips, diagrams and screenshots want nothing alike."""
    if not is_image_only(markup):
        return None
    sources = re.findall(r'<img src="([^"]+)"', markup)
    if all("shields.io" in src for src in sources):
        return "badges"
    if all(src.lower().endswith(".svg") for src in sources):
        return "diagram"
    return "shot"


_BARE_BREAK = re.compile(r"^(?:<br\s*/?>\s*)+$", re.IGNORECASE)


# --------------------------------------------------------------------------
# block markup
# --------------------------------------------------------------------------

def table_cells(line):
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def is_table_divider(cells):
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell or "") for cell in cells)


def is_command_table(body):
    """True when every row leads with a code span -- a command/effect listing."""
    if not body:
        return False
    return all(
        len(row) >= 2 and row[0].startswith("`") and row[0].endswith("`") and len(row[0]) > 2
        for row in body
    )


def render_table(rows):
    """GFM table. An all-empty header row is dropped -- the README uses those
    purely to get a two-column layout, and a blank <thead> is just a gap."""
    head, body = None, rows
    if len(rows) >= 2 and is_table_divider(rows[1]):
        head, body = rows[0], rows[2:]
        if not any(cell for cell in head):
            head = None
    parts = ['<table class="cmd">' if is_command_table(body) else "<table>"]
    if head:
        parts.append("<thead><tr>%s</tr></thead>" % "".join(
            "<th>%s</th>" % inline(cell) for cell in head))
    parts.append("<tbody>")
    for row in body:
        parts.append("<tr>%s</tr>" % "".join("<td>%s</td>" % inline(cell) for cell in row))
    parts.append("</tbody></table>")
    return "\n".join(parts)


def render_alert(kind, body):
    return (
        '<div class="alert alert-%s">'
        '<p class="alert-label">%s</p>%s</div>' % (kind, kind, body)
    )


def starts_block(line):
    stripped = line.strip()
    return stripped.startswith(_BLOCK_STARTS)


def render(markdown):
    """Markdown -> HTML for the subset the README uses."""
    lines = markdown.split("\n")
    out = []
    i, total = 0, len(lines)
    # An image standing before any prose is the page's header image, not a
    # figure inside it, and wants no surface of its own.
    seen_prose = False

    while i < total:
        line = lines[i]
        stripped = line.strip()

        if not stripped:
            i += 1
            continue

        # The README uses bare <br> tags to force breathing room on github.com.
        # The site sets its own rhythm in CSS, so they would only leave holes.
        if _BARE_BREAK.match(stripped):
            i += 1
            continue

        # fenced code
        if stripped.startswith(_FENCE):
            lang = stripped[len(_FENCE):].strip()
            i += 1
            buf = []
            while i < total and not lines[i].strip().startswith(_FENCE):
                buf.append(lines[i])
                i += 1
            i += 1
            attr = ' class="language-%s"' % lang if lang else ""
            out.append("<pre><code%s>%s</code></pre>" % (
                attr, html.escape("\n".join(buf), quote=False)))
            continue

        # > [!NOTE] alerts and plain blockquotes
        if stripped.startswith(">"):
            kind = "note"
            buf = []
            while i < total and lines[i].strip().startswith(">"):
                text = lines[i].strip().lstrip(">").strip()
                marker = re.match(r"\[!(\w+)\]", text)
                if marker:
                    kind = marker.group(1).lower()
                elif text:
                    buf.append(text)
                i += 1
            out.append(render_alert(kind, "<p>%s</p>" % inline(" ".join(buf))))
            continue

        # horizontal rule
        if re.fullmatch(r"-{3,}", stripped):
            out.append("<hr>")
            i += 1
            continue

        # heading
        heading = re.match(r"(#{1,6})\s+(.*)", stripped)
        if heading:
            level = len(heading.group(1))
            text = heading.group(2).strip()
            out.append('<h%d id="%s">%s</h%d>' % (level, slug(text), inline(text), level))
            seen_prose = True
            i += 1
            continue

        # table
        if stripped.startswith("|"):
            rows = []
            while i < total and lines[i].strip().startswith("|"):
                rows.append(table_cells(lines[i]))
                i += 1
            out.append(render_table(rows))
            continue

        # raw HTML block -- passed through verbatim up to the next blank line
        if stripped.startswith("<"):
            buf = []
            while i < total and lines[i].strip():
                buf.append(lines[i])
                i += 1
            out.append("\n".join(buf))
            continue

        # paragraph
        buf = []
        while i < total and lines[i].strip() and not starts_block(lines[i]):
            buf.append(lines[i].strip())
            i += 1
        markup = inline(" ".join(buf))
        kind = image_paragraph_class(markup)
        # A strip of badges is never the header image, wherever it sits.
        if kind and kind != "badges" and not seen_prose:
            kind = "banner"
        if not kind:
            seen_prose = True
        css = ' class="imgrow %s"' % kind if kind else ""
        out.append("<p%s>%s</p>" % (css, markup))

    return "\n\n".join(out)


# --------------------------------------------------------------------------
# site
# --------------------------------------------------------------------------

def page_title(markdown):
    """First real h1, ignoring '#' comments inside fenced code blocks."""
    in_fence = False
    for line in markdown.split("\n"):
        if line.strip().startswith(_FENCE):
            in_fence = not in_fence
            continue
        if not in_fence and line.startswith("# "):
            return line[2:].strip()
    return "Glean Code"


def build(out_dir=None, root=None):
    """Write index.html (plus assets) and return the output directory."""
    root = pathlib.Path(root) if root else ROOT
    out_dir = pathlib.Path(out_dir) if out_dir else root / "_site"

    markdown = (root / "README.md").read_text(encoding="utf-8")
    template = (HERE / "template.html").read_text(encoding="utf-8")

    heading = page_title(markdown)
    content = render(markdown)
    if "<h1" not in content:
        # The README leads with the wordmark image; keep a real heading for
        # screen readers and search engines.
        content = '<h1 class="sr-only">%s</h1>\n\n%s' % (heading, content)

    page = template.replace("{{TITLE}}", SITE_TITLE)
    page = page.replace("{{REPO_URL}}", REPO_URL)
    page = page.replace("{{CONTENT}}", content)

    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)
    (out_dir / "index.html").write_text(page, encoding="utf-8")
    # Pages would otherwise hand the directory to Jekyll.
    (out_dir / ".nojekyll").write_text("", encoding="utf-8")

    for name in ASSET_DIRS:
        source = root / name
        if source.is_dir():
            shutil.copytree(source, out_dir / name)

    return out_dir


def main(argv):
    out_dir = build(argv[1] if len(argv) > 1 else None)
    index = out_dir / "index.html"
    print("built %s (%d bytes)" % (index, index.stat().st_size))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
