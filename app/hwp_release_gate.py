"""Fail-closed release state and promotion gate for HWP/HWPX artifacts.

The gate deliberately separates structural generation from semantic release.
It is safe to use on candidate artifacts without opening Hanword or mutating
the source document.
"""

from __future__ import annotations

import json
import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


PROFILE_NAME = "수능완성_수학_문제해설_미주_기본서식_v1"
GATE_FIELDS = (
    "reopen_pass",
    "content_pass",
    "equation_pass",
    "endnote_pass",
    "style_pass",
    "visual_pass",
)
PLACEHOLDER_TOKENS = (
    "원문 검토됨",
    "후속 전사 필요",
    "전사 예정",
    "OCR 확인 필요",
    "placeholder",
    "pending",
    "TODO",
    "FIXME",
    "source raster",
    "추후 입력",
)
_SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_status(
    *,
    document: str,
    source_document: str,
    source_sha256: str = "",
    hwp_sha256: str = "",
    hwpx_sha256: str = "",
    page_count: int = 0,
    problem_count: int = 0,
    solution_count: int = 0,
    equation_count: int = 0,
    endnote_reference_count: int = 0,
    endnote_body_count: int = 0,
    generated: bool = False,
    findings: list[dict[str, Any]] | None = None,
    evidence_files: list[str] | None = None,
    evidence_root: str = "",
    code_commit_sha: str = "",
) -> dict[str, Any]:
    """Create the canonical status object; all release gates start false."""

    return {
        "document": document,
        "source_document": source_document,
        "artifact_class": "CANDIDATE",
        "status": "GENERATED" if generated else "CANDIDATE",
        "profile": PROFILE_NAME,
        "generated": bool(generated),
        **{field: False for field in GATE_FIELDS},
        "final": False,
        "source_sha256": source_sha256,
        "hwp_sha256": hwp_sha256,
        "hwpx_sha256": hwpx_sha256,
        "page_count": int(page_count),
        "problem_count": int(problem_count),
        "solution_count": int(solution_count),
        "equation_count": int(equation_count),
        "endnote_reference_count": int(endnote_reference_count),
        "endnote_body_count": int(endnote_body_count),
        "findings": list(findings or []),
        "evidence_files": list(evidence_files or []),
        "evidence_root": evidence_root,
        "checked_at": _now(),
        "code_commit_sha": code_commit_sha,
    }


