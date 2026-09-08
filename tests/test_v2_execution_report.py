from __future__ import annotations

import json
from pathlib import Path

from app.v2_execution_report import build_execution_report


def _state(tmp_path: Path) -> Path:
    state = tmp_path / "state"
    state.mkdir()
    closure = {"scope_item_count": 3, "inventory_item_count": 3, "reconstructed_item_count": 2,
               "legacy_reviewed_scope_count": 2, "evidence_closed_item_count": 0,
               "evidence_open_item_count": 3, "formula_bearing_item_count": 2,
               "source_formula_occurrence_count": 4, "mathir_occurrence_count": 0,
               "writer_formula_occurrence_count": 0, "saved_hwpx_equation_count": 0,
               "reopened_equation_count": 0, "raw_finding_count": 5, "unique_root_cause_count": 2,
               "blocking_item_count": 3, "release_blocker_count": 5}
    (state / "evidence-closure-summary.json").write_text(json.dumps(closure), encoding="utf-8")
    (state / "root-cause-summary.json").write_text(json.dumps({"groups": [
        {"root_cause_id": "formula-a", "area": "formula", "raw_finding_count": 4, "resolved": False},
        {"root_cause_id": "other", "area": "coverage", "raw_finding_count": 1, "resolved": False},
    ]}), encoding="utf-8")
    (state / "work-queue.json").write_text(json.dumps({"groups": {
        "chapter_I|page_1|formula": [{"item_id": "I-1", "source_page": 1, "chapter": "I", "status": "open", "root_causes": ["formula-a"]}, {"item_id": "I-2", "source_page": 1, "chapter": "I", "status": "open", "root_causes": ["formula-a"]}],
        "chapter_I|page_2|revalidate_legacy_subset": [{"item_id": "I-3", "source_page": 2, "chapter": "I", "status": "revalidate_legacy_subset", "root_causes": []}, {"item_id": "I-4", "source_page": 2, "chapter": "I", "status": "revalidate_legacy_subset", "root_causes": []}],
    }}), encoding="utf-8")
    (state / "build-and-qa.json").write_text(json.dumps({"status": "FAIL", "stage": "source_review"}), encoding="utf-8")
    (state / "strict-findings.jsonl").write_text('{"code":"A"}\n{"code":"B"}\n', encoding="utf-8")
    return state


def test_report_keeps_raw_findings_and_open_items_separate(tmp_path: Path) -> None:
    report = build_execution_report(_state(tmp_path))
    assert report["status"] == "REVIEW_REQUIRED"
    assert report["metrics"]["evidence_open_item_count"] == 3
    assert report["metrics"]["raw_finding_count"] == 2
    assert report["metrics"]["release_blocker_count"] == 5
    assert report["legacy_revalidation"]["pass_count"] == 0
    assert report["legacy_revalidation"]["fail_count"] == 2
    assert report["root_cause_top20_formula"][0]["root_cause_id"] == "formula-a"
    assert report["work_queue"]["group_count"] == 2


def test_report_allows_final_pass_only_when_all_counts_and_build_are_clean(tmp_path: Path) -> None:
    state = _state(tmp_path)
    closure = json.loads((state / "evidence-closure-summary.json").read_text(encoding="utf-8"))
    closure.update({"evidence_open_item_count": 0, "raw_finding_count": 0, "blocking_item_count": 0, "release_blocker_count": 0})
    (state / "evidence-closure-summary.json").write_text(json.dumps(closure), encoding="utf-8")
    (state / "strict-findings.jsonl").write_text("", encoding="utf-8")
    (state / "build-and-qa.json").write_text(json.dumps({"status": "PASS", "stage": "complete"}), encoding="utf-8")
    report = build_execution_report(state)
    assert report["final_pass"] is True
    assert report["status"] == "FINAL_PASS"

