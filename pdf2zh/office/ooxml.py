"""Minimal OOXML (ZIP + XML) package reader/writer.

Only the parts that changed are re-serialized; every other entry is copied
byte-for-byte so relationships, images, embedded objects and unknown
extensions survive untouched.
"""

from __future__ import annotations

import logging
import zipfile
from pathlib import Path

from lxml import etree

logger = logging.getLogger(__name__)

_PARSER = etree.XMLParser(
    resolve_entities=False,
    huge_tree=True,
    recover=False,
)


class OoxmlPackage:
    def __init__(
        self,
        path: Path,
        data: dict[str, bytes],
        infos: list[zipfile.ZipInfo],
    ) -> None:
        self.path = Path(path)
        self.data = data
        self.infos = infos
        self._roots: dict[str, etree._Element] = {}

    @classmethod
    def load(cls, path: str | Path) -> "OoxmlPackage":
        path = Path(path)
        data: dict[str, bytes] = {}
        with zipfile.ZipFile(path, "r") as archive:
            infos = archive.infolist()
            for info in infos:
                data[info.filename] = archive.read(info.filename)
        return cls(path, data, infos)

    @property
    def part_names(self) -> list[str]:
        return list(self.data.keys())

    def has_part(self, name: str) -> bool:
        return name in self.data

    def xml(self, name: str) -> etree._Element:
        root = self._roots.get(name)
        if root is None:
            try:
                root = etree.fromstring(self.data[name], parser=_PARSER)
            except etree.XMLSyntaxError as exc:
                raise ValueError(f"invalid XML part: {name}") from exc
            self._roots[name] = root
        return root

    def mark_changed(self, name: str) -> None:
        if name not in self._roots:
            self.xml(name)

    def save(self, output_path: str | Path, changed: set[str]) -> Path:
        output_path = Path(output_path)
        if output_path.resolve() == self.path.resolve():
            raise ValueError("output path must differ from the source file")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        serialized = {
            name: etree.tostring(
                self._roots[name],
                xml_declaration=True,
                encoding="UTF-8",
                standalone=True,
            )
            for name in changed
            if name in self._roots
        }
        with zipfile.ZipFile(output_path, "w") as archive:
            for info in self.infos:
                payload = serialized.get(info.filename, self.data[info.filename])
                archive.writestr(info, payload)
        return output_path
