"""Plain-text extraction from local files, stdlib only.

Feeds the personal index (`personal.py`). Given a path, `extract()` returns
`(text, title_hint)` — the searchable body and, when the format carries one, a
better title than the filename.

Formats fall into two families:

  * Text-ish (.txt, .md, .markdown, .json, .html) — read and normalise.
  * Office (.docx, .xlsx, .pptx) — these are ZIP archives of XML, so
    `zipfile` + `xml.etree` reads them at zero dependency cost. This is why
    a personal index can cover a real Documents folder without pulling in
    python-docx or openpyxl.

Deliberately out of scope: PDF and legacy binary .doc/.xls/.ppt. Neither is
reachable from the stdlib, and shelling out to pdftotext would make results
depend on what happens to be installed. Unsupported extensions raise
ExtractError so the caller can record a reason rather than silently indexing
an empty document.
"""
from __future__ import annotations

import json
import re
import zipfile
from html.parser import HTMLParser
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from xml.etree import ElementTree


class ExtractError(Exception):
    """A file could not be turned into text. The message is user-facing."""


# ZIP quota. A 2 KB .docx can declare a 4 GB member, and reading it costs the
# whole machine's memory, so both the individual member and the declared total
# are capped before anything is decompressed.
MAX_MEMBER_BYTES = 32 * 1024 * 1024
MAX_ARCHIVE_BYTES = 128 * 1024 * 1024

# Truncation guard for a single document's extracted text. Well past any real
# document; stops one pathological file from dominating the index.
MAX_TEXT_CHARS = 4 * 1024 * 1024

TEXT_EXTS = (".txt", ".md", ".markdown")
HTML_EXTS = (".html", ".htm")
JSON_EXTS = (".json",)
OFFICE_EXTS = (".docx", ".xlsx", ".pptx")

# Ordered for display in /help and skip messages.
SUPPORTED_EXTS: Tuple[str, ...] = TEXT_EXTS + HTML_EXTS + JSON_EXTS + OFFICE_EXTS

# Glob patterns for walk_files(), derived from the same list so the two can
# never drift apart.
INCLUDE_PATTERNS: Tuple[str, ...] = tuple(f"*{ext}" for ext in SUPPORTED_EXTS)

