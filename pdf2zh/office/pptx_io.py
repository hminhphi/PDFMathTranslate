"""PPTX (PresentationML) extraction and write-back.

Covers every ``a:p`` paragraph under slides, notes, charts and diagram
data (DrawingML namespaces are shared with chart parts and Excel
drawings), including grouped shapes and table cells.
"""

from __future__ import annotations

import re

from lxml import etree

from pdf2zh.office.markers import build_marked_text
from pdf2zh.office.model import RunSlot, TextUnit
from pdf2zh.office.ooxml import OoxmlPackage

A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
A = f"{{{A_NS}}}"

A_P = f"{A}p"
A_R = f"{A}r"
A_T = f"{A}t"
A_BR = f"{A}br"
A_FLD = f"{A}fld"

_PPT_PART_RE = re.compile(
    r"^ppt/(slides/slide\d+\.xml"
    r"|notesSlides/notesSlide\d+\.xml"
    r"|charts/chart\d+\.xml"
    r"|diagrams/data\d+\.xml)$"
)


def is_pptx_part(name: str) -> bool:
    return _PPT_PART_RE.match(name) is not None


def extract_units(package: OoxmlPackage) -> list[TextUnit]:
    units: list[TextUnit] = []
    for part in package.part_names:
        if not is_pptx_part(part):
            continue
        root = package.xml(part)
        units.extend(extract_drawing_paragraphs(root, part))
    return units


def extract_drawing_paragraphs(root: etree._Element, part: str) -> list[TextUnit]:
    """Extract units from all ``a:p`` paragraphs inside an XML root."""
    units: list[TextUnit] = []
    for index, paragraph in enumerate(root.iter(A_P)):
        if not isinstance(paragraph.tag, str):
            continue
        unit = _paragraph_unit(paragraph, part, index)
        if unit is not None and unit.runs:
            units.append(unit)
    return units


def _paragraph_unit(
    paragraph: etree._Element, part: str, index: int
) -> TextUnit | None:
    runs: list[RunSlot] = []
    markers: list[tuple[int, str]] = []
    token_count = 0

    for child in paragraph:
        if not isinstance(child.tag, str):
            continue
        if child.tag == A_R:
            nodes = [node for node in child if node.tag == A_T]
            if nodes:
                runs.append(RunSlot(nodes=nodes))
        elif child.tag == A_BR:
            token_count += 1
            markers.append((len(runs), "[[BR]]"))
        elif child.tag == A_FLD:
            continue

    if not runs:
        return None

    marked = build_marked_text(
        [run.text for run in runs],
        markers if token_count else None,
    )
    return TextUnit(
        id=f"{part}#p{index}",
        part=part,
        runs=runs,
        marked=marked,
    )
