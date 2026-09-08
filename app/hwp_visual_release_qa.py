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
        for page in page_results:
            if isinstance(page, Mapping) and page.get("findings"):
                findings.extend(page["findings"])
    return {"status": "PASS" if not findings else "FAIL", "expected_pages": expected, "checked_pages": checked, "findings": findings}


__all__ = ["validate_visual_report"]