_MIME_BY_EXT: Dict[str, str] = {
    ".txt":       "text/plain",
    ".md":        "text/markdown",
    ".markdown":  "text/markdown",
    ".html":      "text/html",
    ".htm":       "text/html",
    ".json":      "application/json",
    ".docx":      "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx":      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".pptx":      "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}

# XML namespaces, as ElementTree's {uri}tag prefixes.
_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
_S = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_DC = "{http://purl.org/dc/elements/1.1/}"

_WS_RUN = re.compile(r"[ \t ]+")
_BLANK_RUN = re.compile(r"\n{3,}")


def supported_extensions() -> List[str]:
    return list(SUPPORTED_EXTS)


def is_supported(path: Path) -> bool:
    return Path(path).suffix.lower() in SUPPORTED_EXTS


def mime_for(path: Path) -> str:
    return _MIME_BY_EXT.get(Path(path).suffix.lower(), "application/octet-stream")


def normalise(text: str) -> str:
    """Collapse whitespace without destroying paragraph structure.

    Runs of spaces and tabs become one space, trailing space per line goes,
    and three or more blank lines become two. Paragraph breaks survive
    because chunking uses them as split points.
    """
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [_WS_RUN.sub(" ", line).rstrip() for line in text.split("\n")]
    out = _BLANK_RUN.sub("\n\n", "\n".join(lines)).strip()
    if len(out) > MAX_TEXT_CHARS:
        out = out[:MAX_TEXT_CHARS].rsplit("\n", 1)[0] + "\n\n[… truncated by the indexer]"
    return out


# ---------------------------------------------------------------- text / html


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        raise ExtractError(f"could not read the file: {e}") from None


class _HTMLText(HTMLParser):
    """Tag stripper that keeps block structure and drops script/style."""

    _SKIP = {"script", "style", "noscript", "template", "svg"}
    _BLOCK = {"p", "div", "br", "li", "tr", "section", "article", "header",
              "footer", "blockquote", "pre", "h1", "h2", "h3", "h4", "h5", "h6"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: List[str] = []
        self.title: Optional[str] = None
        self._skip_depth = 0
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        if tag in self._SKIP:
            self._skip_depth += 1
        elif tag == "title":
            self._in_title = True
        elif tag in self._BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self._SKIP:
            self._skip_depth = max(0, self._skip_depth - 1)
        elif tag == "title":
            self._in_title = False
        elif tag in self._BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if self._skip_depth:
            return
        if self._in_title:
            self.title = (self.title or "") + data
            return
        if data.strip():
            self.parts.append(data)


def _extract_html(path: Path) -> Tuple[str, Optional[str]]:
    parser = _HTMLText()
    try:
        parser.feed(_read_text(path))
        parser.close()
    except ExtractError:
        raise
    except Exception as e:  # malformed markup should not kill an index run
        raise ExtractError(f"could not parse the HTML: {e}") from None
    title = (parser.title or "").strip() or None
    return "".join(parser.parts), title


def _flatten_json(value, prefix: str = "") -> List[str]:
    """Render JSON as `key.path: value` lines so both halves are searchable."""
    out: List[str] = []
    if isinstance(value, dict):
        for key, val in value.items():
            out.extend(_flatten_json(val, f"{prefix}.{key}" if prefix else str(key)))
    elif isinstance(value, list):
        for i, val in enumerate(value):
            out.extend(_flatten_json(val, f"{prefix}[{i}]"))
    else:
        out.append(f"{prefix}: {value}" if prefix else str(value))
    return out


def _extract_json(path: Path) -> Tuple[str, Optional[str]]:
    raw = _read_text(path)
    try:
        data = json.loads(raw)
    except ValueError:
        # Invalid JSON is still text worth searching — JSONL, a truncated
        # export, a config with comments. Index it verbatim.
        return raw, None
    title = None
    if isinstance(data, dict):
        for key in ("title", "name", "subject"):
            if isinstance(data.get(key), str) and data[key].strip():
                title = data[key].strip()
                break
    return "\n".join(_flatten_json(data)), title


# ---------------------------------------------------------------- office (zip)


def _open_zip(path: Path) -> zipfile.ZipFile:
    try:
        zf = zipfile.ZipFile(str(path))
    except (zipfile.BadZipFile, OSError) as e:
        raise ExtractError(f"not a readable Office file: {e}") from None
    declared = sum(max(0, i.file_size) for i in zf.infolist())
    if declared > MAX_ARCHIVE_BYTES:
        zf.close()
        raise ExtractError(
            f"archive declares {declared / 1e6:.0f} MB of content, over the "
            f"{MAX_ARCHIVE_BYTES / 1e6:.0f} MB limit"
        )
    return zf


def _member(zf: zipfile.ZipFile, name: str) -> Optional[bytes]:
    """Read one archive member, or None when it isn't present."""
    try:
        info = zf.getinfo(name)
    except KeyError:
        return None
    if info.file_size > MAX_MEMBER_BYTES:
        raise ExtractError(f"{name} is {info.file_size / 1e6:.0f} MB, over the per-part limit")
    try:
        return zf.read(name)
    except (zipfile.BadZipFile, OSError, RuntimeError) as e:
        raise ExtractError(f"could not read {name}: {e}") from None


def _xml(data: bytes) -> ElementTree.Element:
    try:
        return ElementTree.fromstring(data)
    except ElementTree.ParseError as e:
        raise ExtractError(f"malformed XML inside the document: {e}") from None


def _core_title(zf: zipfile.ZipFile) -> Optional[str]:
    """The document's own title from docProps/core.xml, when it set one."""
    data = _member(zf, "docProps/core.xml")
    if not data:
        return None
    try:
        root = _xml(data)
    except ExtractError:
        return None
    node = root.find(f"{_DC}title")
    if node is not None and (node.text or "").strip():
        return node.text.strip()
    return None


def _extract_docx(path: Path) -> Tuple[str, Optional[str]]:
    zf = _open_zip(path)
    try:
        data = _member(zf, "word/document.xml")
        if data is None:
            raise ExtractError("no word/document.xml — not a Word document")
        root = _xml(data)
        paragraphs: List[str] = []
        # Paragraph order is document order, and a <w:p> maps to a line. Runs
        # inside it are split arbitrarily by formatting, so they concatenate.
        for para in root.iter(f"{_W}p"):
            buf: List[str] = []
            for node in para.iter():
                tag = node.tag
                if tag == f"{_W}t":
                    buf.append(node.text or "")
                elif tag == f"{_W}tab":
                    buf.append("\t")
                elif tag in (f"{_W}br", f"{_W}cr"):
                    buf.append("\n")
            line = "".join(buf).strip()
            if line:
                paragraphs.append(line)
        return "\n\n".join(paragraphs), _core_title(zf)
    finally:
        zf.close()


_SHEET_RE = re.compile(r"^xl/worksheets/sheet(\d+)\.xml$")


def _shared_strings(zf: zipfile.ZipFile) -> List[str]:
    data = _member(zf, "xl/sharedStrings.xml")
    if not data:
        return []
    root = _xml(data)
    out: List[str] = []
    for si in root.findall(f"{_S}si"):
        out.append("".join(t.text or "" for t in si.iter(f"{_S}t")))
    return out


def _sheet_names(zf: zipfile.ZipFile) -> Dict[str, str]:
    """sheetId-ordered names, keyed by the sheetN.xml index we can see."""
    data = _member(zf, "xl/workbook.xml")
    if not data:
        return {}
    try:
        root = _xml(data)
    except ExtractError:
        return {}
    names: Dict[str, str] = {}
    for i, sheet in enumerate(root.iter(f"{_S}sheet"), 1):
        name = sheet.get("name")
        if name:
            names[str(i)] = name
    return names


def _extract_xlsx(path: Path) -> Tuple[str, Optional[str]]:
    zf = _open_zip(path)
    try:
        strings = _shared_strings(zf)
        names = _sheet_names(zf)
        sheets = sorted(
            ((m.group(1), n) for m, n in
             ((_SHEET_RE.match(name), name) for name in zf.namelist()) if m),
            key=lambda pair: int(pair[0]),
        )
        if not sheets:
            raise ExtractError("no worksheets found — not a Workbook")
        blocks: List[str] = []
        for index, member in sheets:
            root = _xml(_member(zf, member) or b"<x/>")
            rows: List[str] = []
            for row in root.iter(f"{_S}row"):
                cells: List[str] = []
                for cell in row.findall(f"{_S}c"):
                    cells.append(_cell_text(cell, strings))
                line = "\t".join(cells).strip()
                if line:
                    rows.append(line)
            if rows:
                heading = names.get(index, f"Sheet {index}")
                blocks.append(f"## {heading}\n" + "\n".join(rows))
        return "\n\n".join(blocks), _core_title(zf)
    finally:
        zf.close()


def _cell_text(cell: ElementTree.Element, strings: List[str]) -> str:
    kind = cell.get("t")
    if kind == "s":  # shared-string index
        node = cell.find(f"{_S}v")
        try:
            return strings[int((node.text or "0"))] if node is not None else ""
        except (ValueError, IndexError):
            return ""
    if kind == "inlineStr":
        node = cell.find(f"{_S}is")
        if node is not None:
            return "".join(t.text or "" for t in node.iter(f"{_S}t"))
        return ""
    node = cell.find(f"{_S}v")
    if node is not None:
        return node.text or ""
    # A formula cell with no cached value carries only the expression.
    formula = cell.find(f"{_S}f")
    return f"={formula.text}" if formula is not None and formula.text else ""


_SLIDE_RE = re.compile(r"^ppt/slides/slide(\d+)\.xml$")


def _extract_pptx(path: Path) -> Tuple[str, Optional[str]]:
    zf = _open_zip(path)
    try:
        slides = sorted(
            ((m.group(1), n) for m, n in
             ((_SLIDE_RE.match(name), name) for name in zf.namelist()) if m),
            key=lambda pair: int(pair[0]),
        )
        if not slides:
            raise ExtractError("no slides found — not a Presentation")
        blocks: List[str] = []
        for index, member in slides:
            root = _xml(_member(zf, member) or b"<x/>")
            # Every text run in a slide, in document order. Shape grouping is
            # not worth reconstructing for search purposes.
            lines = [(t.text or "").strip() for t in root.iter(f"{_A}t")]
            body = "\n".join(line for line in lines if line)
            if body:
                blocks.append(f"## Slide {index}\n{body}")
        return "\n\n".join(blocks), _core_title(zf)
    finally:
        zf.close()


# ---------------------------------------------------------------- entry point


_EXTRACTORS = {}
for _ext in TEXT_EXTS:
    _EXTRACTORS[_ext] = lambda p: (_read_text(p), None)
for _ext in HTML_EXTS:
    _EXTRACTORS[_ext] = _extract_html
for _ext in JSON_EXTS:
    _EXTRACTORS[_ext] = _extract_json
_EXTRACTORS[".docx"] = _extract_docx
_EXTRACTORS[".xlsx"] = _extract_xlsx
_EXTRACTORS[".pptx"] = _extract_pptx


def extract(path: Path) -> Tuple[str, Optional[str]]:
    """Return (normalised text, title hint) for a supported file.

    Raises ExtractError for an unsupported extension or an unreadable file.
    The title hint is None whenever the format carries no title of its own,
    leaving the caller to fall back to the filename.
    """
    path = Path(path)
    ext = path.suffix.lower()
    fn = _EXTRACTORS.get(ext)
    if fn is None:
        raise ExtractError(
            f"unsupported extension {ext or '(none)'} "
            f"(supported: {', '.join(SUPPORTED_EXTS)})"
        )
    text, title = fn(path)
    return normalise(text), (title.strip() if title else None)
