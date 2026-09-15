"""PDF leaf-object helpers for fail-closed teacher-release evidence.

The worksheet layout cannot be measured from blank paragraphs or a PDF text
block that happened to contain two questions.  These helpers use explicit
question markers plus PDF word/drawing/image leaves.  They are deliberately
small and format-agnostic so the command-line evidence collector can use them
for a new book without importing a prior book's page numbers or item count.
"""
from __future__ import annotations

import re


MARKER = re.compile(r"^(\d+)\.$")


def canonical_font(value: str) -> str:
    """Normalize an HWPX/PDF font name without treating any name as proof.

    Hanword PDFs prefix embedded fonts (for example ``INPILL+``), while HWPX
    uses the Windows face name.  Korean-name encodings vary by reader, so the
    stable ASCII stem is intentionally used only for known release faces.
    """
    text = (value or "").split("+")[-1].replace(" ", "").lower()
    if "kopubworld" in text:
        return "KoPubWorldDotumMedium"
    if "태백" in value:
        return "HYtbrB"
    if "울릉도" in value:
        return "HYwulM"
    for stem, canonical in (
        ("hyhwpeqn", "HyhwpEQ"),
        ("hyhwp", "HyhwpEQ"),
        ("hytbr", "HYtbrB"),
        ("hywul", "HYwulM"),
        ("hcrbatang", "HCRBatang"),
        ("haansoftbatang", "Haansoft Batang"),
    ):
        if stem in text:
            return canonical
    return value or "UNKNOWN"


def column_for(x0: float, page_width: float) -> int:
    return 0 if x0 < page_width / 2 else 1


def flow_key(page: int, column: int, y0: float, x0: float) -> tuple[int, int, float, float]:
    return (page, column, round(float(y0), 3), round(float(x0), 3))


def ordered_markers(page_words: list[list[dict]], expected_numbers: list[int]) -> list[dict]:
    """Locate the native printed ``N.`` markers in reading flow order.

    ``x0 < 450`` excludes decimal-like labels at the far right of a question
    while retaining both B4 columns (question starts are near 42pt/375pt).
    The caller supplies the known source-owned order, not a file-name count.
    """
    candidates: list[dict] = []
    for page, words in enumerate(page_words, 1):
        for word in words:
            match = MARKER.fullmatch(str(word.get("text", "")).strip())
            if not match or float(word["x0"]) >= 450:
                continue
            row = dict(word)
            row.update(page=page, printed_number=int(match.group(1)))
            row["column"] = column_for(float(row["x0"]), float(row["page_width"]))
            row["flow"] = flow_key(page, row["column"], row["y0"], row["x0"])
            candidates.append(row)
    candidates.sort(key=lambda row: row["flow"])
    selected: list[dict] = []
    minimum = (-1, -1, -1.0, -1.0)
    for number in expected_numbers:
        choices = [row for row in candidates if row["printed_number"] == number and row["flow"] > minimum]
        if not choices:
            raise ValueError(f"QUESTION_MARKER_MISSING:{number}")
        chosen = choices[0]
        selected.append(chosen)
        minimum = chosen["flow"]
    return selected


def _within_question(leaf: dict, start: dict, following: dict | None) -> bool:
    slot = (int(leaf["page"]), int(leaf["column"]))
    first = (int(start["page"]), int(start["column"]))
    if slot < first:
        return False
    # A word on the marker's baseline commonly starts a few points above the
    # marker's own bbox.  It is still owned by the same question.
    if slot == first and float(leaf["y1"]) < float(start["y0"]) - 18.0:
        return False
    if following is None:
        return True
    last = (int(following["page"]), int(following["column"]))
    if slot > last:
        return False
    # The first body run of the *next* question can have a bbox that begins a
    # few points above its printed ``N.`` marker.  It must not be attributed to
    # the preceding question.  Conversely, an earlier question's final leaf
    # ends entirely above that marker baseline in a valid layout.
    if slot == last and float(leaf["y1"]) >= float(following["y0"]) - 3.0:
        return False
    return True


def workspace_rows(
    item_ids: list[str],
    markers: list[dict],
    leaves: list[dict],
    *,
    body_bottom_pt: float,
    minimum_mm: float = 60.0,
    previously_composite_ids: set[str] | None = None,
) -> list[dict]:
    """Measure every question's final semantic object to its local boundary."""
    if len(item_ids) != len(markers):
        raise ValueError("ITEM_MARKER_CARDINALITY")
    composite = previously_composite_ids or set()
    rows = []
    for index, (item_id, marker) in enumerate(zip(item_ids, markers)):
        following = markers[index + 1] if index + 1 < len(markers) else None
        owned = [leaf for leaf in leaves if _within_question(leaf, marker, following)]
        # Do not use the printed question marker itself as its last object.
        owned = [leaf for leaf in owned if not (leaf.get("kind") == "word" and leaf.get("marker") is True)]
        if not owned:
            rows.append({
                "id": item_id, "printed_number": marker["printed_number"],
                "status": "REVIEW_REQUIRED", "reason": "NO_SEMANTIC_LEAF_ENDPOINT",
                "previously_composite_block": item_id in composite,
            })
            continue
        endpoint = max(owned, key=lambda leaf: flow_key(leaf["page"], leaf["column"], leaf["y1"], leaf["x1"]))
        endpoint_slot = (int(endpoint["page"]), int(endpoint["column"]))
        next_slot = None if following is None else (int(following["page"]), int(following["column"]))
        if following is not None and endpoint_slot == next_slot:
            boundary_y = float(following["y0"])
            boundary_kind = "next_question_marker_same_column"
        else:
            boundary_y = float(body_bottom_pt)
            boundary_kind = "physical_column_bottom"
        gap_pt = boundary_y - float(endpoint["y1"])
        gap_mm = gap_pt * 25.4 / 72.0
        status = "PASS" if gap_mm >= minimum_mm else "REVIEW_REQUIRED"
        rows.append({
            "id": item_id,
            "printed_number": marker["printed_number"],
            "start_page": marker["page"],
            "start_column": "left" if marker["column"] == 0 else "right",
            "endpoint_page": endpoint["page"],
            "endpoint_column": "left" if endpoint["column"] == 0 else "right",
            "endpoint_kind": endpoint["kind"],
            "endpoint_source": "PDF_LEAF_OBJECT",
            "endpoint_bbox_pt": [round(float(endpoint[k]), 3) for k in ("x0", "y0", "x1", "y1")],
            "owned_leaf_count": len(owned),
            "boundary_kind": boundary_kind,
            "boundary_y_pt": round(boundary_y, 3),
            "gap_pt": round(gap_pt, 3),
            "gap_mm": round(gap_mm, 3),
            "minimum_mm": minimum_mm,
            "previously_composite_block": item_id in composite,
            "semantic_endpoint_resolved": True,
            "status": status,
        })
    return rows
