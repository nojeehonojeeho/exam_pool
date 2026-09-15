"""Bind fresh, target-hash-checked evidence to the strict teacher release gate.

The tool never manufactures a PASS.  It normalizes audit/COM/visual artifacts
into the gate schema and leaves an evidence kind REVIEW_REQUIRED when its raw
artifact lacks a required observation (for example native clipboard bytes or a
separately attested physical boundary).  This makes a rerun auditable after a
layout-only repair instead of silently reusing reports for an older target.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.teacher_workflow import file_hash, release_gate, write_json


REQUIRED = (
    "source_scope", "source_payload", "style_roles", "font_render", "header_render",
    "workspace", "endnote_order", "com_roundtrip", "whole_question_transfer", "visual_qa",
)


def ref(path: Path) -> dict:
    return {"path": str(path.resolve()), "sha256": file_hash(path), "bytes": path.stat().st_size}


def args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target-hwp", type=Path, required=True)
    parser.add_argument("--target-hwpx", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--style", type=Path, required=True)
    parser.add_argument("--font", type=Path, required=True)
    parser.add_argument("--header", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--com", type=Path, required=True)
    parser.add_argument("--endnote", type=Path)
    parser.add_argument("--visual", type=Path)
    parser.add_argument("--transfer", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    return parser.parse_args()


def load(path: Path | None) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig")) if path and path.is_file() else {}


def base(kind: str, target: dict, scope: list[str], *, status: str, checks: dict, open_items: list, artifact: Path, **extra) -> dict:
    return {
        "schema": "teacher-evidence/v1", "kind": kind, "target_sha256": target,
        "scope_ids": scope, "status": status, "checks": checks, "open_items": open_items,
        "observations": [{"method": f"target-bound {kind} raw artifact", "artifact": ref(artifact)}], **extra,
    }


def main() -> int:
    a = args()
    if a.out.exists():
        raise FileExistsError(a.out)
    a.out.mkdir(parents=True)
    audit = load(a.audit)
    scope = list(map(str, audit.get("scope_ids", [])))
    target = {"hwp": file_hash(a.target_hwp), "hwpx": file_hash(a.target_hwpx)}
    reports: dict[str, dict] = {}
    source_scope_ok = bool(scope) and audit.get("checks", {}).get("source_ids_resolve") is True and audit.get("checks", {}).get("target_anchor_count") == len(scope)
    reports["source_scope"] = base("source_scope", target, scope, status="PASS" if source_scope_ok else "REVIEW_REQUIRED",
        checks={"full_source_ids_resolve": source_scope_ok, "target_anchor_count_matches_scope": source_scope_ok},
        open_items=[] if source_scope_ok else [{"kind": "SOURCE_SCOPE_NOT_CLOSED"}], artifact=a.audit)
    source_payload_ok = audit.get("checks", {}).get("target_payload_equal_to_build_expected") is True and audit.get("checks", {}).get("source_payload_equal_after_boundary_normalization") is True
    reports["source_payload"] = base("source_payload", target, scope, status="PASS" if source_payload_ok else "REVIEW_REQUIRED",
        checks={"target_payload_equal_to_build_expected": source_payload_ok, "source_payload_equal_after_boundary_normalization": source_payload_ok},
        open_items=[] if source_payload_ok else [{"kind": "SOURCE_PAYLOAD_NOT_CLOSED", "ids": audit.get("mismatch_ids", [])}], artifact=a.audit)
    for kind, path in (("style_roles", a.style), ("font_render", a.font), ("header_render", a.header), ("workspace", a.workspace)):
        report = load(path)
        reports[kind] = report
    com = load(a.com)
    sessions = com.get("sessions", [])
    com_ok = com.get("status", "").startswith("COM_OPERATIONS_PASS") and bool(sessions) and all(row.get("register_module_return") is True and not row.get("approval_windows") and not row.get("owned_pids_remaining") for row in sessions)
    reports["com_roundtrip"] = base("com_roundtrip", target, scope, status="PASS" if com_ok else "REVIEW_REQUIRED",
        checks={"serial_save_reopen_and_b4_export": com_ok, "security_module_and_no_approval": com_ok, "owned_processes_exited": com_ok},
        open_items=[] if com_ok else [{"kind": "COM_ROUNDTRIP_NOT_CLOSED", "error": com.get("error") or com.get("shutdown_error")}], artifact=a.com)
    endnote = load(a.endnote)
    boundary_ok = endnote.get("status") == "PASS" and bool(endnote.get("independent_review"))
    reports["endnote_order"] = base("endnote_order", target, scope, status="PASS" if boundary_ok else "REVIEW_REQUIRED",
        checks={"physical_boundary_independently_attested": boundary_ok},
        open_items=[] if boundary_ok else [{"kind": "ENDNOTE_PHYSICAL_BOUNDARY_REVIEW_REQUIRED"}], artifact=a.endnote or a.audit,
        boundary={"last_question_page": endnote.get("last_main_story_page"), "first_note_page": endnote.get("first_endnote_page"),
                  "last_question_method": "actual page review" if boundary_ok else "unverified", "first_note_method": "actual native-endnote page review" if boundary_ok else "unverified"})
    visual = load(a.visual)
    # The visual producer stores HWP/HWPX render results separately.  Read
    # those real observations instead of treating their absence from an older
    # flattened schema as "zero pages".  Automatic coverage remains distinct
    # from an independently attested representative-page review.
    hwp_pages = int(visual.get("hwp", {}).get("page_count", 0) or 0)
    hwpx_pages = int(visual.get("hwpx", {}).get("page_count", 0) or 0)
    automatic_ok = visual.get("status") == "PASS" and hwp_pages > 0 and hwp_pages == hwpx_pages
    physical = hwp_pages if automatic_ok else 0
    automated = list(range(1, physical + 1)) if automatic_ok else []
    human = visual.get("human_reviewed_pages", [])
    visual_ok = automatic_ok and bool(human)
    reports["visual_qa"] = base("visual_qa", target, scope, status="PASS" if visual_ok else "REVIEW_REQUIRED",
        checks={"automated_render_all_pages": automatic_ok, "separate_human_representative_attestation": bool(human)},
        open_items=[] if visual_ok else [{"kind": "VISUAL_QA_REVIEW_REQUIRED"}], artifact=a.visual or a.audit,
        physical_page_count=physical, automated_pages=automated, human_reviewed_pages=human)
    transfer = load(a.transfer)
    raw_transfers = transfer.get("transfers", [])
    # Preserve raw Windows clipboard diagnostics independently from HWP's
    # own Cut/Paste implementation.  A changed clipboard sequence number or
    # a successful internal HWP action is not proof that ``Hwp Native`` bytes
    # were made available by the operating-system clipboard.
    native_clipboard_records = [
        record
        for session in transfer.get("sessions", [])
        for record in session.get("clipboard_records", [])
    ]
    native_clipboard_ready = bool(native_clipboard_records) and all(
        record.get("record", {}).get("ready") is True for record in native_clipboard_records
    )
    expected_pairs = {(item_id, operation) for item_id in scope for operation in ("copy", "move")}
    normalized_transfers = []
    for transfer_row in raw_transfers:
        before = transfer_row.get("before_payload_sha256", transfer_row.get("source_payload_sha256"))
        after = transfer_row.get("after_payload_sha256", transfer_row.get("readback_payload_sha256"))
        raw_artifact = transfer_row.get("readback_artifact")
        if isinstance(raw_artifact, dict):
            artifact = raw_artifact
        elif isinstance(raw_artifact, str) and Path(raw_artifact).is_file():
            artifact = ref(Path(raw_artifact))
        else:
            artifact = None
        normalized_transfers.append({
            "id": transfer_row.get("id"), "operation": transfer_row.get("operation"),
            "whole_question": transfer_row.get("whole_question"), "readback": transfer_row.get("readback"),
            "payload_equal": transfer_row.get("payload_equal"),
            "before_payload_sha256": before, "after_payload_sha256": after,
            "readback_artifact": artifact,
            "native_clipboard_ready": transfer_row.get("native_clipboard_ready"),
        })
    actual_pairs = {(row.get("id"), row.get("operation")) for row in normalized_transfers}
    source_matches_target = transfer.get("source_sha256") == target["hwp"]
    transfer_ok = (
        source_matches_target
        and transfer.get("status", "").startswith("COM_OPERATIONS_PASS")
        and len(normalized_transfers) == len(scope) * 2
        and actual_pairs == expected_pairs
        and native_clipboard_ready
        and all(row.get("whole_question") is True and row.get("readback") is True and row.get("payload_equal") is True
                and row.get("native_clipboard_ready") is True and row.get("before_payload_sha256") == row.get("after_payload_sha256")
                and isinstance(row.get("readback_artifact"), dict) for row in normalized_transfers)
    )
    reports["whole_question_transfer"] = base("whole_question_transfer", target, scope, status="PASS" if transfer_ok else "REVIEW_REQUIRED",
        checks={
            "transfer_input_is_current_target_hwp": source_matches_target,
            "native_clipboard_records_observed": bool(native_clipboard_records),
            "native_clipboard_operations_ready": native_clipboard_ready,
            "all_scope_copy_and_move_native_clipboard_readback": transfer_ok,
        },
        open_items=[] if transfer_ok else [{
            "kind": "WHOLE_QUESTION_TRANSFER_NOT_CLOSED" if native_clipboard_ready else "CLIPBOARD_NATIVE_UNAVAILABLE",
            "error": transfer.get("error"),
            "status": transfer.get("status"),
            "scope_count": len(scope),
            "native_clipboard_record_count": len(native_clipboard_records),
            "retry_policy": "one isolated new COM session only; no same-session loop",
        }], artifact=a.transfer or a.audit,
        transfers=normalized_transfers,
        native_clipboard_records=native_clipboard_records,
        internal_hwp_cut_paste=transfer.get("internal_hwp_cut_paste", "NOT_A_NATIVE_CLIPBOARD_SUBSTITUTE"))
    for kind, report in reports.items():
        path = a.out / f"{kind}.json"
        write_json(path, report)
    run = {"schema": "teacher-release/v1", "scope_ids": scope,
           "targets": {"hwp": ref(a.target_hwp), "hwpx": ref(a.target_hwpx)},
           "evidence": {kind: ref(a.out / f"{kind}.json") for kind in REQUIRED}}
    write_json(a.out / "release-input.json", run)
    result = release_gate(run, a.out)
    write_json(a.out / "release-gate.json", result)
    print(json.dumps({"status": result["status"], "final": result["final"], "failures": result["failures"]}, ensure_ascii=False))
    return 0 if result["final"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
