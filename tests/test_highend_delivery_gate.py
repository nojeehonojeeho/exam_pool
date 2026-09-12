from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.highend_delivery_gate import REQUIRED_SUBJECTS, audit_com_provenance, audit_delivery_summary


def _scope_manifest(*, declared: int = 1, closed: bool = True) -> dict:
    evidence = {
        "source_pdf_sha256": "a" * 64,
        "source_page": 1,
        "bbox_pt": [0, 0, 10, 10],
        "source_crop_sha256": "b" * 64,
        "review_id": "review-1",
    }
    item = {"item_id": "1", "evidence_status": "CLOSED" if closed else "OPEN", "source_evidence": evidence}
    return {
        "status": "FULL_SOURCE_CLOSED",
        "strict_pass": True,
        "full_source_scope": True,
        # ``problem_items`` is intentionally not authoritative: it may be a
        # selected-output count.  Full-source manifests must name their
        # denominator explicitly.
        "full_source_item_count": declared,
        "items": [item for _ in range(declared)],
        "source_documents": {
            "problem": {"sha256": "c" * 64, "page_count": 2},
            "solution": {"sha256": "d" * 64, "page_count": 2},
        },
    }


def _summary(*, source_status: str = "FULL_SOURCE_CLOSED") -> dict:
    subjects = {
        subject: {"status": "PASS", "files": 3}
        for subject in REQUIRED_SUBJECTS
    }
    endnotes = {
        subject: {"status": "PASS", "endnotes": 1, "autonum": 1, "empty": 0}
        for subject in REQUIRED_SUBJECTS
    }
    files = []
    for subject in REQUIRED_SUBJECTS:
        for role in ("문제", "미주작업_완료", "정답및풀이"):
            for extension, digest in (("hwp", "e" * 64), ("hwpx", "f" * 64)):
                files.append({"subject": subject, "name": f"{subject}_{role}.{extension}", "sha256": digest})
    return {
        "schema": "highend-v6-comverified-delivery-summary-v1",
        "release_status": "FINAL" if source_status == "FULL_SOURCE_CLOSED" else "BLOCKED_SOURCE_FIDELITY_OPEN",
        "final": source_status == "FULL_SOURCE_CLOSED",
        "structural_audit": {"status": "PASS", "subjects": subjects},
        "integrated_endnote_audit": {"status": "PASS", "subjects": endnotes},
        "files": files,
        "source_fidelity": {"status": source_status, "notes": "full source closed" if source_status == "FULL_SOURCE_CLOSED" else "selected scope; full source remains open"},
    }


def _com_report(summary: dict) -> dict:
    rows = []
    for subject in REQUIRED_SUBJECTS:
        for role in ("문제", "미주작업_완료", "정답및풀이"):
            rows.append(
                {
                    "subject": subject,
                    "input": f"C:\\source\\{subject}_{role}.hwpx",
                    "input_sha256_before": "1" * 64,
                    "input_sha256_after": "1" * 64,
                    "sessions": [
                        {
                            "label": "write",
                            "events": ["dispatch_ex_ok"],
                            "register_module_return": True,
                            "open_return": True,
                            "save_hwp_return": True,
                            "save_hwpx_return": True,
                            "save_pdf_return": True,
                            "wait": {"status": "OK", "alive": []},
                            "new_pids_exited": True,
                        },
                        {
                            "label": "reopen",
                            "events": ["dispatch_ex_ok"],
                            "register_module_return": True,
                            "open_return": True,
                            "readback_hwpx_return": True,
                            "readback_exists": True,
                            "wait": {"status": "OK", "alive": []},
                            "new_pids_exited": True,
                        },
                    ],
                    "status": "PASS",
                    "approval_before": {"status": "OK", "titles": []},
                    "approval_after": {"status": "OK", "titles": []},
                    "approval_window_count": 0,
                    "output_hashes": {
                        f"{subject}_{role}.hwp": "e" * 64,
                        f"{subject}_{role}.hwpx": "f" * 64,
                    },
                }
            )
    return {"schema": "hwp-dispatchex-serial-readback-batch-v1", "status": "PASS", "count": 12, "pass_count": 12, "fail_count": 0, "rows": rows}


