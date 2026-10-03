"""Run markers and fallback distribution for Office document translation.

The per-run marker scheme (``[[R0]]text[[/R0]]``) and the proportional
fallback distribution are adapted from the two-pass OpenXML pipeline of
Vncntvx/pptx-translate (MIT license):
https://github.com/Vncntvx/pptx-translate
"""

from __future__ import annotations

import re

_RUN_MARKER_RE = re.compile(r"\[\[/?(?:R\d+|TAB|BR|HL|/HL|FLD)\]\]")


def build_run_marker(index: int, text: str) -> str:
    return f"[[R{index}]]{text}[[/R{index}]]"


def build_marked_text(
    run_texts: list[str],
    tokens: list[tuple[int, str]] | None = None,
) -> str:
    """Join run texts with run markers, interleaving protected tokens.

    ``tokens`` contains ``(run_position, token)`` pairs where
    ``run_position`` is the number of runs that appear before the token.
    """
    if not tokens:
        if len(run_texts) <= 1:
            return "".join(run_texts)
        return "".join(build_run_marker(i, text) for i, text in enumerate(run_texts))

    parts: list[str] = []
    cursor = 0
    single = len(run_texts) == 1
    for position, token in tokens:
        while cursor < position:
            parts.append(
                run_texts[cursor]
                if single
                else build_run_marker(cursor, run_texts[cursor])
            )
            cursor += 1
        parts.append(token)
    while cursor < len(run_texts):
        parts.append(
            run_texts[cursor] if single else build_run_marker(cursor, run_texts[cursor])
        )
        cursor += 1
    return "".join(parts)


def strip_markers(text: str) -> str:
    return _RUN_MARKER_RE.sub("", text)


def parse_marked_text(text: str, run_count: int) -> list[str] | None:
    """Split translated text back into per-run fragments.

    Tolerates mildly malformed markers (``[R0]`` / ``[/R0]``) because small
    local models occasionally drop a bracket, but returns ``None`` when
    markers are missing or out of order so the caller can fall back to
    proportional distribution.
    """
    if run_count <= 0:
        return None
    if run_count == 1:
        return [strip_markers(text)]
    results: list[str] = []
    cursor = 0
    for i in range(run_count):
        open_match = re.compile(r"\[\[?R%d\]\]?" % i).search(text, cursor)
        if open_match is None:
            return None
        close_match = re.compile(r"\[\[?/R%d\]\]?" % i).search(text, open_match.end())
        if close_match is None:
            return None
        results.append(text[open_match.end() : close_match.start()])
        cursor = close_match.end()
    return results


def distribute_text_to_runs(source_texts: list[str], text: str) -> list[str]:
    """Split ``text`` across runs proportionally to their source lengths."""
    count = len(source_texts)
    if count == 0:
        return []
    if count == 1:
        return [text]

    weights = [max(len(source), 1) for source in source_texts]
    total_weight = sum(weights)
    text_length = len(text)
    lengths = [(text_length * weight) // total_weight for weight in weights]
    assigned = sum(lengths)

    if assigned < text_length:
        fractions = sorted(
            (
                (text_length * weight) / total_weight - lengths[i],
                i,
            )
            for i, weight in enumerate(weights)
        )
        fractions.reverse()
        for k in range(text_length - assigned):
            lengths[fractions[k][1]] += 1

    fragments: list[str] = []
    cursor = 0
    for length in lengths:
        fragments.append(text[cursor : cursor + length])
        cursor += length
    if cursor < text_length:
        fragments[-1] += text[cursor:]
    return fragments
