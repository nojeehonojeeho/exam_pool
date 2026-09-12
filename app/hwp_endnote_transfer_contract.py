"""Pure validation rules for an owned native-endnote copy/move probe.

The COM driver lives in :mod:`tools.hwp_native_endnote_transfer_probe`.  Keeping
the post-save assertions here makes the important rule independently testable:
copying one question must add one *matching native endnote*, not double every
equation in the whole book.
"""
from __future__ import annotations

from collections import Counter
import re
import json
from typing import Any, Iterable, Sequence


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _equation_count(value: Any) -> int:
    """Count native-equation records in a HWPX content snapshot fragment."""
    if isinstance(value, dict):
        return (1 if value.get("type") == "equation" else 0) + sum(
            _equation_count(child) for child in value.values()
        )
    if isinstance(value, list):
        return sum(_equation_count(child) for child in value)
    return 0


def _normalise_text(value: Any) -> str:
    """Normalise only transport whitespace for a bounded text fingerprint."""
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _text_tokens(value: Any) -> list[str]:
    """Return stable visible-text tokens for a COM/HWPX encoding fallback.

    HWP's ``UNICODE`` block export and the later HWPX snapshot can differ in
    control characters or paragraph separators even when the visible question
    is unchanged.  Token coverage is used only after the exact fingerprint
    check and still requires the original main story to remain a prefix.
    """
    return re.findall(r"[0-9A-Za-z가-힣]+", _normalise_text(value))


def _body_sequence(notes: Sequence[dict[str, Any]]) -> list[str]:
    """Return the ordered, canonical native-endnote body sequence."""
    return [_canonical(note.get("content", [])) for note in notes]


def expected_endnote_body_sequence(
    baseline_notes: Sequence[dict[str, Any]], *, mode: str, note_index: int
) -> list[str]:
    """Return the exact body order expected after one bounded transfer.

    A copy appends one native note for the copied question.  A move changes
    the question's location but does not create or delete a native endnote;
    its ordered note-body sequence therefore remains unchanged.  Comparing
    this sequence, rather than a ``Counter``, catches swapped or duplicated
    note bodies with the same aggregate counts.
    """
    if mode not in {"copy", "move"}:
        raise ValueError(f"unsupported transfer mode: {mode}")
    if not 0 <= note_index < len(baseline_notes):
        raise ValueError("note_index is outside the baseline native-endnote range")
    expected = _body_sequence(baseline_notes)
    if mode == "copy":
        expected.append(expected[note_index])
    return expected


def validate_endnote_placement_values(
    declarations: Iterable[Sequence[str | None]], *, native_endnotes_present: bool
) -> bool:
    """Validate each native-endnote placement declaration fail-closed.

    A missing ``endNotePr`` is not silently accepted when notes exist.  Each
    declaration must contain exactly one explicit ``placement`` child, and
    every value must be the trimmed literal ``END_OF_DOCUMENT``.  This also
    rejects a second declaration with a missing or ambiguous placement.  A
    document with no native notes has no placement requirement.
    """
    sections = [list(section) for section in declarations]
    if not native_endnotes_present:
        return True
    if not sections:
        return False
    return all(
        len(section) == 1
        and isinstance(section[0], str)
        and section[0].strip() == "END_OF_DOCUMENT"
        for section in sections
    )


