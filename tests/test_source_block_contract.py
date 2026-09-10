"""Synthetic contracts for source-block reconstruction and bounded promotion."""

from __future__ import annotations


def _merge_text_blocks(blocks: list[dict], merge_ids: list[str]) -> dict:
    selected = [block for block in blocks if block["id"] in merge_ids]
    assert selected and [block["id"] for block in selected] == merge_ids
    return {
        "id": "merged:" + "+".join(merge_ids),
        "rows": [row for block in selected for row in block["rows"]],
        "segments": [segment for block in selected for segment in block["segments"]],
        "source_ids": merge_ids,
    }


def test_condition_rows_merge_without_losing_inline_segments() -> None:
    blocks = [
        {"id": "b1", "rows": ["(가) 첫 번째 조건"], "segments": ["문장", "q/p"]},
        {"id": "b2", "rows": ["(나) 두 번째 조건"], "segments": ["와", "p+q"]},
    ]
    merged = _merge_text_blocks(blocks, ["b1", "b2"])
    assert merged["rows"] == ["(가) 첫 번째 조건", "(나) 두 번째 조건"]
    assert merged["segments"] == ["문장", "q/p", "와", "p+q"]
    assert merged["source_ids"] == ["b1", "b2"]


def test_display_pile_preserves_one_occurrence_and_does_not_invent_label() -> None:
    occurrence = {
        "occurrence_id": "F028",
        "source_script": "p=9,q=4; p+q=9+4=13",
        "display_script": "pile { p=9,q=4 # p+q=9+4=13 }",
        "inferred_label": None,
    }
    assert occurrence["occurrence_id"] == "F028"
    assert occurrence["display_script"].startswith("pile {")
    assert occurrence["inferred_label"] is None


def test_bounded_candidate_is_not_whole_book_final() -> None:
    report = {
        "scope_status": "BOUNDED_CANDIDATE_ONLY",
        "final": False,
        "whole_book_final": False,
        "remaining_gates": ["whole-book source coverage"],
    }
    assert report["scope_status"] == "BOUNDED_CANDIDATE_ONLY"
    assert report["final"] is False
    assert report["whole_book_final"] is False
    assert report["remaining_gates"]
