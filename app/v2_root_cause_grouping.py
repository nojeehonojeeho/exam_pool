"""Conservative grouping of v2 findings by candidate root cause.

Grouping is diagnostic only. It never deletes findings or changes release
status. Each group retains raw finding indexes and requires source evidence
before it can be considered resolved.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


_PATH_INDEX = re.compile(r"/(?:segments|cells|components)/(\d+)")


def _anchor(path: str) -> str:
    text = str(path or "")
    match = _PATH_INDEX.search(text)
    if match:
        return text[: match.end()]
    return text.split("/", 2)[0] if text else "root"


def _category(code: str) -> str:
    code = str(code or "UNKNOWN")
    if code in {"DIALECT_REQUIRED", "FORMULA_MARKUP_IN_TEXT", "FORMULA_UNTYPED_CELL", "PIECEWISE_NATIVE_REQUIRED"}:
        return "formula-authoring-contract"
    if code in {"SOURCE_BBOX_UNVERIFIED", "FORMULA_OCCURRENCE_UNVERIFIED", "MATHIR_EVIDENCE_MISSING"}:
        return "formula-source-evidence"
    if code in {"FIGURE_ASSET_MISSING", "FIGURE_NOT_APPROVED", "FIGURE_ASSET_HASH_MISMATCH", "FIGURE_DESCRIPTION_REPLACEMENT"}:
        return "figure-evidence"
    if code in {"NATIVE_PARAGRAPH_REQUIRED", "AUTHORING_UNCONSUMED_CONTENT", "AUTHORING_UNKNOWN_FIELD"}:
        return "content-consumption"
    if code in {"SOLUTION_DECLARED_COUNT_MISMATCH", "ITEM_SET_OR_ORDER_MISMATCH"}:
        return "item-solution-linkage"
    return code.lower()


def _document_role(finding: dict[str, Any], path: str) -> str:
    explicit = finding.get("document_role") or finding.get("role")
    if explicit:
        return str(explicit)
    head = path.split("/", 1)[0] if path else ""
    if head.endswith("_blocks"):
        return head.removesuffix("_blocks")
    return "unknown"


def _stage(finding: dict[str, Any], code: str) -> str:
    explicit = finding.get("stage")
    if explicit:
        return str(explicit)
    if code.startswith("SOURCE_") or "OCCURRENCE" in code or "MATHIR" in code:
        return "source-evidence"
    if code.startswith("AUTHORING_") or code in {"DIALECT_REQUIRED", "FORMULA_MARKUP_IN_TEXT", "FORMULA_UNTYPED_CELL", "PIECEWISE_NATIVE_REQUIRED"}:
        return "authoring"
    if code.startswith("FIGURE_"):
        return "figure-evidence"
    if code.startswith("SOLUTION_") or "ITEM_SET" in code:
        return "linkage"
    return "unknown"


def _evidence_key(finding: dict[str, Any], category: str, anchor: str) -> str:
    explicit = finding.get("evidence_key")
    if explicit:
        return str(explicit)
    # Keep the legacy path anchor as a deterministic fallback when a finding
    # predates explicit evidence keys.  It is never treated as proof of
    # resolution; it only prevents run-to-run group ID drift.
    return f"{category}:{anchor}"


def group_findings(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str, str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for index, finding in enumerate(findings):
        item = str(finding.get("item_id") or "GLOBAL")
        category = _category(finding.get("code"))
        path = str(finding.get("path") or "root")
        anchor = _anchor(path)
        code = str(finding.get("code") or "UNKNOWN")
        document_role = _document_role(finding, path)
        stage = _stage(finding, code)
        evidence_key = _evidence_key(finding, category, anchor)
        source_hash = str(finding.get("source_hash") or "unknown")
        groups[(document_role, item, stage, evidence_key, source_hash)].append(
            {"raw_finding_index": index, "_category": category, "_anchor": anchor, **finding}
        )

    result: list[dict[str, Any]] = []
    for document_role, item, stage, evidence_key, source_hash in sorted(groups):
        members = groups[(document_role, item, stage, evidence_key, source_hash)]
        categories = sorted({str(m.get("_category") or _category(m.get("code"))) for m in members})
        anchors = sorted({str(m.get("_anchor") or "root") for m in members})
        result.append(
            {
                "root_cause_id": "|".join((document_role, item, stage, evidence_key, source_hash)),
                "candidate_only": True,
                "resolved": False,
                "document_role": document_role,
                "item_id": item,
                "stage": stage,
                "evidence_key": evidence_key,
                "source_hash": source_hash,
                # Legacy consumers may still read a single category/anchor;
                # retain them when the deterministic key contains one value.
                "category": categories[0] if len(categories) == 1 else "mixed",
                "anchor": anchors[0] if len(anchors) == 1 else "mixed",
                "categories": categories,
                "anchors": anchors,
                "raw_finding_count": len(members),
                "raw_finding_indices": [m["raw_finding_index"] for m in members],
                "codes": dict(Counter(str(m.get("code") or "UNKNOWN") for m in members)),
            }
        )
    return result


def summarize(report: dict[str, Any]) -> dict[str, Any]:
    findings = report.get("findings") or []
    groups = group_findings(findings)
    items = {str(f.get("item_id")) for f in findings if f.get("item_id")}
    return {
        "schema": "v2-root-cause-summary-1",
        "status": "DIAGNOSTIC_ONLY",
        "raw_finding_count": len(findings),
        "unique_root_cause_candidate_count": len(groups),
        "finding_item_count": len(items),
        "evidence_closed_item_count": report.get("evidence_closed_item_count"),
        "evidence_open_item_count": report.get("evidence_open_item_count"),
        "release_blocker_count": len(findings),
        "groups": groups,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    report = json.loads(args.report.read_text(encoding="utf-8"))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(summarize(report), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