def validate_endnote_transfer(
    baseline: dict[str, Any],
    actual: dict[str, Any],
    *,
    mode: str,
    note_index: int,
    before_equation_count: int,
    after_equation_count: int,
    source_hwp_unchanged: bool,
    source_hwpx_unchanged: bool,
    placement_is_end_of_document: bool,
    selected_question_equation_count: int | None = None,
    baseline_main_text: str | None = None,
    actual_main_text: str | None = None,
    selected_main_text: str | None = None,
    baseline_main_sequence: Sequence[Any] | None = None,
    actual_main_sequence: Sequence[Any] | None = None,
    selected_main_sequence: Sequence[Any] | None = None,
    selected_native_endnote_count: int | None = None,
) -> dict[str, bool]:
    """Validate one real HWP native copy or move operation.

    ``baseline`` and ``actual`` are produced by ``read_hwpx_snapshot``.  The
    selected question can contain a different number of equations from the
    rest of the book; therefore checking ``after == before * 2`` is incorrect
    for a one-question copy and is deliberately not used here.
    """
    if mode not in {"copy", "move"}:
        raise ValueError(f"unsupported transfer mode: {mode}")
    baseline_notes = list(baseline.get("endnotes", []))
    actual_notes = list(actual.get("endnotes", []))
    if not 0 <= note_index < len(baseline_notes):
        raise ValueError("note_index is outside the baseline native-endnote range")

    before_bodies = Counter(_canonical(note.get("content", [])) for note in baseline_notes)
    after_bodies = Counter(_canonical(note.get("content", [])) for note in actual_notes)
    selected_body = _canonical(baseline_notes[note_index].get("content", []))
    selected_equations = _equation_count(baseline_notes[note_index].get("content", []))
    expected_count = len(baseline_notes) + (1 if mode == "copy" else 0)
    expected_bodies = expected_endnote_body_sequence(
        baseline_notes, mode=mode, note_index=note_index
    )
    actual_bodies = _body_sequence(actual_notes)
    selected_question_equation_count = (
        0 if selected_question_equation_count is None else selected_question_equation_count
    )
    if selected_question_equation_count < 0:
        raise ValueError("selected_question_equation_count must be non-negative")
    expected_equation_delta = (
        selected_equations + selected_question_equation_count if mode == "copy" else 0
    )

    if mode == "copy":
        expected_selected_occurrences = before_bodies[selected_body] + 1
        original_bodies_preserved = all(
            after_bodies[body] >= count for body, count in before_bodies.items()
        )
        equation_nonloss = (
            after_equation_count - before_equation_count >= selected_equations
        )
    else:
        expected_selected_occurrences = before_bodies[selected_body]
        original_bodies_preserved = after_bodies == before_bodies
        equation_nonloss = after_equation_count == before_equation_count

    checks = {
        "native_note_count": len(actual_notes) == expected_count,
        "automatic_number_order": [note.get("number") for note in actual_notes]
        == [str(number) for number in range(1, expected_count + 1)],
        "selected_native_endnote_transferred": actual_bodies == expected_bodies,
        "all_original_endnote_bodies_preserved": original_bodies_preserved,
        "selected_endnote_equations_nonloss": equation_nonloss,
        "source_equations_nonloss": after_equation_count - before_equation_count
        == expected_equation_delta,
        "placement_is_end_of_document": placement_is_end_of_document,
        "source_hwp_unchanged": source_hwp_unchanged,
        "source_hwpx_unchanged": source_hwpx_unchanged,
    }
    if selected_native_endnote_count is not None:
        # The COM selection itself must contain exactly one native endnote
        # control. A body-only selection can otherwise make copied-body and
        # equation deltas look correct while proving nothing about the
        # question's reference anchor.
        checks["selected_native_endnote_reference"] = selected_native_endnote_count == 1
    if all(value is not None for value in (baseline_main_text, actual_main_text, selected_main_text)):
        baseline_text = _normalise_text(baseline_main_text)
        actual_text = _normalise_text(actual_main_text)
        selected_text = _normalise_text(selected_main_text)
        # A text fingerprint is a fallback for formats whose HWPX snapshot
        # cannot expose the COM selection boundary.  It still requires the
        # selected question to occur with the expected multiplicity.
        baseline_occurrences = baseline_text.count(selected_text) if selected_text else 0
        actual_occurrences = actual_text.count(selected_text) if selected_text else 0
        expected_occurrences = baseline_occurrences + (1 if mode == "copy" else 0)
        exact_match = bool(
            selected_text
            and baseline_occurrences >= 1
            and actual_occurrences >= expected_occurrences
        )
        # A COM saveblock may expose paragraph/control boundaries differently
        # from the HWPX snapshot.  For a copy, accept this representation-only
        # difference only when the complete original main story is preserved
        # as a prefix and the appended story covers the selected question's
        # visible tokens.  This remains fail-closed for an empty selection or
        # unrelated appended text.
        fallback_match = False
        if mode == "copy" and not exact_match:
            baseline_tokens = _text_tokens(baseline_text)
            actual_tokens = _text_tokens(actual_text)
            selected_tokens = _text_tokens(selected_text)
            prefix_match = actual_text.startswith(baseline_text) and len(actual_text) > len(baseline_text)
            appended_text = actual_text[len(baseline_text) :].strip()
            appended_tokens = _text_tokens(appended_text)
            if selected_tokens and appended_tokens:
                appended_counts = Counter(appended_tokens)
                covered = sum(
                    min(count, appended_counts[token])
                    for token, count in Counter(selected_tokens).items()
                )
                coverage = covered / len(selected_tokens)
                selected_counts = Counter(selected_tokens)
                appended_covered = sum(
                    min(count, selected_counts[token])
                    for token, count in appended_counts.items()
                )
                appended_coverage = appended_covered / len(appended_tokens)
                fallback_match = bool(
                    prefix_match
                    and len(actual_tokens) > len(baseline_tokens)
                    and appended_text in baseline_text
                    and appended_coverage >= 0.95
                )
        checks["main_question_fingerprint_preserved"] = exact_match or fallback_match
    if all(value is not None for value in (baseline_main_sequence, actual_main_sequence, selected_main_sequence)):
        baseline_sequence = [_canonical(value) for value in baseline_main_sequence or []]
        actual_sequence = [_canonical(value) for value in actual_main_sequence or []]
        selected_sequence = [_canonical(value) for value in selected_main_sequence or []]
        expected_sequence = list(baseline_sequence)
        if mode == "copy":
            expected_sequence.extend(selected_sequence)
        else:
            selected_len = len(selected_sequence)
            for start in range(len(expected_sequence) - selected_len + 1):
                if expected_sequence[start : start + selected_len] == selected_sequence:
                    del expected_sequence[start : start + selected_len]
                    break
            expected_sequence.extend(selected_sequence)
        checks["main_question_sequence_preserved"] = actual_sequence == expected_sequence
    return checks
