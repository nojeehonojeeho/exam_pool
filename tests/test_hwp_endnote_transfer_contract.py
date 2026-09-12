from __future__ import annotations

from app.hwp_endnote_transfer_contract import (
    expected_endnote_body_sequence,
    validate_endnote_placement_values,
    validate_endnote_transfer,
)


def _note(number: int, content: list[dict]) -> dict:
    return {"number": str(number), "content": content}


def _baseline() -> dict:
    return {
        "endnotes": [
            _note(1, [{"type": "paragraph", "content": [{"type": "text", "text": "정답 1"}]}]),
            _note(2, [{"type": "paragraph", "content": [{"type": "equation", "script": "x+1"}]}]),
        ]
    }


def test_copy_requires_one_extra_matching_native_body_not_whole_book_formula_doubling() -> None:
    baseline = _baseline()
    actual = {"endnotes": [baseline["endnotes"][0], baseline["endnotes"][1], _note(3, baseline["endnotes"][1]["content"])]}
    checks = validate_endnote_transfer(
        baseline, actual, mode="copy", note_index=1,
        before_equation_count=11, after_equation_count=12,
        source_hwp_unchanged=True, source_hwpx_unchanged=True,
        placement_is_end_of_document=True,
    )
    assert all(checks.values())


def test_move_requires_exact_endnote_body_multiset_and_equation_preservation() -> None:
    baseline = _baseline()
    # A moved question can appear at the end of the main story but its two
    # native endnote bodies must still be exactly the same set.
    actual = {"endnotes": [baseline["endnotes"][0], baseline["endnotes"][1]]}
    checks = validate_endnote_transfer(
        baseline, actual, mode="move", note_index=0,
        before_equation_count=11, after_equation_count=11,
        source_hwp_unchanged=True, source_hwpx_unchanged=True,
        placement_is_end_of_document=True,
    )
    assert all(checks.values())


def test_copy_fails_when_selected_native_endnote_does_not_follow_the_question() -> None:
    baseline = _baseline()
    actual = {"endnotes": [baseline["endnotes"][0], baseline["endnotes"][1], _note(3, baseline["endnotes"][0]["content"])]}
    checks = validate_endnote_transfer(
        baseline, actual, mode="copy", note_index=1,
        before_equation_count=11, after_equation_count=12,
        source_hwp_unchanged=True, source_hwpx_unchanged=True,
        placement_is_end_of_document=True,
    )
    assert checks["selected_native_endnote_transferred"] is False


def test_copy_fails_when_it_only_preserves_total_formula_count() -> None:
    baseline = _baseline()
    actual = {"endnotes": [baseline["endnotes"][0], baseline["endnotes"][1], _note(3, baseline["endnotes"][1]["content"])]}
    checks = validate_endnote_transfer(
        baseline, actual, mode="copy", note_index=1,
        before_equation_count=11, after_equation_count=11,
        source_hwp_unchanged=True, source_hwpx_unchanged=True,
        placement_is_end_of_document=True,
    )
    assert checks["selected_endnote_equations_nonloss"] is False


def test_copy_requires_ordered_endnote_bodies_not_only_a_matching_counter() -> None:
    baseline = _baseline()
    # Both bodies are present, but the first two native notes are swapped.
    actual = {
        "endnotes": [
            baseline["endnotes"][1],
            baseline["endnotes"][0],
            _note(3, baseline["endnotes"][1]["content"]),
        ]
    }
    checks = validate_endnote_transfer(
        baseline, actual, mode="copy", note_index=1,
        before_equation_count=11, after_equation_count=12,
        source_hwp_unchanged=True, source_hwpx_unchanged=True,
        placement_is_end_of_document=True,
    )
    assert checks["all_original_endnote_bodies_preserved"] is True
    assert checks["selected_native_endnote_transferred"] is False
    assert expected_endnote_body_sequence(
        baseline["endnotes"], mode="copy", note_index=1
    ) != [
        # Explicitly document the order-sensitive expectation.
        expected_endnote_body_sequence(
            baseline["endnotes"], mode="copy", note_index=1
        )[1],
        expected_endnote_body_sequence(
            baseline["endnotes"], mode="copy", note_index=1
        )[0],
        expected_endnote_body_sequence(
            baseline["endnotes"], mode="copy", note_index=1
        )[2],
    ]


