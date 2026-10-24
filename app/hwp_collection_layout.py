"""Pure geometry triage; never imports COM or changes document content."""
from __future__ import annotations
import re


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
