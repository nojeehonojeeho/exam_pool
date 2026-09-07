from __future__ import annotations

import json
import sys
from pathlib import Path


WORK = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WORK))

from build_math_up_source_region_queue import build  # noqa: E402


def _item(item_id: str, *, reviewed: bool, formulas: int = 0) -> dict:
    formula_records = [
        {
            "source_region_status": "UNMAPPED_NO_BBOX_IN_REVIEWED_MANIFEST",
            "source_pdf_verified": False,
        }
        for _ in range(formulas)
    ]
    return {
        "item_id": item_id,
        "inventory_natural_position": 1,
        "chapter": 1,
        "section": "synthetic",
        "subsection": "A",
        "source_pdf_page": 11,
        "column": "left",
        "first_sentence": "문항",
        "source_region_v2": {
            "review_status": "REVIEWED_SCOPE_SOURCE_REGION_UNMAPPED" if reviewed else "UNREVIEWED_FULL_BOOK_ITEM",
            "item_frame": {"bbox_status": "ESTIMATED_FROM_TWO_COLUMN_LAYOUT", "source_pdf_page": 11},
            "typed_content": {
                "typed_content_status": "REVIEWED_CONTENT_PRESENT_BUT_SOURCE_REGIONS_UNMAPPED",
                "formula_occurrences": formula_records,
            },
            "solution_source": {
                "solution_boundary_status": "CHAPTER_RANGE_ONLY_UNVERIFIED",
                "solution_pdf_page_range_draft": [4, 12],
                "source_pdf_verified": False,
            },
        },
        "v2_content_summary": {"formula_occurrence_count": formulas, "special_block_count": 1},
    }


def test_queue_is_conservative_and_page_batched(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"items": [_item("A", reviewed=True, formulas=2), _item("B", reviewed=False)]}), encoding="utf-8")
    payload = build(manifest, tmp_path / "out")

    assert payload["counts"]["scope_item_count"] == 2
    assert payload["counts"]["reviewed_scope_item_count"] == 1
    assert payload["counts"]["full_book_item_count"] == 1
    assert payload["counts"]["formula_occurrences_observed"] == 2
    assert payload["counts"]["formula_occurrences_unmapped"] == 2
    assert payload["counts"]["release_eligible_item_count"] == 0
    assert set(payload["page_batches"]) == {"11"}
    assert all(row["release_eligible"] is False for row in payload["priority_queue"])
    assert payload["priority_queue"][0]["phase"] == "P0_FULL_ITEM_REVIEW"


def test_queue_does_not_promote_exact_looking_frame_without_solution_and_content(tmp_path: Path) -> None:
    item = _item("A", reviewed=True)
    item["source_region_v2"]["item_frame"]["bbox_status"] = "EXACT_HUMAN_VERIFIED"
    item["source_region_v2"]["solution_source"]["solution_boundary_status"] = "EXACT_ITEM_LEVEL"
    item["source_region_v2"]["solution_source"]["source_pdf_verified"] = True
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"items": [item]}), encoding="utf-8")
    payload = build(manifest, tmp_path / "out")
    row = payload["priority_queue"][0]

    assert row["frame_status"] == "EXACT_HUMAN_VERIFIED"
    assert row["solution_boundary_status"] == "EXACT_ITEM_LEVEL"
    assert "typed_block_region_ownership_and_reading_order" in row["required_evidence"]
    assert row["release_eligible"] is False
