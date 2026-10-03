"""Office document translation (DOCX / XLSX / PPTX) preserving formatting.

Pipeline (inspired by Vncntvx/pptx-translate and daodiaonan/sanmu6-public,
both MIT):

1. unzip the OOXML package and extract translatable *runs* per paragraph /
   string item / chart label;
2. join the runs into one text with ``[[R0]]...[[/R0]]`` markers so the
   translator can reorder text while keeping run boundaries;
3. translate through the regular ``pdf2zh.translator`` services (cache
   included);
4. write each translated run back into its original text node, or fall
   back to proportional distribution when markers are lost;
5. re-zip every untouched part byte-for-byte.
"""

from pdf2zh.office.service import (
    OFFICE_EXTENSIONS,
    build_translator,
    is_office_file,
    translate_office_file,
    translate_units,
)

__all__ = [
    "OFFICE_EXTENSIONS",
    "build_translator",
    "is_office_file",
    "translate_office_file",
    "translate_units",
]
