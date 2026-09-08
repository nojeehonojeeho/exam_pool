"""Reusable semantic paragraph-boundary rules for OCR-to-HWP writers.

OCR detections are physical rows.  This module exposes the deliberately narrow
marker predicate used by writers so a Korean syllable (for example ``나`` at
the start of ``나열하여``) can never be mistaken for a sub-item marker.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any


_KOREAN_SUBITEM = "가나다라마바사아자차카타파하"
_STRUCTURAL_PREFIX = re.compile(
    rf"^(?:[①②③④⑤⑥⑦⑧⑨⑩]|"
    rf"\((?:{'|'.join(_KOREAN_SUBITEM)})\)|"
    rf"(?:{'|'.join(_KOREAN_SUBITEM)})[.)]|\(?[ivxIVX]+[.)]|\[[^\]]{{1,20}}\])"
)
_HEADING_PREFIX = re.compile(r"^(?:정답|해설|풀이|출제영역|출제 영역|채점|[1-9][.]\s*)")


def is_explicit_structural_marker(value: str) -> bool:
    """Return true only for an explicit numbered/labelled block marker."""

    text = str(value or "").strip()
    if not text:
        return True
    if re.fullmatch(r"\d{1,3}[.)]?", text):
        return True
    return bool(_STRUCTURAL_PREFIX.match(text) or _HEADING_PREFIX.match(text)
                or re.match(r"^(?:why\?|NOTE|[※*])", text, re.I))


def merge_physical_rows(rows: Iterable[Mapping[str, Any]], *, text_key: str = "text") -> list[tuple[str, Mapping[str, Any]]]:
    """Merge physical OCR rows into prose blocks without splitting inline math.

    Formula detection remains the writer's responsibility.  A row containing
    Hangul is kept in the prose buffer; its inline equation runs can still be
    emitted natively by the writer.  Explicit markers and formula-only rows
    flush the buffer.  No target count or half-splitting is performed.
    """

    grouped: list[tuple[str, Mapping[str, Any]]] = []
    buffer: list[tuple[str, Mapping[str, Any]]] = []

    def flush() -> None:
        if buffer:
            text = " ".join(str(value).strip() for value, _ in buffer if str(value).strip()).strip()
            if text:
                grouped.append((text, buffer[0][1]))
            buffer.clear()

    for row in rows:
        value = str(row.get(text_key, "") or "").strip()
        if not value:
            continue
        structural = is_explicit_structural_marker(value)
        formula_only = not re.search(r"[가-힣]", value) and bool(re.search(r"(?:[=+\-*/^]|\\[A-Za-z]+|[∑Σ∫√])", value))
        if structural or formula_only:
            flush()
            grouped.append((value, row))
            continue
        buffer.append((value, row))
        if re.search(r"[.!?。？！]$", value):
            flush()
    flush()
    return grouped


__all__ = ["is_explicit_structural_marker", "merge_physical_rows"]