def _contains_placeholder(value: Any) -> str | None:
    if isinstance(value, Mapping):
        for item in value.values():
            found = _contains_placeholder(item)
            if found:
                return found
    elif isinstance(value, (list, tuple)):
        for item in value:
            found = _contains_placeholder(item)
            if found:
                return found
    elif isinstance(value, str):
        lower = value.lower()
        for token in PLACEHOLDER_TOKENS:
            if token.lower() in lower:
                return token
    return None


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _resolve_evidence(status: Mapping[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Resolve and hash evidence files without trusting a status string.

    Evidence paths are relative to one explicit root.  An evidence entry may
    be a string or ``{"path": ..., "sha256": ...}``; a missing root, file,
    hash, or hash mismatch is a blocking finding.  This keeps old status files
    useful as candidates while preventing them from being promoted by merely
    naming an evidence file.
    """

    raw = status.get("evidence_files")
    if not isinstance(raw, (list, tuple)) or not raw:
        return [], [{"code": "EVIDENCE_FILES_MISSING", "blocking": True}]
    root_value = status.get("evidence_root")
    if not root_value:
        return [], [{"code": "EVIDENCE_ROOT_MISSING", "blocking": True}]
    root = Path(str(root_value)).expanduser()
    records: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    for entry in raw:
        if isinstance(entry, Mapping):
            relative = entry.get("path") or entry.get("relative_path")
            expected = str(entry.get("sha256") or "").lower()
        else:
            relative = entry
            expected = ""
        if not isinstance(relative, str) or not relative.strip():
            findings.append({"code": "EVIDENCE_PATH_INVALID", "blocking": True})
            continue
        path = (root / relative).resolve()
        try:
            path.relative_to(root.resolve())
        except ValueError:
            findings.append({"code": "EVIDENCE_PATH_OUTSIDE_ROOT", "path": relative, "blocking": True})
            continue
        if not path.is_file():
            findings.append({"code": "EVIDENCE_FILE_MISSING", "path": relative, "blocking": True})
            continue
        actual = _sha256_file(path)
        if not _SHA256.fullmatch(expected):
            findings.append({"code": "EVIDENCE_SHA256_MISSING", "path": relative, "blocking": True})
        elif actual != expected:
            findings.append({"code": "EVIDENCE_SHA256_MISMATCH", "path": relative, "expected": expected, "actual": actual, "blocking": True})
        records.append({"path": str(path), "relative_path": relative, "sha256": actual})
    return records, findings


def evaluate_release(status: Mapping[str, Any]) -> dict[str, Any]:
    """Return a copy with a fail-closed status and final flag.

    No status is promoted when any gate is absent/false, an evidence finding is
    present, or placeholder text is found.  A caller must supply all evidence
    explicitly; this function never infers a pass from file existence/counts.
    """

    result = dict(status)
    findings = list(result.get("findings") or [])
    evidence_records, evidence_findings = _resolve_evidence(result)
    findings.extend(evidence_findings)
    result["resolved_evidence"] = evidence_records
    findings.extend(_endnote_boundary_findings(result, evidence_records))
    placeholder = _contains_placeholder(result)
    if placeholder and not any(f.get("code") == "PLACEHOLDER_CONTENT" for f in findings if isinstance(f, Mapping)):
        findings.append({"code": "PLACEHOLDER_CONTENT", "token": placeholder})
    result["findings"] = findings
    gates_pass = all(result.get(field) is True for field in GATE_FIELDS)
    hwp_hash = str(result.get("hwp_sha256") or "").lower()
    hwpx_hash = str(result.get("hwpx_sha256") or "").lower()
    result["final"] = bool(
        result.get("generated") is True
        and gates_pass
        and not findings
        and _SHA256.fullmatch(hwp_hash)
        and _SHA256.fullmatch(hwpx_hash)
    )
    if result["final"]:
        result["status"] = "FINAL"
    elif findings:
        result["status"] = "BLOCKED" if any(f.get("blocking", True) for f in findings if isinstance(f, Mapping)) else "NEEDS_REVIEW"
    elif result.get("generated"):
        # Do not skip the ordered states: the first missing gate is the state
        # immediately before it, and an absent proof remains a review state.
        result["status"] = "NEEDS_REVIEW"
    else:
        result["status"] = "CANDIDATE"
    return result


def _endnote_boundary_findings(status: Mapping[str, Any], records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Native-note release cannot omit the physical new-page gate.

    Re-evaluate the report inputs instead of trusting an old JSON PASS. This is
    only the boundary gate; content/style/transfer/source evidence remains
    mandatory and independent. No COM process or document writer is called.
    """
    counts = (status.get("endnote_reference_count", 0), status.get("endnote_body_count", 0))
    required = status.get("document_role") in {"endnote", "integrated", "native_endnote"}
    required = required or any(value not in (0, None, "0") for value in counts)
    if not required:
        return []
    name = status.get("endnote_boundary_report")
    record = next((entry for entry in records if entry["relative_path"] == name), None)
    if record is None:
        return [{"code": "ENDNOTE_BOUNDARY_RELEASE_EVIDENCE_MISSING", "blocking": True}]
    try:
        report = json.loads(Path(record["path"]).read_text(encoding="utf-8-sig"))
        if report.get("schema") != "hwp-native-endnote-render-boundary-audit-v2":
            raise ValueError("legacy heuristic boundary reports cannot release a document")
        if report.get("input_sha256", {}).get("integrated_hwpx") != status.get("hwpx_sha256"):
            raise ValueError("boundary report is not bound to the delivered HWPX")
        from tools.audit_hwp_endnote_page_boundary import audit_endnote_page_boundary

        actual = audit_endnote_page_boundary(
            Path(report["problem_pdf"]), Path(report["integrated_pdf"]),
            Path(report["integrated_hwpx"]), Path(report["independent_review"]["review_path"]),
        )
        if actual["status"] != "PASS" or actual.get("input_sha256") != report.get("input_sha256"):
            raise ValueError("boundary inputs changed or independent review did not pass")
        if actual["independent_review"]["review_sha256"] != report["independent_review"]["review_sha256"]:
            raise ValueError("boundary review changed since the recorded audit")
        if report.get("status") != "PASS" or report.get("findings") != []:
            raise ValueError("recorded boundary audit did not pass")
    except (OSError, ValueError, KeyError, TypeError, AttributeError, ImportError) as exc:
        return [{"code": "ENDNOTE_BOUNDARY_RELEASE_EVIDENCE_INVALID", "blocking": True, "message": str(exc)}]
    return []


def write_status(path: str | Path, status: Mapping[str, Any]) -> dict[str, Any]:
    """Evaluate and atomically write a status JSON beside an artifact."""

    target = Path(path)
    evaluated = evaluate_release(status)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(target.name + ".tmp")
    tmp.write_text(json.dumps(evaluated, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(target)
    return evaluated


def can_promote_final(status: Mapping[str, Any]) -> bool:
    """Strict predicate used by packagers and tests."""

    return bool(evaluate_release(status).get("final") is True)


__all__ = [
    "GATE_FIELDS",
    "PROFILE_NAME",
    "can_promote_final",
    "evaluate_release",
    "new_status",
    "write_status",
]
