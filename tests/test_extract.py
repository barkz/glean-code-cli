"""Tests for local text extraction.

The Office formats are ZIP archives of XML, so every fixture here is built
with zipfile rather than committed as a binary. That keeps the repo text-only
and documents the exact parts of each format the extractor depends on.
"""
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from glean_code import extract

_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_A = "http://schemas.openxmlformats.org/drawingml/2006/main"
_S = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"

_R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_PKG = "http://schemas.openxmlformats.org/package/2006/relationships"
_PML = "http://schemas.openxmlformats.org/presentationml/2006/main"

_CORE = ('<cp:coreProperties xmlns:cp="x" '
         'xmlns:dc="http://purl.org/dc/elements/1.1/">'
         '<dc:title>{}</dc:title></cp:coreProperties>')


def _rels_part(pairs):
    """A .rels part mapping rId -> target, as both Office formats use."""
    items = "".join(f'<Relationship Id="{rid}" Target="{target}" Type="x"/>'
                    for rid, target in pairs)
    return f'<Relationships xmlns="{_PKG}">{items}</Relationships>'


def _workbook(sheets):
    """workbook.xml listing (name, rId) in workbook order."""
    items = "".join(f'<sheet name="{n}" r:id="{r}"/>' for n, r in sheets)
    return f'<workbook xmlns="{_S}" xmlns:r="{_R}"><sheets>{items}</sheets></workbook>'


def _sheet_xml(text):
    return (f'<worksheet xmlns="{_S}"><sheetData><row>'
            f'<c t="inlineStr"><is><t>{text}</t></is></c>'
            '</row></sheetData></worksheet>')


def _presentation(rids):
    items = "".join(f'<p:sldId r:id="{r}"/>' for r in rids)
    return (f'<p:presentation xmlns:p="{_PML}" xmlns:r="{_R}">'
            f'<p:sldIdLst>{items}</p:sldIdLst></p:presentation>')


