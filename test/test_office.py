"""Tests for Office document translation (docx/xlsx/pptx)."""

import io
import tempfile
import unittest
import zipfile
from pathlib import Path

from pdf2zh.office.docx_io import extract_units as extract_docx_units
from pdf2zh.office.markers import (
    build_marked_text,
    distribute_text_to_runs,
    parse_marked_text,
    strip_markers,
)
from pdf2zh.office.ooxml import OoxmlPackage
from pdf2zh.office.pptx_io import extract_units as extract_pptx_units
from pdf2zh.office.service import translate_office_file
from pdf2zh.office.xlsx_io import extract_units as extract_xlsx_units

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
S_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"

CONTENT_TYPES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    "</Types>"
)

RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"/>'
)


class UpperTranslator:
    """Fake translator that preserves run markers."""

    name = "fake-upper"

    def translate(self, text: str) -> str:
        return text.upper()


class MarkerDroppingTranslator:
    """Fake translator that drops run markers (fallback path)."""

    name = "fake-drop"

    def translate(self, text: str) -> str:
        return strip_markers(text).upper()


def _docx_bytes(document_xml: str, extra_parts: dict | None = None) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", CONTENT_TYPES)
        archive.writestr("_rels/.rels", RELS)
        archive.writestr("word/document.xml", document_xml)
        for name, payload in (extra_parts or {}).items():
            archive.writestr(name, payload)
    return buffer.getvalue()


