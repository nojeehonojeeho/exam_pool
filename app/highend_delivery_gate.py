"""Repository-level gate for high-end four-subject delivery packages.

The existing HWP/HWPX and endnote auditors intentionally answer structural
questions only.  This module is the final *promotion* gate: it requires a
closed full-source scope for every subject and independently checks that the
COM evidence is serial, reproducible, and hash-linked to the package.  A
matching endnote count is therefore never treated as proof of source closure.

The functions are deliberately mapping based so that an audit can be run on
JSON loaded from a report, or on synthetic records in tests.  They do not
write or mutate any input artifact.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence


SCHEMA_VERSION = "highend-delivery-gate-v1"
SUMMARY_SCHEMA = "highend-v6-comverified-delivery-summary-v1"
REQUIRED_SUBJECTS = ("고등수학상", "고등수학하", "수학II", "확률과_통계")
_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
_CLOSED_STATUSES = {
    "FULL_SOURCE_CLOSED",
    "FULL_SOURCE_VERIFIED",
    "SOURCE_FIDELITY_CLOSED",
    "SOURCE_FIDELITY_VERIFIED",
}


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and bool(_SHA256_RE.fullmatch(value.strip()))


def _as_mapping(value: Any) -> Mapping[str, Any] | None:
    return value if isinstance(value, Mapping) else None


def _as_int(value: Any) -> int | None:
    # bool is an int subclass, but it is not a count.
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value >= 0:
        return value
    if isinstance(value, float) and value.is_integer() and value >= 0:
        return int(value)
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def _first_int(record: Mapping[str, Any], keys: Sequence[str]) -> int | None:
    for key in keys:
        count = _as_int(record.get(key))
        if count is not None:
            return count
    return None


def _nested_int(record: Mapping[str, Any], paths: Sequence[Sequence[str]]) -> int | None:
    for path in paths:
        current: Any = record
        for key in path:
            current = current.get(key) if isinstance(current, Mapping) else None
        count = _as_int(current)
        if count is not None:
            return count
    return None


def _finding(code: str, message: str, *, subject: str | None = None, blocking: bool = True) -> dict[str, Any]:
    result: dict[str, Any] = {"code": code, "blocking": blocking, "message": message}
    if subject is not None:
        result["subject"] = subject
    return result


def _records(manifest: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    """Return item records without assuming a particular manifest version."""

    for key in ("items", "item_records", "records", "problem_items"):
        value = manifest.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, Mapping)]
    return []


def _source_documents(manifest: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    value = manifest.get("source_documents")
    if isinstance(value, Mapping):
        return [item for item in value.values() if isinstance(item, Mapping)]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, Mapping)]
    value = manifest.get("documents")
    if isinstance(value, Mapping):
        return [item for item in value.values() if isinstance(item, Mapping)]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, Mapping)]
    return []


def _document_hash(document: Mapping[str, Any]) -> str | None:
    for key in ("sha256", "source_pdf_sha256", "pdf_sha256", "hash"):
        value = document.get(key)
        if _is_sha256(value):
            return str(value).lower()
    return None


def _document_pages(document: Mapping[str, Any]) -> int | None:
    return _first_int(document, ("page_count", "pdf_pages", "pages", "physical_pages"))


def _explicit_full_scope(manifest: Mapping[str, Any]) -> bool:
    direct = (
        "full_source_scope",
        "source_scope_complete",
        "scope_complete",
        "full_source",
        "coverage_complete",
    )
    if any(manifest.get(key) is True for key in direct):
        return True
    for key in ("scope", "coverage", "full_source_scope"):
        nested = _as_mapping(manifest.get(key))
        # Nested ``complete``/``closed`` flags are ambiguous (they may only
        # describe the selected review subset).  Require the nested object to
        # say explicitly that it is full-source.
        if nested and any(nested.get(k) is True for k in ("full_source", "is_full_source")):
            return True
    statuses = [manifest.get("status"), manifest.get("scope_status"), manifest.get("source_fidelity_status")]
    # A generic ``CLOSED`` status is intentionally not enough.  Older
    # manifests used it for a selected/partially reviewed scope, so accepting
    # it here would allow a non-full source package to be promoted.
    return any(isinstance(status, str) and status.strip().upper() in _CLOSED_STATUSES for status in statuses)


def _strict_pass(manifest: Mapping[str, Any]) -> bool:
    return manifest.get("strict_pass") is True


def _human_review_required(manifest: Mapping[str, Any]) -> bool:
    if manifest.get("human_review_required") is True:
        return True
    for key in ("render_review", "review", "scope_policy"):
        nested = _as_mapping(manifest.get(key))
        if nested and nested.get("human_review_required") is True:
            return True
    status_values = [manifest.get("status"), manifest.get("scope_status")]
    return any(isinstance(value, str) and "REVIEW_REQUIRED" in value.upper() for value in status_values)


def _evidence_closed(record: Mapping[str, Any]) -> bool:
    # CLOSED without source coordinates is not evidence closure.
    status_values = [record.get("evidence_status"), record.get("v2_status"), record.get("review_status")]
    closed = any(isinstance(value, str) and value.strip().upper() == "CLOSED" for value in status_values)
    evidence = _as_mapping(record.get("source_evidence")) or _as_mapping(record.get("evidence")) or record
    if not closed:
        return False
    source_hash = evidence.get("source_pdf_sha256") or evidence.get("pdf_sha256")
    crop_hash = evidence.get("source_crop_sha256") or evidence.get("crop_sha256")
    page = _as_int(evidence.get("source_page"))
    bbox = evidence.get("bbox_pt") or evidence.get("bbox")
    review_id = evidence.get("review_id") or record.get("review_id")
    return (
        _is_sha256(source_hash)
        and page is not None
        and page > 0
        and isinstance(bbox, (list, tuple))
        and len(bbox) >= 4
        and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in bbox[:4])
        and _is_sha256(crop_hash)
        and isinstance(review_id, str)
        and bool(review_id.strip())
    )


def _record_id(record: Mapping[str, Any]) -> str | None:
    for key in ("item_id", "source_item_id", "question_id", "id"):
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, int) and not isinstance(value, bool):
            return str(value)
    return None


def _manifest_count(manifest: Mapping[str, Any]) -> int | None:
    counts = _as_mapping(manifest.get("counts"))
    paths: list[tuple[str, ...]] = []
    if counts:
        # ``counts.problem_items`` is often the selected output count rather
        # than the authoritative full-source denominator.  Never infer full
        # scope from that ambiguous key.
        paths.extend(("counts", key) for key in ("full_source_item_count", "source_items", "total_items", "item_count"))
    paths.extend((key,) for key in ("full_source_item_count", "source_item_count", "declared_item_count", "estimated_total_problem_items", "total_items", "item_count"))
    return _nested_int(manifest, paths)


def _scope_count(manifest: Mapping[str, Any], records: list[Mapping[str, Any]]) -> int | None:
    count = _nested_int(
        manifest,
        (
            ("scope_item_count",),
            ("reviewed_item_count",),
            ("selected_item_count",),
            ("counts", "reviewed_items"),
            ("counts", "selected_items"),
            ("coverage", "reviewed_items"),
        ),
    )
    return count if count is not None else (len(records) if records else None)


def audit_scope_manifest(
    manifest: Mapping[str, Any],
    *,
    subject: str | None = None,
    path: str | None = None,
) -> dict[str, Any]:
    """Audit one source manifest for full-source, evidence-backed closure."""

    findings: list[dict[str, Any]] = []
    subject_label = subject or (str(manifest.get("subject") or "(unknown)") if isinstance(manifest, Mapping) else "(unknown)")
    if not isinstance(manifest, Mapping):
        return {
            "subject": subject_label,
            "path": path,
            "closure_eligible": False,
            "findings": [_finding("SCOPE_SCHEMA_INVALID", "Source scope manifest must be a JSON object.", subject=subject_label)],
        }

    records = _records(manifest)
    source_documents = _source_documents(manifest)
    declared = _manifest_count(manifest)
    scope_count = _scope_count(manifest, records)
    closed_record_count = sum(1 for record in records if _evidence_closed(record))
    explicit_closed = _nested_int(
        manifest,
        (("evidence_closed_item_count",), ("counts", "evidence_closed_items"), ("counts", "closed_items")),
    )
    explicit_open = _nested_int(
        manifest,
        (("evidence_open_item_count",), ("counts", "evidence_open_items"), ("counts", "open_items")),
    )
    closed_count = explicit_closed if explicit_closed is not None else (closed_record_count if records else None)
    open_count = explicit_open if explicit_open is not None else (
        len(records) - closed_record_count if records else None
    )
    full_scope = _explicit_full_scope(manifest)
    strict_pass = _strict_pass(manifest)
    human_review = _human_review_required(manifest)
    status_values = [manifest.get("status"), manifest.get("scope_status"), manifest.get("source_fidelity_status")]
    closed_status = any(isinstance(value, str) and value.strip().upper() in _CLOSED_STATUSES for value in status_values)

    if not full_scope:
        findings.append(_finding("SCOPE_FULL_SOURCE_UNDECLARED", "Full-source scope closure is not explicitly declared.", subject=subject_label))
    if not strict_pass:
        findings.append(_finding("SCOPE_STRICT_PASS_REQUIRED", "strict_pass=true is required for source promotion.", subject=subject_label))
    if human_review:
        findings.append(_finding("SCOPE_HUMAN_REVIEW_REQUIRED", "Human review gates remain open in the source manifest.", subject=subject_label))
    if not closed_status:
        findings.append(_finding("SCOPE_STATUS_NOT_CLOSED", "Source manifest status is not an explicit full-source closed status.", subject=subject_label))
    if declared is None:
        findings.append(_finding("SCOPE_DECLARED_COUNT_MISSING", "No authoritative full-source item denominator is present.", subject=subject_label))
    if declared is not None and declared > 0 and not records:
        findings.append(_finding("SCOPE_ITEM_RECORDS_REQUIRED", "Item-level source evidence records are required for every declared source item.", subject=subject_label))
    if declared is not None and records and len(records) != declared:
        findings.append(_finding("SCOPE_ITEM_COUNT_MISMATCH", f"{len(records)} item records do not equal declared source count {declared}.", subject=subject_label))
    if closed_count is None or (declared is not None and closed_count != declared):
        findings.append(_finding("SCOPE_EVIDENCE_CLOSURE_MISSING", "Closed source evidence does not cover the authoritative denominator.", subject=subject_label))
    if open_count is None or open_count != 0:
        findings.append(_finding("SCOPE_EVIDENCE_OPEN", "Source evidence still has unknown or open items.", subject=subject_label))
    if declared is not None and declared > 0 and records and closed_record_count != len(records):
        findings.append(_finding("SCOPE_ITEM_EVIDENCE_INVALID", "One or more item records lack complete source coordinates, crop hash, and review id.", subject=subject_label))
    record_ids = [_record_id(record) for record in records]
    if any(value is None for value in record_ids):
        findings.append(_finding("SCOPE_ITEM_ID_MISSING", "Every item record needs a stable source item identity.", subject=subject_label))
    if len(set(value for value in record_ids if value is not None)) != len([value for value in record_ids if value is not None]):
        findings.append(_finding("SCOPE_ITEM_ID_DUPLICATE", "Source item identities must be unique within a manifest.", subject=subject_label))
    if len(source_documents) < 2:
        findings.append(_finding("SCOPE_SOURCE_DOCUMENTS_INCOMPLETE", "Problem and solution source-document provenance is required.", subject=subject_label))
    else:
        bad_documents = [
            index + 1
            for index, document in enumerate(source_documents)
            if not _document_hash(document) or not (_document_pages(document) and _document_pages(document) > 0)
        ]
        if bad_documents:
            findings.append(_finding("SCOPE_SOURCE_DOCUMENT_EVIDENCE_INVALID", f"Invalid source document evidence at entries {bad_documents}.", subject=subject_label))

    return {
        "subject": subject_label,
        "path": path,
        "declared_item_count": declared,
        "scope_item_count": scope_count,
        "item_record_count": len(records) if records else None,
        "evidence_closed_item_count": closed_count,
        "evidence_open_item_count": open_count,
        "source_document_count": len(source_documents),
        "full_source_scope": full_scope,
        "strict_pass": strict_pass,
        "human_review_required": human_review,
        "status": next((value for value in status_values if isinstance(value, str)), None),
        "closure_eligible": not findings,
        "findings": findings,
    }


def _summary_file_hashes(summary: Mapping[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    files = summary.get("files")
    if not isinstance(files, list):
        return result
    for item in files:
        if not isinstance(item, Mapping):
            continue
        subject = item.get("subject")
        name = item.get("name")
        sha = item.get("sha256")
        if isinstance(subject, str) and isinstance(name, str) and _is_sha256(sha):
            result[f"{subject}\0{name}"] = str(sha).lower()
    return result


def _row_file_hashes(row: Mapping[str, Any]) -> Mapping[str, Any]:
    hashes = row.get("output_hashes")
    return hashes if isinstance(hashes, Mapping) else {}


def _row_subject(row: Mapping[str, Any]) -> str | None:
    value = row.get("subject")
    return value if isinstance(value, str) else None


def _row_role(row: Mapping[str, Any]) -> str | None:
    """Return the document role represented by a COM row.

    New reports should carry an explicit ``role``.  For compatibility with
    the existing readback report, infer it from the output filename only when
    it is unambiguous.  A subject-only row is not sufficient to prove that
    the three required documents were all tested.
    """

    value = row.get("role")
    if isinstance(value, str) and value.strip():
        return value.strip()
    hashes = _row_file_hashes(row)
    names = [str(key) for key in hashes if isinstance(key, str) and ".readback." not in key.lower()]
    candidates: set[str] = set()
    for name in names:
        stem = Path(name).stem
        if "미주작업_완료" in stem or "미주" in stem:
            candidates.add("미주작업_완료")
        elif "정답및풀이" in stem or "해설" in stem or "풀이" in stem:
            candidates.add("정답및풀이")
        elif "문제" in stem:
            candidates.add("문제")
    return next(iter(candidates)) if len(candidates) == 1 else None


def audit_com_provenance(report: Mapping[str, Any], *, summary: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Validate serial COM readback evidence and its package hash linkage."""

    findings: list[dict[str, Any]] = []
    if not isinstance(report, Mapping):
        return {"closure_eligible": False, "row_count": None, "hash_linked_rows": 0, "findings": [_finding("COM_SCHEMA_INVALID", "COM report must be a JSON object.")]}
    status = report.get("status")
    schema = report.get("schema")
    rows = report.get("rows")
    rows = rows if isinstance(rows, list) else []
    expected_count = _as_int(report.get("count"))
    pass_count = _as_int(report.get("pass_count"))
    fail_count = _as_int(report.get("fail_count"))
    if not isinstance(schema, str) or not schema.startswith("hwp-dispatchex-serial-readback"):
        findings.append(_finding("COM_SCHEMA_INVALID", "COM report schema must identify serial readback evidence."))
    if not isinstance(status, str) or status.upper() != "PASS":
        findings.append(_finding("COM_STATUS_NOT_PASS", "COM report status is not PASS."))
    if expected_count != len(rows) or expected_count != 12:
        findings.append(_finding("COM_ROW_COUNT_INVALID", "Exactly 12 COM rows (three roles per subject) are required."))
    if pass_count != len(rows) or fail_count != 0:
        findings.append(_finding("COM_ROW_STATUS_INVALID", "Every COM row must pass and fail_count must be zero."))

    subject_counts = Counter(_row_subject(row) for row in rows if isinstance(row, Mapping))
    if set(subject_counts) != set(REQUIRED_SUBJECTS) or any(subject_counts.get(subject, 0) != 3 for subject in REQUIRED_SUBJECTS):
        findings.append(_finding("COM_SUBJECT_ROLE_SET_INVALID", "COM evidence must contain exactly three rows for each required subject."))

    roles_by_subject: dict[str, list[str | None]] = {subject: [] for subject in REQUIRED_SUBJECTS}
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        row_subject = _row_subject(row)
        if row_subject in roles_by_subject:
            roles_by_subject[row_subject].append(_row_role(row))
    required_roles = {"문제", "정답및풀이", "미주작업_완료"}
    for subject, roles in roles_by_subject.items():
        if set(roles) != required_roles or len(roles) != len(required_roles):
            findings.append(_finding("COM_ROLE_SET_INVALID", f"COM evidence for {subject} must contain exactly one 문제, 정답및풀이, and 미주작업_완료 row.", subject=subject))

    summary_hashes = _summary_file_hashes(summary or {})
    hash_linked = 0
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            findings.append(_finding("COM_ROW_INVALID", f"COM row {index + 1} is not an object."))
            continue
        row_subject = _row_subject(row)
        row_hashes = _row_file_hashes(row)
        before = row.get("input_sha256_before")
        after = row.get("input_sha256_after")
        if not (_is_sha256(before) and _is_sha256(after) and str(before).lower() == str(after).lower()):
            findings.append(_finding("COM_INPUT_HASH_NOT_STABLE", f"COM row {index + 1} input hash is missing or changed."))
        if str(row.get("status", "")).upper() != "PASS":
            findings.append(_finding("COM_ROW_NOT_PASS", f"COM row {index + 1} status is not PASS."))
        sessions = row.get("sessions")
        sessions = sessions if isinstance(sessions, list) else []
        labels = {session.get("label") for session in sessions if isinstance(session, Mapping)}
        if not {"write", "reopen"}.issubset(labels):
            findings.append(_finding("COM_SESSION_PAIR_MISSING", f"COM row {index + 1} must include write and reopen sessions."))
        for session in sessions:
            if not isinstance(session, Mapping):
                findings.append(_finding("COM_SESSION_INVALID", f"COM row {index + 1} contains a non-object session."))
                continue
            label = str(session.get("label", "session"))
            if session.get("register_module_return") is not True or session.get("open_return") is not True:
                findings.append(_finding("COM_SESSION_NOT_REGISTERED", f"COM row {index + 1} {label} lacks successful registration/open."))
            wait = _as_mapping(session.get("wait"))
            events = session.get("events")
            if not isinstance(events, list) or "dispatch_ex_ok" not in events or session.get("new_pids_exited") is not True or not wait or wait.get("status") != "OK" or wait.get("alive") != []:
                findings.append(_finding("COM_SESSION_LIFECYCLE_INCOMPLETE", f"COM row {index + 1} {label} lifecycle evidence is incomplete."))
            if label == "write" and any(session.get(key) is not True for key in ("save_hwp_return", "save_hwpx_return", "save_pdf_return")):
                findings.append(_finding("COM_WRITE_EXPORT_INCOMPLETE", f"COM row {index + 1} write session lacks all export confirmations."))
            if label == "reopen" and (session.get("readback_hwpx_return") is not True or session.get("readback_exists") is not True):
                findings.append(_finding("COM_REOPEN_READBACK_MISSING", f"COM row {index + 1} reopen session lacks HWPX readback."))
        approval_before = _as_mapping(row.get("approval_before"))
        approval_after = _as_mapping(row.get("approval_after"))
        if not approval_before or approval_before.get("status") != "OK" or not approval_after or approval_after.get("status") != "OK":
            findings.append(_finding("COM_APPROVAL_STATUS_INVALID", f"COM row {index + 1} approval status is not OK."))
        if _as_int(row.get("approval_window_count")) != 0:
            findings.append(_finding("COM_APPROVAL_WINDOW_OPENED", f"COM row {index + 1} has missing or non-zero approval-window evidence."))
        if row_subject and row_hashes:
            linked_this_row = False
            for extension in ("hwp", "hwpx"):
                output_entries = [
                    (str(key), value)
                    for key, value in row_hashes.items()
                    if isinstance(key, str)
                    and key.lower().endswith(f".{extension}")
                    and ".readback." not in key.lower()
                ]
                if len(output_entries) != 1 or not _is_sha256(output_entries[0][1]):
                    findings.append(_finding("COM_OUTPUT_HASH_MISSING", f"COM row {index + 1} has no valid {extension} output hash."))
                    continue
                output_name, output_sha = output_entries[0]
                expected = summary_hashes.get(f"{row_subject}\0{Path(output_name).name}")
                if summary_hashes and expected != str(output_sha).lower():
                    findings.append(_finding("COM_PACKAGE_HASH_MISMATCH", f"COM row {index + 1} {extension} hash is not linked to a package file."))
                else:
                    linked_this_row = True
            if linked_this_row:
                hash_linked += 1

    if summary_hashes and hash_linked < 12:
        findings.append(_finding("COM_PACKAGE_HASH_LINKAGE_INCOMPLETE", "All COM rows must link HWP/HWPX output hashes to the candidate summary."))
    return {
        "status": status,
        "row_count": len(rows),
        "hash_linked_rows": hash_linked,
        "closure_eligible": not findings,
        "findings": findings,
    }


