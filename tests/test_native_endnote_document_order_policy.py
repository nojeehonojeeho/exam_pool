"""Regression checks for the reusable native-endnote document-order policy."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "docs" / "NATIVE_ENDNOTE_DOCUMENT_ORDER_POLICY.md"
RELEASE_POLICY = ROOT / "docs" / "PDF_HWP_RELEASE_GATING_WORK_INSTRUCTIONS.md"


def test_policy_requires_separate_question_solution_and_endnote_documents() -> None:
    text = POLICY.read_text(encoding="utf-8")

    for phrase in (
        "문제 문서 (`question`)",
        "해설 문서 (`solution`)",
        "미주 문서 (`endnote`)",
        "최종 통합본은",
        "세 원본 문서를 덮어쓰거나 대체하지",
    ):
        assert phrase in text


def test_policy_makes_question_first_and_endnotes_document_end() -> None:
    text = " ".join(POLICY.read_text(encoding="utf-8").split())

    for phrase in (
        "모든 문제 페이지를 원본 읽기 순서로 먼저 배치",
        "첫 번째 native endnote body가 렌더되기 전까지 문제 페이지가 모두 끝나야",
        "`hp:endNotePr/hp:placement/@place`는 `END_OF_DOCUMENT`",
        "문항 하나를 복사하면 native reference와 그 문항의 linked endnote body가 정확히",
        "문항 하나를 이동하면 reference, linked body, 자동번호",
    ):
        assert phrase in text


def test_policy_forbids_inline_solution_leakage_and_plain_markers() -> None:
    text = POLICY.read_text(encoding="utf-8")

    assert "inline solution leakage" in text
    assert "주 본문에 inline solution leakage가 없고 평문 미주 표식이 없다" in text
    assert "`※`," in text
    assert "숨은 텍스트" in text
    assert "즉시 FAIL" in text


def test_policy_separates_root_causes_raw_findings_and_evidence_open() -> None:
    text = POLICY.read_text(encoding="utf-8")

    for phrase in (
        "`raw_finding_count`",
        "`unique_root_cause_candidate_count`",
        "`evidence_closed_item_count`",
        "`evidence_open_item_count`",
        "`release_blocker_count`",
        "candidate_only=true",
        "evidence_open_item_count=0",
        "FINAL_PASS",
    ):
        assert phrase in text


def test_policy_links_existing_detailed_instructions() -> None:
    text = POLICY.read_text(encoding="utf-8")
    assert "USER_INTENT_EXECUTION_DEFAULT.md" in text
    assert "PDF_HWP_SOURCE_FIDELITY_V2_WORK_INSTRUCTIONS.md" in text
    assert "PDF_HWP_MATH_ENDNOTE_WORK_RULES.md" in text
    assert "PDF_HWP_SOURCE_FIDELITY_V2_REGRESSION_SPEC.md" in text


def test_policy_requires_hash_bound_package_files_and_distinct_com_roles() -> None:
    text = RELEASE_POLICY.read_text(encoding="utf-8")
    assert "출고 요약의 `files`" in text
    assert "총 24개" in text
    assert "서로 다른 세 role" in text
