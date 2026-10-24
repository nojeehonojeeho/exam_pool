"""Pure geometry triage; never imports COM or changes document content."""
from __future__ import annotations
import re


def compensate_paragraph_border_offset(border: dict, right_margin_delta: int) -> dict:
    """Preserve an outside paragraph-frame edge for a declared margin change.

    Native rendered vector coordinates still require verification. In particular,
    ignoreMargin=1 alone is not proof that Hanword keeps the outer edge fixed.
    """
    if not isinstance(right_margin_delta, int) or "offsetRight" not in border:
        raise ValueError("Explicit integer margin delta and border offset required")
    result = dict(border)
    result["offsetRight"] = str(int(border["offsetRight"]) + right_margin_delta)
    return result


def isolated_final_korean_span_indices(spans: list[dict], left_limit: float = 80) -> list[int]:
    """Find a left-aligned final syllable without same-row text/math neighbors.

    This is only a physical candidate detector. A caller must additionally bind
    the exact document text order and paragraph ending before applying a repair.
    Separate PDF extraction lines are not necessarily separate physical rows.
    """
    result = []
    for index, span in enumerate(spans):
        if "KoPub" not in span["font"] or not re.fullmatch(r"\s*[가-힣][.!?。]\s*", span["text"]):
            continue
        box = span["bbox"]
        if box[0] >= left_limit:
            continue
        center = (box[1] + box[3]) / 2
        neighbors = [other for other_index, other in enumerate(spans)
                     if other_index != index and other["text"].strip()
                     and (other["bbox"][0] > box[2] + .5 or other["bbox"][2] < box[0] - .5)
                     and other["bbox"][1] - 1 <= center <= other["bbox"][3] + 1]
        if not neighbors:
            result.append(index)
    return result