def _load_json(path: str | Path) -> Mapping[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, Mapping):
        raise ValueError(f"JSON root is not an object: {path}")
    return value


def audit_delivery_summary(
    summary: Mapping[str, Any],
    *,
    scope_manifests: Mapping[str, Mapping[str, Any]] | None = None,
    manifest_paths: Mapping[str, str] | None = None,
    com_report: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Audit a candidate summary and return an independent promotion decision."""

    findings: list[dict[str, Any]] = []
    if not isinstance(summary, Mapping):
        return {"schema": SCHEMA_VERSION, "status": "FAIL", "final": False, "promotion_allowed": False, "findings": [_finding("SUMMARY_SCHEMA_INVALID", "Delivery summary must be a JSON object.")]}

    summary_schema_ok = summary.get("schema") == SUMMARY_SCHEMA
    if not summary_schema_ok:
        findings.append(_finding("SUMMARY_SCHEMA_INVALID", f"Expected schema {SUMMARY_SCHEMA}."))
    subjects_seen: set[str] = set()
    structural = _as_mapping(summary.get("structural_audit")) or {}
    structural_subjects = _as_mapping(structural.get("subjects")) or {}
    endnote = _as_mapping(summary.get("integrated_endnote_audit")) or {}
    endnote_subjects = _as_mapping(endnote.get("subjects")) or {}
    files = summary.get("files")
    if not isinstance(files, list) or not files:
        findings.append(_finding("SUMMARY_FILES_REQUIRED", "A non-empty candidate package file list is required for promotion."))
    else:
        subjects_seen.update(item.get("subject") for item in files if isinstance(item, Mapping) and isinstance(item.get("subject"), str))
        if not all(
            isinstance(item, Mapping)
            and isinstance(item.get("subject"), str)
            and isinstance(item.get("name"), str)
            and bool(item.get("name").strip())
            and _is_sha256(item.get("sha256"))
            for item in files
        ):
            findings.append(_finding("SUMMARY_FILE_HASH_INVALID", "Every candidate package file entry needs subject, name, and valid SHA-256."))
        file_keys = [
            (item.get("subject"), item.get("name"))
            for item in files
            if isinstance(item, Mapping) and isinstance(item.get("subject"), str) and isinstance(item.get("name"), str)
        ]
        if len(file_keys) != len(set(file_keys)):
            findings.append(_finding("SUMMARY_FILE_DUPLICATE", "Candidate package file entries must be unique by subject and name."))
        expected_roles = {"문제", "정답및풀이", "미주작업_완료"}
        expected_extensions = {"hwp", "hwpx"}
        for subject in REQUIRED_SUBJECTS:
            subject_files = [str(name) for owner, name in file_keys if owner == subject]
            roles = {
                role
                for name in subject_files
                for role in expected_roles
                if role in Path(name).stem
            }
            extensions = {Path(name).suffix.lower().lstrip(".") for name in subject_files}
            if len(subject_files) != 6 or roles != expected_roles or extensions != expected_extensions:
                findings.append(_finding("SUMMARY_FILE_ROLE_SET_INVALID", f"Candidate package for {subject} must contain exactly six files: 문제, 정답및풀이, 미주작업_완료 in both HWP and HWPX.", subject=subject))
    subjects_seen.update(key for key in structural_subjects if isinstance(key, str))
    subjects_seen.update(key for key in endnote_subjects if isinstance(key, str))
    if subjects_seen != set(REQUIRED_SUBJECTS):
        findings.append(_finding("SUMMARY_SUBJECT_SET_INVALID", "Summary must cover exactly the four required subjects."))
    if str(structural.get("status", "")).upper() != "PASS":
        findings.append(_finding("SUMMARY_STRUCTURAL_AUDIT_NOT_PASS", "Structural audit is not PASS."))
    if str(endnote.get("status", "")).upper() != "PASS":
        findings.append(_finding("SUMMARY_ENDNOTE_AUDIT_NOT_PASS", "Integrated endnote audit is not PASS."))

    observed_endnotes: dict[str, int | None] = {}
    for subject in REQUIRED_SUBJECTS:
        item = _as_mapping(endnote_subjects.get(subject)) or {}
        endnotes = _as_int(item.get("endnotes"))
        autonum = _as_int(item.get("autonum"))
        empty = _as_int(item.get("empty"))
        observed_endnotes[subject] = endnotes
        if endnotes is None or autonum is None or endnotes != autonum or empty != 0:
            findings.append(_finding("SUMMARY_ENDNOTE_COUNT_INVALID", f"{subject} endnote/autonum/empty-body counts are not closed.", subject=subject))

    scope_reports: dict[str, dict[str, Any]] = {}
    if scope_manifests is None:
        findings.append(_finding("SCOPE_MANIFESTS_REQUIRED", "Four source scope manifests are required for full-source promotion."))
    else:
        if set(scope_manifests) != set(REQUIRED_SUBJECTS):
            findings.append(_finding("SCOPE_MANIFEST_SUBJECT_SET_INVALID", "Exactly one source scope manifest is required per subject."))
        for subject in REQUIRED_SUBJECTS:
            manifest = scope_manifests.get(subject)
            scope_reports[subject] = audit_scope_manifest(manifest or {}, subject=subject, path=(manifest_paths or {}).get(subject))
            findings.extend(scope_reports[subject]["findings"])

    source_fidelity = _as_mapping(summary.get("source_fidelity")) or {}
    source_status = str(source_fidelity.get("status", "")).upper()
    if source_status != "PASS" and source_status not in _CLOSED_STATUSES:
        findings.append(_finding("SUMMARY_SOURCE_FIDELITY_OPEN", "Source fidelity is not explicitly closed."))
    notes = str(source_fidelity.get("notes", "")).upper()
    if any(word in notes for word in ("OPEN", "REMAINS", "NOT SOURCE CLOSURE", "SELECTED")):
        findings.append(_finding("SUMMARY_SOURCE_FIDELITY_NOTE_OPEN", "Source-fidelity notes describe selected or open scope."))
    if str(summary.get("release_status", "")).upper() != "FINAL":
        findings.append(_finding("SUMMARY_RELEASE_NOT_FINAL", "Candidate summary is not independently marked FINAL." , blocking=False))

    declared_total: int | None = 0 if scope_reports and all(report.get("declared_item_count") is not None for report in scope_reports.values()) else None
    closed_total: int | None = 0 if scope_reports and all(report.get("evidence_closed_item_count") is not None for report in scope_reports.values()) else None
    if declared_total is not None:
        declared_total = sum(int(report["declared_item_count"]) for report in scope_reports.values())
    if closed_total is not None:
        closed_total = sum(int(report["evidence_closed_item_count"]) for report in scope_reports.values())
    observed_total = sum(value for value in observed_endnotes.values() if value is not None)
    if scope_reports and all(report.get("closure_eligible") for report in scope_reports.values()):
        for subject in REQUIRED_SUBJECTS:
            if observed_endnotes.get(subject) != scope_reports[subject].get("declared_item_count"):
                findings.append(_finding("ENDNOTE_SOURCE_COUNT_MISMATCH", "Observed endnotes do not equal the closed full-source denominator.", subject=subject))
    else:
        findings.append(_finding("ENDNOTE_COUNT_NOT_SOURCE_CLOSURE", "Endnote counts are package observations only until every source manifest is closed."))

    com_result: dict[str, Any]
    if com_report is None:
        com_result = {"closure_eligible": False, "row_count": None, "hash_linked_rows": 0, "findings": [_finding("COM_REPORT_REQUIRED", "COM provenance report is required for full-source promotion.")]}
    else:
        com_result = audit_com_provenance(com_report, summary=summary)
        findings.extend(com_result["findings"])

    # A summary's own final flag and top-level PASS are claims, not evidence.
    if summary.get("final") is True and findings:
        findings.append(_finding("SUMMARY_FINAL_CLAIM_REJECTED", "Summary final=true is ignored when an independent gate is blocked."))

    blocking = [item for item in findings if item.get("blocking") is True]
    promotion_allowed = not blocking
    return {
        "schema": SCHEMA_VERSION,
        "status": "PASS" if promotion_allowed else "BLOCKED",
        "final": promotion_allowed,
        "promotion_allowed": promotion_allowed,
        "gates": {
            "summary_schema": summary_schema_ok,
            "exact_subject_set": subjects_seen == set(REQUIRED_SUBJECTS),
            "structural_audit": str(structural.get("status", "")).upper() == "PASS",
            "integrated_endnote_audit": str(endnote.get("status", "")).upper() == "PASS",
            "source_scope_closed": bool(scope_reports) and all(report.get("closure_eligible") for report in scope_reports.values()),
            "endnote_counts_reconciled": bool(scope_reports) and all(report.get("closure_eligible") for report in scope_reports.values()) and declared_total == observed_total,
            "com_provenance_closed": bool(com_result.get("closure_eligible")),
            "candidate_files_hashed": isinstance(files, list) and bool(files) and all(
                isinstance(item, Mapping)
                and isinstance(item.get("subject"), str)
                and isinstance(item.get("name"), str)
                and _is_sha256(item.get("sha256"))
                for item in files
            ),
        },
        "subjects": scope_reports,
        "com": com_result,
        "counts": {
            "observed_integrated_endnotes": observed_total,
            "declared_full_source_items": declared_total,
            "evidence_closed_source_items": closed_total,
        },
        "findings": findings,
    }


def audit_delivery_summary_path(
    summary_path: str | Path,
    *,
    scope_manifest_paths: Mapping[str, str | Path] | None = None,
    com_report_path: str | Path | None = None,
) -> dict[str, Any]:
    """Load a summary and evidence files read-only, then run the gate."""

    summary = _load_json(summary_path)
    manifests: dict[str, Mapping[str, Any]] | None = None
    manifest_paths: dict[str, str] = {}
    if scope_manifest_paths is not None:
        manifests = {}
        for subject, path in scope_manifest_paths.items():
            manifests[subject] = _load_json(path)
            manifest_paths[subject] = str(path)
    com_report = _load_json(com_report_path) if com_report_path is not None else None
    return audit_delivery_summary(summary, scope_manifests=manifests, manifest_paths=manifest_paths, com_report=com_report)


__all__ = [
    "REQUIRED_SUBJECTS",
    "SCHEMA_VERSION",
    "SUMMARY_SCHEMA",
    "audit_com_provenance",
    "audit_delivery_summary",
    "audit_delivery_summary_path",
    "audit_scope_manifest",
]
