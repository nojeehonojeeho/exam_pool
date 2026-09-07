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


def group_findings(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for index, finding in enumerate(findings):
        item = str(finding.get("item_id") or "GLOBAL")
        category = _category(finding.get("code"))
        anchor = _anchor(str(finding.get("path") or "root"))
        groups[(item, category, anchor)].append({"raw_finding_index": index, **finding})

    result: list[dict[str, Any]] = []
    for item, category, anchor in sorted(groups):
        members = groups[(item, category, anchor)]
        result.append(
            {
                "root_cause_id": f"{item}|{category}|{anchor}",
                "candidate_only": True,
                "resolved": False,
                "item_id": item,
                "category": category,
                "anchor": anchor,
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
