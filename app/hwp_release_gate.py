"""Fail-closed release state and promotion gate for HWP/HWPX artifacts.

The gate deliberately separates structural generation from semantic release.
It is safe to use on candidate artifacts without opening Hanword or mutating
the source document.
"""

from __future__ import annotations

import json
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


def evaluate_release(status: Mapping[str, Any]) -> dict[str, Any]:
    """Return a copy with a fail-closed status and final flag.

    No status is promoted when any gate is absent/false, an evidence finding is
    present, or placeholder text is found.  A caller must supply all evidence
    explicitly; this function never infers a pass from file existence/counts.
    """

    result = dict(status)
    findings = list(result.get("findings") or [])
    placeholder = _contains_placeholder(result)
    if placeholder and not any(f.get("code") == "PLACEHOLDER_CONTENT" for f in findings if isinstance(f, Mapping)):
        findings.append({"code": "PLACEHOLDER_CONTENT", "token": placeholder})
    result["findings"] = findings
    gates_pass = all(result.get(field) is True for field in GATE_FIELDS)
    result["final"] = bool(
        result.get("generated") is True
        and gates_pass
        and not findings
        and bool(result.get("hwp_sha256"))
        and bool(result.get("hwpx_sha256"))
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
