"""DOCX (WordprocessingML) extraction and write-back.

Covers paragraphs anywhere in the part tree, including tables, content
controls, hyperlinks and drawing text boxes (``w:txbxContent``), plus
headers, footers, footnotes, endnotes and comments.
"""

from __future__ import annotations

import re

from lxml import etree

from pdf2zh.office.markers import build_marked_text
from pdf2zh.office.model import RunSlot, TextUnit
from pdf2zh.office.ooxml import OoxmlPackage

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W = f"{{{W_NS}}}"

W_P = f"{W}p"
W_R = f"{W}r"
W_T = f"{W}t"
W_TAB = f"{W}tab"
W_BR = f"{W}br"
W_CR = f"{W}cr"
W_NO_BREAK_HYPHEN = f"{W}noBreakHyphen"
W_HYPERLINK = f"{W}hyperlink"
W_FLD_SIMPLE = f"{W}fldSimple"
W_SDT_CONTENT = f"{W}sdtContent"
W_SMART_TAG = f"{W}smartTag"
W_INS = f"{W}ins"
W_MOVE_TO = f"{W}moveTo"

_CONTAINER_TAGS = {
    W_HYPERLINK,
    W_SDT_CONTENT,
    W_SMART_TAG,
    W_INS,
    W_MOVE_TO,
}

_SKIP_TAGS = {
    f"{W}instrText",
    f"{W}fldChar",
    f"{W}delText",
    f"{W}del",
    f"{W}moveFrom",
    f"{W}drawing",
    f"{W}object",
    f"{W}pict",
    f"{W}txbxContent",
    f"{W}bookmarkStart",
    f"{W}bookmarkEnd",
    f"{W}commentRangeStart",
    f"{W}commentRangeEnd",
    f"{W}proofErr",
    f"{W}softHyphen",
    f"{W}lastRenderedPageBreak",
}

_PART_RE = re.compile(
    r"^word/(document\.xml"
    r"|header\d*\.xml"
    r"|footer\d*\.xml"
    r"|footnotes\.xml"
    r"|endnotes\.xml"
    r"|comments\.xml)$"
)


def is_docx_part(name: str) -> bool:
    return _PART_RE.match(name) is not None


def extract_units(package: OoxmlPackage) -> list[TextUnit]:
    units: list[TextUnit] = []
    for part in package.part_names:
        if not is_docx_part(part):
            continue
        root = package.xml(part)
        for index, paragraph in enumerate(root.iter(W_P)):
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

    def visit(element: etree._Element) -> None:
        nonlocal token_count
        for child in element:
            if not isinstance(child.tag, str):
                continue
            tag = child.tag
            if tag == W_R:
                nodes = [node for node in child if node.tag == W_T]
                if nodes:
                    runs.append(RunSlot(nodes=nodes))
                for node in child:
                    if node.tag == W_TAB:
                        token_count += 1
                        markers.append((len(runs), "[[TAB]]"))
                    elif node.tag in (W_BR, W_CR):
                        token_count += 1
                        markers.append((len(runs), "[[BR]]"))
                    elif node.tag == W_NO_BREAK_HYPHEN:
                        pass
            elif tag == W_FLD_SIMPLE:
                token_count += 1
                markers.append((len(runs), "[[FLD]]"))
                visit(child)
            elif tag in _CONTAINER_TAGS:
                visit(child)
            elif tag in _SKIP_TAGS:
                continue
            else:
                visit(child)

    visit(paragraph)
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
