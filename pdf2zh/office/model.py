"""Shared model for Office document translation units."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from lxml import etree

from pdf2zh.office.markers import (
    build_run_marker,
    distribute_text_to_runs,
    parse_marked_text,
    strip_markers,
)

XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"

_MARKER_REMNANT_RE = re.compile(r"\[\[?/?R\d+\]\]?")


@dataclass
class RunSlot:
    """A group of text nodes that share one run's formatting.

    A Word/PPT run normally owns a single text node, but some producers
    split text across several nodes; all of them are tracked so the
    translation can be written into the first node while the rest are
    cleared, preserving the run properties.
    """

    nodes: list[etree._Element] = field(default_factory=list)

    @property
    def text(self) -> str:
        return "".join(node.text or "" for node in self.nodes)

    def set_text(self, text: str) -> None:
        if not self.nodes:
            return
        first = self.nodes[0]
        first.text = text if text else None
        if text and (text[0].isspace() or text[-1].isspace()):
            first.set(XML_SPACE, "preserve")
        else:
            first.attrib.pop(XML_SPACE, None)
        for node in self.nodes[1:]:
            node.text = None
            node.attrib.pop(XML_SPACE, None)


@dataclass
class TextUnit:
    """One translatable container (paragraph, string item, chart label...)."""

    id: str
    part: str
    runs: list[RunSlot] = field(default_factory=list)
    tokens: list[str] = field(default_factory=list)
    marked: str | None = None

    @property
    def marked_text(self) -> str:
        if self.marked is not None:
            return self.marked
        if len(self.runs) <= 1:
            return "".join(run.text for run in self.runs)
        parts: list[str] = []
        for index, run in enumerate(self.runs):
            parts.append(build_run_marker(index, run.text))
        return "".join(parts)

    @property
    def source_text(self) -> str:
        return "".join(run.text for run in self.runs)

    def apply_translation(self, translated: str) -> bool:
        """Write translated text back into the run text nodes.

        Returns ``True`` when the per-run markers survived the translator
        (formatting mapped exactly), ``False`` when the proportional
        fallback was used.
        """
        if not self.runs:
            return False
        fragments = parse_marked_text(translated, len(self.runs))
        if fragments is None:
            cleaned = strip_markers(translated)
            fragments = distribute_text_to_runs(
                [run.text for run in self.runs], cleaned
            )
            exact = False
        else:
            exact = True
        for run, fragment in zip(self.runs, fragments):
            run.set_text(_MARKER_REMNANT_RE.sub("", fragment))
        return exact
