"""Regression checks for the shared PDF→HWP/HWPX/endnote execution policy."""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
POLICY = DOCS / "USER_INTENT_EXECUTION_DEFAULT.md"
AGENTS = ROOT / "AGENTS.md"


def _pdf_hwp_execution_docs() -> list[Path]:
    """Return execution documents that must inherit the shared policy."""

    paths: list[Path] = []
    for path in DOCS.glob("*.md"):
        if path == POLICY:
            continue
        text = path.read_text(encoding="utf-8")
        if re.search(r"PDF.*HWP|HWP.*PDF|HWPX|endnote|미주", text, flags=re.IGNORECASE):
            paths.append(path)
    return sorted(paths)


def test_policy_captures_intent_execution_and_evidence_boundary() -> None:
    text = POLICY.read_text(encoding="utf-8")

    for phrase in ("할 수 있나", "원해", "도와줘", "실행 지시"):
        assert phrase in text
    for phrase in ("evidence-open", "CANDIDATE", "FINAL/PASS", "원문에 없는 내용 생성"):
        assert phrase in text
    assert "HWP/HWPX" in text
    assert "미주" in text


def test_all_pdf_hwp_execution_docs_link_shared_policy() -> None:
    docs = _pdf_hwp_execution_docs()
    assert docs, "the audit must cover at least one execution document"
    missing = [path.name for path in docs if "USER_INTENT_EXECUTION_DEFAULT.md" not in path.read_text(encoding="utf-8")]
    assert missing == []


def test_policy_names_this_regression_audit() -> None:
    assert "test_user_intent_execution_default.py" in POLICY.read_text(encoding="utf-8")


def test_project_rules_point_to_shared_policy() -> None:
    text = AGENTS.read_text(encoding="utf-8")
    assert "docs/USER_INTENT_EXECUTION_DEFAULT.md" in text
    assert "확인 질문이나" in text
    assert "검증 전 FINAL 승격" in text
