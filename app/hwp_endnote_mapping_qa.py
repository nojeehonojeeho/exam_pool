"""Native endnote linkage checks; counts alone are intentionally insufficient."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any


def validate_endnote_mapping(
    item_ids: Iterable[str],
    references: Iterable[Mapping[str, Any]],
    bodies: Iterable[Mapping[str, Any]],
) -> dict[str, Any]:
    """Validate one-to-one ordered item → reference → body mapping."""

    expected = [str(x) for x in item_ids]
    refs = [dict(x) for x in references]
    notes = [dict(x) for x in bodies]
    findings: list[dict[str, Any]] = []
    ref_ids = [str(x.get("item_id", "")) for x in refs]
    body_ids = [str(x.get("item_id", "")) for x in notes]
    if len(ref_ids) != len(set(ref_ids)):
        findings.append({"code": "ENDNOTE_REFERENCE_DUPLICATE", "blocking": True})
    if len(body_ids) != len(set(body_ids)):
        findings.append({"code": "ENDNOTE_BODY_DUPLICATE", "blocking": True})
    if ref_ids != expected:
        findings.append({"code": "ENDNOTE_REFERENCE_ORDER_OR_SCOPE_MISMATCH", "blocking": True, "expected": expected, "actual": ref_ids})
    if body_ids != expected:
        findings.append({"code": "ENDNOTE_BODY_ORDER_OR_SCOPE_MISMATCH", "blocking": True, "expected": expected, "actual": body_ids})
    for index, (ref, body) in enumerate(zip(refs, notes), 1):
        if ref.get("endnote_number") != body.get("endnote_number"):
            findings.append({"code": "ENDNOTE_NUMBER_MISMATCH", "index": index, "blocking": True})
        if ref.get("body_fingerprint") and ref.get("body_fingerprint") != body.get("body_fingerprint"):
            findings.append({"code": "ENDNOTE_BODY_FINGERPRINT_MISMATCH", "index": index, "blocking": True})
    if len(refs) != len(expected) or len(notes) != len(expected):
        findings.append({"code": "ENDNOTE_COUNT_MISMATCH", "expected": len(expected), "references": len(refs), "bodies": len(notes), "blocking": True})
    ref_numbers = [ref.get("endnote_number") for ref in refs]
    body_numbers = [body.get("endnote_number") for body in notes]
    if any(number in (None, "") for number in ref_numbers + body_numbers):
        findings.append({"code": "ENDNOTE_NUMBER_MISSING", "blocking": True})
    if len(ref_numbers) != len(set(ref_numbers)) or len(body_numbers) != len(set(body_numbers)):
        findings.append({"code": "ENDNOTE_NUMBER_DUPLICATE", "blocking": True})
    for index, (ref, body) in enumerate(zip(refs, notes), 1):
        ref_fp = ref.get("body_fingerprint")
        body_fp = body.get("body_fingerprint")
        if not isinstance(ref_fp, str) or not ref_fp.strip() or not isinstance(body_fp, str) or not body_fp.strip():
            findings.append({"code": "ENDNOTE_BODY_FINGERPRINT_MISSING", "index": index, "blocking": True})
    return {
        "status": "PASS" if not findings else "FAIL",
        "item_count": len(expected),
        "reference_count": len(refs),
        "body_count": len(notes),
        "findings": findings,
    }


__all__ = ["validate_endnote_mapping"]