def _evidence() -> tuple[dict, dict[str, dict], dict]:
    summary = _summary()
    scopes = {subject: _scope_manifest() for subject in REQUIRED_SUBJECTS}
    com = _com_report(summary)
    return summary, scopes, com


def test_full_source_and_com_closure_allows_final():
    summary, scopes, com = _evidence()
    result = audit_delivery_summary(summary, scope_manifests=scopes, com_report=com)
    assert result["promotion_allowed"] is True
    assert result["gates"]["source_scope_closed"] is True
    assert result["gates"]["com_provenance_closed"] is True


def test_selected_scope_cannot_promote_even_when_endnote_numbers_match():
    summary, scopes, com = _evidence()
    summary = copy.deepcopy(summary)
    summary["source_fidelity"] = {"status": "OPEN", "notes": "Selected package-to-scope counts only; full source remains open."}
    summary["final"] = False
    summary["release_status"] = "BLOCKED_SOURCE_FIDELITY_OPEN"
    scopes["수학II"] = _scope_manifest()
    scopes["수학II"]["strict_pass"] = False
    scopes["수학II"]["status"] = "CANDIDATE_WITH_HUMAN_REVIEW_REQUIRED"
    result = audit_delivery_summary(summary, scope_manifests=scopes, com_report=com)
    codes = {item["code"] for item in result["findings"]}
    assert result["promotion_allowed"] is False
    assert "SCOPE_STRICT_PASS_REQUIRED" in codes
    assert "ENDNOTE_COUNT_NOT_SOURCE_CLOSURE" in codes


def test_generic_closed_status_is_not_full_source_closure():
    summary, scopes, com = _evidence()
    scopes["고등수학상"] = _scope_manifest()
    scopes["고등수학상"]["status"] = "CLOSED"
    scopes["고등수학상"]["full_source_scope"] = False
    result = audit_delivery_summary(summary, scope_manifests=scopes, com_report=com)
    codes = {item["code"] for item in result["findings"]}
    assert result["promotion_allowed"] is False
    assert "SCOPE_FULL_SOURCE_UNDECLARED" in codes


def test_nested_generic_complete_flag_is_not_full_source_declaration():
    summary, scopes, com = _evidence()
    scopes["수학II"] = _scope_manifest()
    scopes["수학II"]["status"] = "CANDIDATE"
    scopes["수학II"]["full_source_scope"] = {"complete": True}
    result = audit_delivery_summary(summary, scope_manifests=scopes, com_report=com)
    codes = {item["code"] for item in result["findings"]}
    assert result["promotion_allowed"] is False
    assert "SCOPE_FULL_SOURCE_UNDECLARED" in codes


def test_open_item_evidence_blocks_source_scope():
    summary, scopes, com = _evidence()
    scopes["고등수학상"] = _scope_manifest(closed=False)
    result = audit_delivery_summary(summary, scope_manifests=scopes, com_report=com)
    assert result["promotion_allowed"] is False
    assert "SCOPE_EVIDENCE_OPEN" in {item["code"] for item in result["findings"]}


def test_matching_endnote_count_without_full_source_evidence_is_blocked():
    summary, _, com = _evidence()
    count_only = {
        "status": "CANDIDATE",
        "strict_pass": False,
        "counts": {"problem_items": 1},
        "source_documents": {
            "problem": {"sha256": "c" * 64, "page_count": 2},
            "solution": {"sha256": "d" * 64, "page_count": 2},
        },
    }
    result = audit_delivery_summary(summary, scope_manifests={subject: count_only for subject in REQUIRED_SUBJECTS}, com_report=com)
    codes = {item["code"] for item in result["findings"]}
    assert result["promotion_allowed"] is False
    assert "SCOPE_FULL_SOURCE_UNDECLARED" in codes
    assert "SCOPE_EVIDENCE_CLOSURE_MISSING" in codes
    assert "ENDNOTE_COUNT_NOT_SOURCE_CLOSURE" in codes


