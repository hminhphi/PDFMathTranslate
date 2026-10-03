"""XLSX (SpreadsheetML) extraction and write-back.

Covers the shared string table, inline cell strings, drawing text boxes
and chart titles. Formula cells (``f``) and cached formula results
(``v``) are intentionally never touched.
"""

from __future__ import annotations

import re

from lxml import etree

from pdf2zh.office.markers import build_marked_text
from pdf2zh.office.model import RunSlot, TextUnit
from pdf2zh.office.ooxml import OoxmlPackage
from pdf2zh.office.pptx_io import extract_drawing_paragraphs

S_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
S = f"{{{S_NS}}}"

S_SI = f"{S}si"
S_IS = f"{S}is"
S_T = f"{S}t"
S_RPH = f"{S}rPh"

_SHARED_STRINGS_RE = re.compile(r"^xl/sharedStrings\.xml$")
_WORKSHEET_RE = re.compile(r"^xl/worksheets/sheet\d+\.xml$")
_DRAWING_RE = re.compile(r"^xl/(drawings/drawing\d+\.xml|charts/chart\d+\.xml)$")


def is_xlsx_part(name: str) -> bool:
    return (
        _SHARED_STRINGS_RE.match(name) is not None
        or _WORKSHEET_RE.match(name) is not None
        or _DRAWING_RE.match(name) is not None
    )


def extract_units(package: OoxmlPackage) -> list[TextUnit]:
    units: list[TextUnit] = []
    for part in package.part_names:
        if _SHARED_STRINGS_RE.match(part):
            root = package.xml(part)
            for index, item in enumerate(root.iter(S_SI)):
                unit = _string_unit(item, part, index)
                if unit is not None:
                    units.append(unit)
        elif _WORKSHEET_RE.match(part):
            root = package.xml(part)
            for index, item in enumerate(root.iter(S_IS)):
                unit = _string_unit(item, part, index)
                if unit is not None:
                    units.append(unit)
        elif _DRAWING_RE.match(part):
            root = package.xml(part)
            units.extend(extract_drawing_paragraphs(root, part))
    return units


def _string_unit(item: etree._Element, part: str, index: int) -> TextUnit | None:
    nodes: list[etree._Element] = []

    def visit(element: etree._Element) -> None:
        for child in element:
            if not isinstance(child.tag, str):
                continue
            if child.tag == S_RPH:
                continue
            if child.tag == S_T:
                nodes.append(child)
            else:
                visit(child)

    visit(item)
    if not nodes:
        return None
    runs = [RunSlot(nodes=[node]) for node in nodes]
    marked = build_marked_text([run.text for run in runs])
    return TextUnit(
        id=f"{part}#s{index}",
        part=part,
        runs=runs,
        marked=marked,
    )
