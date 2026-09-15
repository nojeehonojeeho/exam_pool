"""Merge serial native-HWP clipboard transfer segments into one strict ledger.

Each segment is produced in an isolated COM session.  This tool verifies that
every source-owned item has exactly one native ``copy`` and one native ``move``
record, that all payload readbacks agree, and that the Windows clipboard
diagnostics were actually ready.  It never turns a failed or partial segment
into a successful ledger.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.teacher_workflow import file_hash, write_json


def args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scope-json", type=Path, required=True,
                        help="Source audit with ordered scope_ids.")
    parser.add_argument("--target-hwp", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True, nargs="+",
                        help="Successful isolated COM segment reports.")
    parser.add_argument("--out", type=Path, required=True)
    return parser.parse_args()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def ref(path: Path) -> dict:
    return {"path": str(path.resolve()), "sha256": file_hash(path), "bytes": path.stat().st_size}


def scope_ids(path: Path) -> list[str]:
    raw = load_json(path)
    values = raw.get("scope_ids", raw if isinstance(raw, list) else [])
    if (not isinstance(values, list) or not values or any(not isinstance(item, str) or not item for item in values)
            or len(set(values)) != len(values)):
        raise ValueError("TRANSFER_SCOPE_IDS_INVALID")
    return values


def _session_ok(session: dict) -> bool:
    return (
        session.get("register_module_return") is True
        and not session.get("approval_windows")
        and not session.get("owned_pids_remaining")
    )


def merge(scope: list[str], target_sha256: str, reports: list[tuple[Path, dict]]) -> dict:
    """Validate and combine reports without assuming a fixed book size."""
    if not reports:
        raise ValueError("TRANSFER_SEGMENTS_EMPTY")
    expected = {(item_id, operation) for item_id in scope for operation in ("copy", "move")}
    seen: set[tuple[str, str]] = set()
    merged_transfers: list[dict] = []
    merged_sessions: list[dict] = []
    artifacts: list[dict] = []
    for path, report in reports:
        if report.get("source_sha256") != target_sha256:
            raise ValueError("TRANSFER_SEGMENT_TARGET_MISMATCH:" + str(path))
        if not report.get("status", "").startswith("COM_OPERATIONS_PASS"):
            raise ValueError("TRANSFER_SEGMENT_NOT_PASS:" + str(path))
        if report.get("source_unchanged") is not True:
            raise ValueError("TRANSFER_SOURCE_MUTATED:" + str(path))
        sessions = report.get("sessions")
        if not isinstance(sessions, list) or not sessions or not all(_session_ok(row) for row in sessions):
            raise ValueError("TRANSFER_SEGMENT_SESSION_NOT_CLOSED:" + str(path))
        segment_rows = report.get("transfers")
        if not isinstance(segment_rows, list) or not segment_rows:
            raise ValueError("TRANSFER_SEGMENT_ROWS_EMPTY:" + str(path))
        native_records = [
            record for session in sessions for record in session.get("clipboard_records", [])
        ]
        native_pairs = {
            (str(record.get("item_id", "")), str(record.get("operation", "")))
            for record in native_records
            if record.get("record", {}).get("ready") is True
        }
        for row in segment_rows:
            pair = (str(row.get("id", "")), str(row.get("operation", "")))
            if pair not in expected or pair in seen:
                raise ValueError("TRANSFER_PAIR_DUPLICATE_OR_OUT_OF_SCOPE:" + repr(pair))
            if not (row.get("whole_question") is True and row.get("readback") is True
                    and row.get("payload_equal") is True and row.get("native_clipboard_ready") is True):
                raise ValueError("TRANSFER_ROW_NOT_CLOSED:" + repr(pair))
            if pair not in native_pairs:
                raise ValueError("TRANSFER_NATIVE_CLIPBOARD_EVIDENCE_MISSING:" + repr(pair))
            before = row.get("source_payload_sha256")
            after = row.get("readback_payload_sha256")
            if not isinstance(before, str) or len(before) != 64 or before != after:
                raise ValueError("TRANSFER_PAYLOAD_READBACK_MISMATCH:" + repr(pair))
            artifact = Path(row.get("readback_artifact", ""))
            if not artifact.is_file():
                raise ValueError("TRANSFER_READBACK_ARTIFACT_MISSING:" + repr(pair))
            merged_transfers.append({
                "id": pair[0], "operation": pair[1], "whole_question": True,
                "readback": True, "payload_equal": True,
                "before_payload_sha256": before, "after_payload_sha256": after,
                "readback_artifact": ref(artifact),
                "native_clipboard_ready": True,
                "native_clipboard_sha256": row.get("native_clipboard_sha256"),
                "segment": str(path.resolve()),
            })
            seen.add(pair)
        merged_sessions.extend(sessions)
        artifacts.append(ref(path))
    if seen != expected:
        missing = sorted(expected - seen)
        unexpected = sorted(seen - expected)
        raise ValueError("TRANSFER_SCOPE_COVERAGE_MISMATCH:" + json.dumps({"missing": missing, "unexpected": unexpected}, ensure_ascii=False))
    return {
        "schema": "teacher-com-pilot/v1",
        "status": "COM_OPERATIONS_PASS_REQUIRES_PAYLOAD_QA",
        "source_sha256": target_sha256,
        "source_unchanged": True,
        "transfer_scope_ids": scope,
        "transfers": sorted(merged_transfers, key=lambda row: (scope.index(row["id"]), row["operation"])),
        "sessions": merged_sessions,
        "segment_reports": artifacts,
        "internal_hwp_cut_paste": "RECORDED_SEPARATELY_NOT_A_NATIVE_CLIPBOARD_SUBSTITUTE",
        "merge_checks": {
            "all_scope_ids_have_one_copy_and_one_move": True,
            "all_native_clipboard_records_ready": True,
            "all_payload_readbacks_equal": True,
            "all_segment_sessions_closed": True,
        },
    }


def main() -> int:
    a = args()
    if a.out.exists():
        raise FileExistsError(a.out)
    scope = scope_ids(a.scope_json)
    target = file_hash(a.target_hwp)
    report_paths = [path.resolve() for path in a.report]
    if len(set(report_paths)) != len(report_paths):
        raise ValueError("TRANSFER_SEGMENT_REPORT_DUPLICATE")
    result = merge(scope, target, [(path, load_json(path)) for path in report_paths])
    write_json(a.out, result)
    print(json.dumps({"status": result["status"], "scope_count": len(scope), "transfer_count": len(result["transfers"])}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
