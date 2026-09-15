import json
from pathlib import Path

import pytest

from app.teacher_workflow import file_hash
from tools.teacher_transfer_merge import merge


def segment(tmp_path: Path, ids: list[str], *, status="COM_OPERATIONS_PASS_REQUIRES_PAYLOAD_QA", ready=True):
    source = tmp_path / "source.hwp"
    source.write_bytes(b"target")
    artifact = tmp_path / ("readback-" + "-".join(ids) + ".hwpx")
    artifact.write_bytes(b"readback")
    rows = []
    records = []
    for index, item_id in enumerate(ids):
        for operation in ("copy", "move"):
            rows.append({"id": item_id, "operation": operation, "whole_question": True, "readback": True,
                         "payload_equal": True, "native_clipboard_ready": ready,
                         "source_payload_sha256": "a" * 64, "readback_payload_sha256": "a" * 64,
                         "readback_artifact": str(artifact)})
            records.append({"item_id": item_id, "operation": operation, "record": {"ready": ready}})
    return source, {"source_sha256": file_hash(source), "status": status, "source_unchanged": True,
                    "sessions": [{"register_module_return": True, "approval_windows": [], "owned_pids_remaining": [],
                                  "clipboard_records": records}], "transfers": rows}


def test_merge_requires_complete_unique_native_scope(tmp_path):
    source, left = segment(tmp_path, ["q1", "q2"])
    _, right = segment(tmp_path, ["q3"])
    left_path = tmp_path / "left.json"; right_path = tmp_path / "right.json"
    left_path.write_text(json.dumps(left)); right_path.write_text(json.dumps(right))
    result = merge(["q1", "q2", "q3"], file_hash(source), [(left_path, left), (right_path, right)])
    assert len(result["transfers"]) == 6
    assert result["merge_checks"]["all_scope_ids_have_one_copy_and_one_move"] is True
    assert all("before_payload_sha256" in row for row in result["transfers"])


def test_merge_rejects_missing_or_not_ready_native_record(tmp_path):
    source, report = segment(tmp_path, ["q1"], ready=False)
    path = tmp_path / "bad.json"; path.write_text(json.dumps(report))
    with pytest.raises(ValueError, match="TRANSFER_ROW_NOT_CLOSED"):
        merge(["q1"], file_hash(source), [(path, report)])


def test_merge_rejects_late_artifact_after_supervisor_deadline(tmp_path):
    source, report = segment(tmp_path, ["q1"])
    path = tmp_path / "late.json"; path.write_text(json.dumps(report))
    (tmp_path / "timeout.json").write_text('{"status":"COM_DEADLINE_EXCEEDED"}')
    with pytest.raises(ValueError, match="TRANSFER_SEGMENT_DEADLINE_EXCEEDED"):
        merge(["q1"], file_hash(source), [(path, report)])
