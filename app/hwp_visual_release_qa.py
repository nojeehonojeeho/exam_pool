"""Fail-closed full-page visual QA contract."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any



def validate_visual_report(report: Mapping[str, Any]) -> dict[str, Any]:
    """Require every expected page to be checked with no visual findings."""

    expected = int(report.get("expected_pages", 0) or 0)
    checked = int(report.get("checked_pages", 0) or 0)
    findings = list(report.get("findings") or [])
    page_results = report.get("pages")
    if expected < 1:
        findings.append({"code": "VISUAL_EXPECTED_PAGE_COUNT_MISSING", "blocking": True})
    if checked != expected:
        findings.append({"code": "VISUAL_NOT_ALL_PAGES_CHECKED", "expected": expected, "actual": checked, "blocking": True})
    if not isinstance(page_results, Sequence) or isinstance(page_results, (str, bytes)):
        findings.append({"code": "VISUAL_PAGE_EVIDENCE_MISSING", "blocking": True})
    else:
        pages = list(page_results)
        if len(pages) != expected:
            findings.append({"code": "VISUAL_PAGE_LIST_COUNT_MISMATCH", "expected": expected, "actual": len(pages), "blocking": True})
        page_numbers: list[int] = []
        for page in pages:
            if not isinstance(page, Mapping):
                findings.append({"code": "VISUAL_PAGE_RECORD_INVALID", "blocking": True})
                continue
            raw_number = page.get("page", page.get("page_number"))
            try:
                number = int(raw_number)
            except (TypeError, ValueError):
                number = 0
            page_numbers.append(number)
            if number < 1 or number > expected:
                findings.append({"code": "VISUAL_PAGE_NUMBER_INVALID", "page": raw_number, "blocking": True})
            if not page.get("render_sha256") and not page.get("sha256"):
                findings.append({"code": "VISUAL_RENDER_HASH_MISSING", "page": number, "blocking": True})
            for key in ("width_px", "height_px", "dpi"):
                value = page.get(key)
                if not isinstance(value, (int, float)) or value <= 0:
                    findings.append({"code": "VISUAL_RENDER_METADATA_MISSING", "page": number, "field": key, "blocking": True})
            if page.get("manual_review_completed") is not True:
                findings.append({"code": "VISUAL_MANUAL_REVIEW_INCOMPLETE", "page": number, "blocking": True})
            if page.get("findings"):
                findings.extend(page["findings"])
        if len(page_numbers) != len(set(page_numbers)):
            findings.append({"code": "VISUAL_PAGE_DUPLICATE", "pages": page_numbers, "blocking": True})
        if set(page_numbers) != set(range(1, expected + 1)):
            findings.append({"code": "VISUAL_PAGE_COVERAGE_MISMATCH", "expected": list(range(1, expected + 1)), "actual": page_numbers, "blocking": True})
    return {"status": "PASS" if not findings else "FAIL", "expected_pages": expected, "checked_pages": checked, "findings": findings}


__all__ = ["validate_visual_report"]