def _pptx_bytes(slide_xml: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", CONTENT_TYPES)
        archive.writestr("_rels/.rels", RELS)
        archive.writestr("ppt/slides/slide1.xml", slide_xml)
    return buffer.getvalue()


def _xlsx_bytes(shared_strings: str, sheet_xml: str | None = None) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", CONTENT_TYPES)
        archive.writestr("_rels/.rels", RELS)
        archive.writestr("xl/sharedStrings.xml", shared_strings)
        if sheet_xml is not None:
            archive.writestr("xl/worksheets/sheet1.xml", sheet_xml)
    return buffer.getvalue()


class TestMarkers(unittest.TestCase):
    def test_build_and_parse_roundtrip(self):
        marked = build_marked_text(["Hello ", "world"])
        self.assertEqual(marked, "[[R0]]Hello [[/R0]][[R1]]world[[/R1]]")
        self.assertEqual(parse_marked_text(marked, 2), ["Hello ", "world"])

    def test_parse_returns_none_when_markers_lost(self):
        self.assertIsNone(parse_marked_text("Hello world", 2))

    def test_parse_returns_none_when_reordered(self):
        marked = "[[R1]]world[[/R1]][[R0]]Hello[[/R0]]"
        self.assertIsNone(parse_marked_text(marked, 2))

    def test_strip_markers(self):
        self.assertEqual(
            strip_markers("[[R0]]Hello [[/R0]][[R1]]world[[/R1]]"), "Hello world"
        )

    def test_distribute_text_to_runs(self):
        fragments = distribute_text_to_runs(["aaaa", "bb"], "Hello world!")
        self.assertEqual("".join(fragments), "Hello world!")
        self.assertTrue(any(fragments))

    def test_distribute_empty_source(self):
        fragments = distribute_text_to_runs(["", ""], "abcd")
        self.assertEqual("".join(fragments), "abcd")


class TestDocx(unittest.TestCase):
    def test_marker_remnants_cleaned(self):
        from lxml import etree

        from pdf2zh.office.model import RunSlot, TextUnit

        first = etree.Element("t")
        second = etree.Element("t")
        unit = TextUnit(id="u", part="p", runs=[RunSlot([first]), RunSlot([second])])
        unit.apply_translation("[[R0]] Xin [[/R0]][[R1]] chào[/R1]")
        self.assertEqual(first.text, " Xin ")
        self.assertEqual(second.text, " chào")

    def test_extract_paragraphs_tables_textboxes(self):
        document = (
            f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f'<w:document xmlns:w="{W_NS}"><w:body>'
            f"<w:p><w:r><w:t>Hello </w:t></w:r>"
            f'<w:r><w:t xml:space="preserve">world</w:t></w:r></w:p>'
            f"<w:tbl><w:tr><w:tc><w:p><w:r><w:t>Cell text</w:t></w:r></w:p></w:tc></w:tr></w:tbl>"
            f"<w:p><w:r><w:drawing><w:txbxContent>"
            f"<w:p><w:r><w:t>Textbox text</w:t></w:r></w:p>"
            f"</w:txbxContent></w:drawing></w:r></w:p>"
            f"</w:body></w:document>"
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sample.docx"
            path.write_bytes(_docx_bytes(document))
            package = OoxmlPackage.load(path)
            units = extract_docx_units(package)
        self.assertEqual(len(units), 3)
        self.assertEqual(units[0].marked_text, "[[R0]]Hello [[/R0]][[R1]]world[[/R1]]")
        self.assertEqual(units[1].source_text, "Cell text")
        self.assertEqual(units[2].source_text, "Textbox text")

    def test_translate_roundtrip_preserves_runs(self):
        document = (
            f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f'<w:document xmlns:w="{W_NS}"><w:body>'
            f"<w:p><w:r><w:t>Hello </w:t></w:r>"
            f'<w:r><w:t xml:space="preserve">world</w:t></w:r></w:p>'
            f"</w:body></w:document>"
        )
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "sample.docx"
            source.write_bytes(_docx_bytes(document))
            output = translate_office_file(
                source,
                lang_in="en",
                lang_out="vi",
                service="google",
                output=tmp,
                translator=UpperTranslator(),
            )
            package = OoxmlPackage.load(output)
            units = extract_docx_units(package)
        self.assertEqual(len(units), 1)
        self.assertEqual(units[0].runs[0].text, "HELLO ")
        self.assertEqual(units[0].runs[1].text, "WORLD")

    def test_fallback_distribution_keeps_all_text(self):
        document = (
            f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f'<w:document xmlns:w="{W_NS}"><w:body>'
            f"<w:p><w:r><w:t>Hello </w:t></w:r>"
            f'<w:r><w:t xml:space="preserve">world</w:t></w:r></w:p>'
            f"</w:body></w:document>"
        )
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "sample.docx"
            source.write_bytes(_docx_bytes(document))
            output = translate_office_file(
                source,
                lang_in="en",
                lang_out="vi",
                service="google",
                output=tmp,
                translator=MarkerDroppingTranslator(),
            )
            package = OoxmlPackage.load(output)
            units = extract_docx_units(package)
        self.assertEqual(units[0].source_text, "HELLO WORLD")

    def test_tab_token_survives_and_formula_not_touched(self):
        document = (
            f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f'<w:document xmlns:w="{W_NS}"><w:body>'
            f"<w:p><w:r><w:t>Before</w:t><w:tab/></w:r>"
            f"<w:r><w:t>After</w:t></w:r></w:p>"
            f"</w:body></w:document>"
        )
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "sample.docx"
            source.write_bytes(_docx_bytes(document))
            package = OoxmlPackage.load(source)
            units = extract_docx_units(package)
            self.assertIn("[[TAB]]", units[0].marked_text)
            self.assertEqual(units[0].runs[0].text, "Before")
            self.assertEqual(units[0].runs[1].text, "After")

    def test_untouched_parts_are_byte_identical(self):
        document = (
            f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f'<w:document xmlns:w="{W_NS}"><w:body>'
            f"<w:p><w:r><w:t>Hello</w:t></w:r></w:p>"
            f"</w:body></w:document>"
        )
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "sample.docx"
            source.write_bytes(_docx_bytes(document))
            output = translate_office_file(
                source,
                lang_in="en",
                lang_out="vi",
                service="google",
                output=tmp,
                translator=UpperTranslator(),
            )
            with (
                zipfile.ZipFile(source) as original,
                zipfile.ZipFile(output) as translated,
            ):
                self.assertEqual(
                    original.read("_rels/.rels"),
                    translated.read("_rels/.rels"),
                )
                self.assertEqual(
                    original.read("[Content_Types].xml"),
                    translated.read("[Content_Types].xml"),
                )


class TestXlsx(unittest.TestCase):
    def test_shared_strings_and_inline(self):
        shared = (
            f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f'<sst xmlns="{S_NS}">'
            f"<si><t>Simple</t></si>"
            f"<si><r><t>Rich </t></r><r><t>text</t></r></si>"
            f"</sst>"
        )
        sheet = (
            f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f'<worksheet xmlns="{S_NS}"><sheetData>'
            f'<row r="1"><c r="A1" t="inlineStr"><is><t>Inline text</t></is></c></row>'
            f'<row r="2"><c r="A2"><f>SUM(B1:B2)</f><v>3</v></c></row>'
            f"</sheetData></worksheet>"
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sample.xlsx"
            path.write_bytes(_xlsx_bytes(shared, sheet))
            package = OoxmlPackage.load(path)
            units = extract_xlsx_units(package)
        texts = [unit.source_text for unit in units]
        self.assertIn("Simple", texts)
        self.assertIn("Rich text", texts)
        self.assertIn("Inline text", texts)
        self.assertNotIn("SUM(B1:B2)", texts)

    def test_translate_shared_strings(self):
        shared = (
            f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f'<sst xmlns="{S_NS}">'
            f"<si><t>Simple</t></si>"
            f"<si><r><t>Rich </t></r><r><t>text</t></r></si>"
            f"</sst>"
        )
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "sample.xlsx"
            source.write_bytes(_xlsx_bytes(shared))
            output = translate_office_file(
                source,
                lang_in="en",
                lang_out="vi",
                service="google",
                output=tmp,
                translator=UpperTranslator(),
            )
            package = OoxmlPackage.load(output)
            units = extract_xlsx_units(package)
        self.assertEqual(units[0].source_text, "SIMPLE")
        self.assertEqual(units[1].runs[0].text, "RICH ")
        self.assertEqual(units[1].runs[1].text, "TEXT")


class TestPptx(unittest.TestCase):
    def test_slide_paragraphs(self):
        slide = (
            f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f'<p:sld xmlns:p="{P_NS}" xmlns:a="{A_NS}">'
            f"<p:cSld><p:spTree><p:sp><p:txBody>"
            f"<a:p><a:r><a:t>Title text</a:t></a:r></a:p>"
            f"<a:p><a:r><a:t>Bold</a:t></a:r><a:r><a:t> normal</a:t></a:r></a:p>"
            f"</p:txBody></p:sp></p:spTree></p:cSld></p:sld>"
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sample.pptx"
            path.write_bytes(_pptx_bytes(slide))
            package = OoxmlPackage.load(path)
            units = extract_pptx_units(package)
        self.assertEqual(len(units), 2)
        self.assertEqual(units[0].source_text, "Title text")
        self.assertEqual(units[1].marked_text, "[[R0]]Bold[[/R0]][[R1]] normal[[/R1]]")

    def test_translate_slide(self):
        slide = (
            f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f'<p:sld xmlns:p="{P_NS}" xmlns:a="{A_NS}">'
            f"<p:cSld><p:spTree><p:sp><p:txBody>"
            f"<a:p><a:r><a:t>Title</a:t></a:r></a:p>"
            f"<a:p><a:r><a:t>Bold</a:t></a:r><a:r><a:t> normal</a:t></a:r></a:p>"
            f"</p:txBody></p:sp></p:spTree></p:cSld></p:sld>"
        )
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "sample.pptx"
            source.write_bytes(_pptx_bytes(slide))
            output = translate_office_file(
                source,
                lang_in="en",
                lang_out="vi",
                service="google",
                output=tmp,
                translator=UpperTranslator(),
            )
            package = OoxmlPackage.load(output)
            units = extract_pptx_units(package)
        self.assertEqual(units[0].source_text, "TITLE")
        self.assertEqual(units[1].source_text, "BOLD NORMAL")


if __name__ == "__main__":
    unittest.main()
