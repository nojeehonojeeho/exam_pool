"""Conservative normalization for OCR formula candidates.

OCR sidecars sometimes label every scalar in a table or answer list as an
equation.  A bare numeric token is ordinary text unless source evidence proves
that it is an equation occurrence.  This module keeps that policy reusable and
testable before any HWP writer is called.
"""

from __future__ import annotations

import re
from typing import Any

_BARE_NUMBER = re.compile(r"[-−+]?\d+(?:\.\d+)?\Z")


def demote_standalone_numeric_equations(value: Any) -> Any:
    """Recursively convert bare numeric equation nodes into text nodes.

    Structured expressions (including ``x+1``, fractions, equalities, and
    functions) are left unchanged.  The input is not mutated.
    """

    if isinstance(value, dict):
        if value.get("type") in ("equation", "display_equation"):
            raw = str(
                value.get("source_text_exact")
                or value.get("source_script")
                or value.get("script")
                or ""
            ).strip()
            if _BARE_NUMBER.fullmatch(raw):
                return {"type": "text", "text": raw}
        return {key: demote_standalone_numeric_equations(child) for key, child in value.items()}
    if isinstance(value, list):
        return [demote_standalone_numeric_equations(child) for child in value]
    return value


__all__ = ["demote_standalone_numeric_equations"]