class _Tmp(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def write(self, name: str, text: str) -> Path:
        path = self.root / name
        path.write_text(text, encoding="utf-8")
        return path

    def zipped(self, name: str, members: dict) -> Path:
        path = self.root / name
        with zipfile.ZipFile(path, "w") as zf:
            for member, body in members.items():
                zf.writestr(member, body)
        return path


class TestRegistry(_Tmp):
    def test_supported_extensions_and_include_patterns_agree(self):
        exts = extract.supported_extensions()
        self.assertEqual(tuple(f"*{e}" for e in exts), extract.INCLUDE_PATTERNS)

    def test_office_formats_are_supported(self):
        for ext in (".docx", ".xlsx", ".pptx"):
            self.assertIn(ext, extract.supported_extensions())

    def test_is_supported_and_mime(self):
        self.assertTrue(extract.is_supported(Path("a.md")))
        self.assertFalse(extract.is_supported(Path("a.pdf")))
        self.assertEqual(extract.mime_for(Path("a.md")), "text/markdown")
        self.assertIn("wordprocessingml", extract.mime_for(Path("a.docx")))

    def test_unsupported_extension_raises_with_the_supported_list(self):
        with self.assertRaises(extract.ExtractError) as ctx:
            extract.extract(self.root / "report.pdf")
        self.assertIn(".pdf", str(ctx.exception))
        self.assertIn(".docx", str(ctx.exception))


class TestNormalise(unittest.TestCase):
    def test_collapses_spaces_but_keeps_paragraphs(self):
        out = extract.normalise("a  \t b\n\n\n\nc")
        self.assertEqual(out, "a b\n\nc")

    def test_normalises_line_endings(self):
        self.assertEqual(extract.normalise("a\r\nb\rc"), "a\nb\nc")

    def test_truncates_beyond_the_cap(self):
        out = extract.normalise("word " * (extract.MAX_TEXT_CHARS // 2))
        self.assertLess(len(out), extract.MAX_TEXT_CHARS + 100)
        self.assertIn("truncated by the indexer", out)


class TestTextFormats(_Tmp):
    def test_plain_text_has_no_title_hint(self):
        text, title = extract.extract(self.write("a.txt", "hello there"))
        self.assertEqual(text, "hello there")
        self.assertIsNone(title)

    def test_markdown_keeps_heading_markers(self):
        text, _ = extract.extract(self.write("a.md", "# Heading\n\nbody"))
        self.assertIn("# Heading", text)

    def test_html_strips_tags_and_takes_the_title(self):
        path = self.write("a.html",
                          "<html><head><title>Onboarding</title>"
                          "<style>p{color:red}</style></head><body>"
                          "<h1>Welcome</h1><script>evil()</script>"
                          "<p>Read the <b>handbook</b>.</p></body></html>")
        text, title = extract.extract(path)
        self.assertEqual(title, "Onboarding")
        self.assertIn("Welcome", text)
        self.assertIn("Read the handbook.", text)

    def test_html_drops_script_and_style_bodies(self):
        text, _ = extract.extract(self.write(
            "a.html", "<style>p{color:red}</style><script>evil()</script><p>ok</p>"))
        self.assertNotIn("color:red", text)
        self.assertNotIn("evil", text)

    def test_json_flattens_paths_and_finds_a_title(self):
        path = self.write("a.json", '{"title":"Runbook","steps":["restart"],'
                                    '"owner":{"email":"a@b.c"}}')
        text, title = extract.extract(path)
        self.assertEqual(title, "Runbook")
        self.assertIn("steps[0]: restart", text)
        self.assertIn("owner.email: a@b.c", text)

    def test_invalid_json_is_indexed_verbatim(self):
        text, title = extract.extract(self.write("a.json", "{not json at all"))
        self.assertIn("not json at all", text)
        self.assertIsNone(title)


class TestOfficeFormats(_Tmp):
    def test_docx_paragraphs_runs_and_core_title(self):
        path = self.zipped("a.docx", {
            "docProps/core.xml": _CORE.format("Q3 Compensation"),
            "word/document.xml": f'<w:document xmlns:w="{_W}"><w:body>'
                                 '<w:p><w:r><w:t>Salary bands</w:t></w:r>'
                                 '<w:r><w:t> for FY27</w:t></w:r></w:p>'
                                 '<w:p><w:r><w:t>Band 4</w:t></w:r></w:p>'
                                 '<w:p/></w:body></w:document>',
        })
        text, title = extract.extract(path)
        self.assertEqual(title, "Q3 Compensation")
        # Runs inside one paragraph join; separate paragraphs stay separate.
        self.assertIn("Salary bands for FY27", text)
        self.assertIn("Band 4", text)

    def test_docx_without_document_xml_raises(self):
        path = self.zipped("a.docx", {"other.xml": "<x/>"})
        with self.assertRaises(extract.ExtractError):
            extract.extract(path)

    def test_xlsx_shared_strings_inline_and_sheet_names(self):
        path = self.zipped("a.xlsx", {
            "xl/workbook.xml": _workbook([("Headcount", "rId1")]),
            "xl/_rels/workbook.xml.rels": _rels_part([("rId1", "worksheets/sheet1.xml")]),
            "xl/sharedStrings.xml": f'<sst xmlns="{_S}">'
                                    '<si><t>Region</t></si><si><t>EMEA</t></si></sst>',
            "xl/worksheets/sheet1.xml": f'<worksheet xmlns="{_S}"><sheetData>'
                                        '<row><c t="s"><v>0</v></c><c t="s"><v>1</v></c></row>'
                                        '<row><c><v>42</v></c>'
                                        '<c t="inlineStr"><is><t>inline</t></is></c></row>'
                                        '</sheetData></worksheet>',
        })
        text, _ = extract.extract(path)
        self.assertIn("## Headcount", text)
        self.assertIn("Region", text)
        self.assertIn("EMEA", text)
        self.assertIn("42", text)
        self.assertIn("inline", text)

    def test_xlsx_sheet_names_follow_relationships_not_position(self):
        """Regression: a reordered workbook must not pair names with the wrong sheet.

        Position in workbook.xml is unrelated to the sheetN.xml number. Keying by
        position produced "## Beta" above sheet1.xml's content, and sheet names
        carry bm25 weight.
        """
        path = self.zipped("a.xlsx", {
            "xl/workbook.xml": _workbook([("Beta", "rId2"), ("Alpha", "rId1")]),
            "xl/_rels/workbook.xml.rels": _rels_part([
                ("rId1", "worksheets/sheet1.xml"),
                ("rId2", "worksheets/sheet2.xml")]),
            "xl/worksheets/sheet1.xml": _sheet_xml("ALPHA-CONTENT"),
            "xl/worksheets/sheet2.xml": _sheet_xml("BETA-CONTENT"),
        })
        text, _ = extract.extract(path)
        self.assertIn("## Beta\nBETA-CONTENT", text)
        self.assertIn("## Alpha\nALPHA-CONTENT", text)
        # Workbook order, not filename order.
        self.assertLess(text.index("Beta"), text.index("Alpha"))

    def test_xlsx_without_relationships_uses_generic_labels(self):
        """A real name paired with the wrong sheet is worse than no name."""
        path = self.zipped("a.xlsx", {
            "xl/workbook.xml": _workbook([("Beta", "rId2"), ("Alpha", "rId1")]),
            "xl/worksheets/sheet1.xml": _sheet_xml("ALPHA-CONTENT"),
        })
        text, _ = extract.extract(path)
        self.assertIn("## Sheet 1", text)
        self.assertNotIn("Beta", text)

    def test_xlsx_out_of_range_shared_string_does_not_raise(self):
        path = self.zipped("a.xlsx", {
            "xl/worksheets/sheet1.xml": f'<worksheet xmlns="{_S}"><sheetData>'
                                        '<row><c t="s"><v>99</v></c></row>'
                                        '</sheetData></worksheet>',
        })
        text, _ = extract.extract(path)
        self.assertEqual(text, "")

    def test_xlsx_without_worksheets_raises(self):
        with self.assertRaises(extract.ExtractError):
            extract.extract(self.zipped("a.xlsx", {"xl/workbook.xml": "<w/>"}))

    def test_pptx_slides_are_numbered_in_order(self):
        path = self.zipped("a.pptx", {
            "ppt/slides/slide10.xml": f'<sld xmlns:a="{_A}"><a:t>Tenth</a:t></sld>',
            "ppt/slides/slide2.xml": f'<sld xmlns:a="{_A}"><a:t>Second</a:t></sld>',
        })
        text, _ = extract.extract(path)
        # No relationships: numeric filename ordering, not lexicographic.
        self.assertLess(text.index("Second"), text.index("Tenth"))
        self.assertIn("## Slide 2", text)

    def test_pptx_order_and_numbering_follow_sldidlst(self):
        """Regression: slideN.xml is creation order, not display order.

        Move slide 1 to the end of a deck and the file keeps its name, so citing
        "Slide 1" would point a reader at the wrong slide.
        """
        path = self.zipped("a.pptx", {
            "ppt/presentation.xml": _presentation(["rId3", "rId1"]),
            "ppt/_rels/presentation.xml.rels": _rels_part([
                ("rId1", "slides/slide1.xml"),
                ("rId3", "slides/slide3.xml")]),
            "ppt/slides/slide1.xml": f'<sld xmlns:a="{_A}"><a:t>WAS-FIRST</a:t></sld>',
            "ppt/slides/slide3.xml": f'<sld xmlns:a="{_A}"><a:t>NOW-FIRST</a:t></sld>',
        })
        text, _ = extract.extract(path)
        # slide3.xml is presented first, so it is "Slide 1".
        self.assertIn("## Slide 1\nNOW-FIRST", text)
        self.assertIn("## Slide 2\nWAS-FIRST", text)

    def test_pptx_without_slides_raises(self):
        with self.assertRaises(extract.ExtractError):
            extract.extract(self.zipped("a.pptx", {"ppt/x.xml": "<x/>"}))

    def test_a_file_that_is_not_a_zip_raises(self):
        path = self.root / "a.docx"
        path.write_bytes(b"definitely not a zip")
        with self.assertRaises(extract.ExtractError) as ctx:
            extract.extract(path)
        self.assertIn("not a readable Office file", str(ctx.exception))

    def test_malformed_xml_inside_a_valid_zip_raises(self):
        path = self.zipped("a.docx", {"word/document.xml": "<w:document"})
        with self.assertRaises(extract.ExtractError) as ctx:
            extract.extract(path)
        self.assertIn("malformed XML", str(ctx.exception))

    def test_an_oversized_declared_archive_is_refused(self):
        path = self.zipped("a.docx", {"word/document.xml": "<x/>"})
        # Rewrite the central directory to claim an absurd uncompressed size,
        # which is how a zip bomb presents before anything is decompressed.
        original = extract.MAX_ARCHIVE_BYTES
        try:
            extract.MAX_ARCHIVE_BYTES = 1
            with self.assertRaises(extract.ExtractError) as ctx:
                extract.extract(path)
            self.assertIn("over the", str(ctx.exception))
        finally:
            extract.MAX_ARCHIVE_BYTES = original


if __name__ == "__main__":
    unittest.main()