def test_copy_formula_delta_includes_selected_main_question_formulae() -> None:
    baseline = _baseline()
    actual = {
        "endnotes": [baseline["endnotes"][0], baseline["endnotes"][1],
                     _note(3, baseline["endnotes"][1]["content"])]
    }
    checks = validate_endnote_transfer(
        baseline, actual, mode="copy", note_index=1,
        before_equation_count=11, after_equation_count=15,
        selected_question_equation_count=3,
        source_hwp_unchanged=True, source_hwpx_unchanged=True,
        placement_is_end_of_document=True,
    )
    assert checks["source_equations_nonloss"] is True

    checks = validate_endnote_transfer(
        baseline, actual, mode="copy", note_index=1,
        before_equation_count=11, after_equation_count=14,
        selected_question_equation_count=3,
        source_hwp_unchanged=True, source_hwpx_unchanged=True,
        placement_is_end_of_document=True,
    )
    assert checks["source_equations_nonloss"] is False


def test_main_question_fingerprint_requires_expected_copy_occurrence() -> None:
    baseline = _baseline()
    actual = {"endnotes": [baseline["endnotes"][0], baseline["endnotes"][1],
                            _note(3, baseline["endnotes"][1]["content"])]}
    checks = validate_endnote_transfer(
        baseline, actual, mode="copy", note_index=1,
        before_equation_count=11, after_equation_count=12,
        source_hwp_unchanged=True, source_hwpx_unchanged=True,
        placement_is_end_of_document=True,
        baseline_main_text="문제 1 문제 2",
        actual_main_text="문제 1 문제 2 문제 2",
        selected_main_text="문제 2",
    )
    assert checks["main_question_fingerprint_preserved"] is True

    checks = validate_endnote_transfer(
        baseline, actual, mode="copy", note_index=1,
        before_equation_count=11, after_equation_count=12,
        source_hwp_unchanged=True, source_hwpx_unchanged=True,
        placement_is_end_of_document=True,
        baseline_main_text="문제 1 문제 2",
        actual_main_text="문제 1 문제 2",
        selected_main_text="문제 2",
    )
    assert checks["main_question_fingerprint_preserved"] is False


def test_main_question_fingerprint_accepts_hwp_control_boundary_reencoding() -> None:
    baseline = _baseline()
    actual = {"endnotes": [baseline["endnotes"][0], baseline["endnotes"][1], _note(3, baseline["endnotes"][1]["content"])]}
    checks = validate_endnote_transfer(
        baseline, actual, mode="copy", note_index=1,
        before_equation_count=11, after_equation_count=12,
        source_hwp_unchanged=True, source_hwpx_unchanged=True,
        placement_is_end_of_document=True,
        baseline_main_text="문제 1 문제 2",
        # HWPX snapshot preserves the original story and appends the copied
        # question, while COM saveblock may have different separators.
        actual_main_text="문제 1 문제 2\n문제\u00a02",
        selected_main_text="문제\r\n2",
    )
    assert checks["main_question_fingerprint_preserved"] is True


def test_endnote_placement_validation_is_explicit_and_fail_closed() -> None:
    assert validate_endnote_placement_values(
        [[" END_OF_DOCUMENT "]], native_endnotes_present=True
    ) is True
    assert validate_endnote_placement_values([], native_endnotes_present=True) is False
    assert validate_endnote_placement_values([[]], native_endnotes_present=True) is False
    assert validate_endnote_placement_values(
        [["END_OF_DOCUMENT"], []], native_endnotes_present=True
    ) is False
    assert validate_endnote_placement_values(
        [["END_OF_DOCUMENT"], ["EACH_COLUMN"]], native_endnotes_present=True
    ) is False
    assert validate_endnote_placement_values([], native_endnotes_present=False) is True


def test_copy_requires_selection_to_contain_one_native_reference() -> None:
    baseline = _baseline()
    actual = {
        "endnotes": [
            baseline["endnotes"][0],
            baseline["endnotes"][1],
            _note(3, baseline["endnotes"][1]["content"]),
        ]
    }
    checks = validate_endnote_transfer(
        baseline,
        actual,
        mode="copy",
        note_index=1,
        before_equation_count=11,
        after_equation_count=12,
        source_hwp_unchanged=True,
        source_hwpx_unchanged=True,
        placement_is_end_of_document=True,
        selected_native_endnote_count=0,
    )
    assert checks["selected_native_endnote_reference"] is False