def test_com_pass_claim_without_lifecycle_or_hash_linkage_is_blocked():
    summary, _, com = _evidence()
    broken = copy.deepcopy(com)
    broken["rows"][0]["sessions"][0]["new_pids_exited"] = False
    broken["rows"][0]["output_hashes"][f"{REQUIRED_SUBJECTS[0]}_문제.hwp"] = "0" * 64
    result = audit_com_provenance(broken, summary=summary)
    codes = {item["code"] for item in result["findings"]}
    assert result["closure_eligible"] is False
    assert "COM_SESSION_LIFECYCLE_INCOMPLETE" in codes
    assert "COM_PACKAGE_HASH_MISMATCH" in codes


def test_missing_scope_manifests_fail_closed():
    summary, _, com = _evidence()
    result = audit_delivery_summary(summary, com_report=com)
    assert result["promotion_allowed"] is False
    assert "SCOPE_MANIFESTS_REQUIRED" in {item["code"] for item in result["findings"]}


def test_missing_candidate_file_list_cannot_bypass_com_hash_linkage():
    summary, scopes, com = _evidence()
    summary = copy.deepcopy(summary)
    summary.pop("files")
    result = audit_delivery_summary(summary, scope_manifests=scopes, com_report=com)
    codes = {item["code"] for item in result["findings"]}
    assert result["promotion_allowed"] is False
    assert "SUMMARY_FILES_REQUIRED" in codes
    assert result["gates"]["candidate_files_hashed"] is False


def test_candidate_file_package_must_have_exact_role_and_extension_matrix():
    summary, scopes, com = _evidence()
    summary = copy.deepcopy(summary)
    summary["files"].append(
        {"subject": "고등수학상", "name": "고등수학상_임의파일.txt", "sha256": "a" * 64}
    )
    result = audit_delivery_summary(summary, scope_manifests=scopes, com_report=com)
    codes = {item["code"] for item in result["findings"]}
    assert result["promotion_allowed"] is False
    assert "SUMMARY_FILE_ROLE_SET_INVALID" in codes


def test_empty_scope_records_cannot_claim_aggregate_closure():
    summary, scopes, com = _evidence()
    scopes["수학II"] = _scope_manifest()
    scopes["수학II"]["items"] = []
    scopes["수학II"]["evidence_closed_item_count"] = 1
    scopes["수학II"]["evidence_open_item_count"] = 0
    result = audit_delivery_summary(summary, scope_manifests=scopes, com_report=com)
    codes = {item["code"] for item in result["findings"]}
    assert result["promotion_allowed"] is False
    assert "SCOPE_ITEM_RECORDS_REQUIRED" in codes


def test_com_rows_must_cover_distinct_document_roles():
    summary, _, com = _evidence()
    broken = copy.deepcopy(com)
    for row in broken["rows"][:3]:
        row["role"] = "문제"
    result = audit_com_provenance(broken, summary=summary)
    assert result["closure_eligible"] is False
    assert "COM_ROLE_SET_INVALID" in {item["code"] for item in result["findings"]}


def test_cli_reads_summary_scope_root_and_emits_audit(tmp_path):
    summary, scopes, com = _evidence()
    summary_path = tmp_path / "summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False), encoding="utf-8")
    root = tmp_path / "scopes"
    for subject, manifest in scopes.items():
        folder = root / {"고등수학상": "math_up", "고등수학하": "math_down", "수학II": "math2", "확률과_통계": "probability"}[subject]
        folder.mkdir(parents=True)
        filename = "highend_probability_source_manifest.json" if subject == "확률과_통계" else "source_inventory.json"
        (folder / filename).write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    com_path = tmp_path / "com.json"
    com_path.write_text(json.dumps(com, ensure_ascii=False), encoding="utf-8")
    output_path = tmp_path / "audit.json"
    completed = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "highend_delivery_gate.py"), str(summary_path), "--scope-root", str(root), "--com-report", str(com_path), "--json", str(output_path)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0
    assert json.loads(output_path.read_text(encoding="utf-8"))["promotion_allowed"] is True
