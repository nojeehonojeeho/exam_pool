"""Build an auditable v2 execution report from a subject state directory.

The report deliberately keeps raw findings, deterministic root-cause
candidates, and release blockers separate.  It derives evidence-open from
the persisted closure summary and never treats a historical scope-minus-
legacy value such as ``291`` as the current result.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


METRIC_KEYS = (
    "scope_item_count", "inventory_item_count", "reconstructed_item_count",
    "legacy_reviewed_scope_count", "evidence_closed_item_count",
    "evidence_open_item_count", "formula_bearing_item_count",
    "source_formula_occurrence_count", "mathir_occurrence_count",
    "writer_formula_occurrence_count", "saved_hwpx_equation_count",
    "reopened_equation_count", "raw_finding_count", "unique_root_cause_count",
    "blocking_item_count", "release_blocker_count",
)


def _read_json(path: Path, default: Any) -> Any:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _flatten_queue(queue: dict[str, Any]) -> list[dict[str, Any]]:
    groups = queue.get("groups") or {}
    rows: list[dict[str, Any]] = []
    if isinstance(groups, dict):
        for key, members in groups.items():
            if isinstance(members, list):
                rows.extend({"group_key": str(key), **m} for m in members if isinstance(m, dict))
    elif isinstance(groups, list):
        rows.extend(m for m in groups if isinstance(m, dict))
    return rows


def _queue_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row.get("group_key") or "ungrouped")].append(row)
    groups: list[dict[str, Any]] = []
    for key in sorted(grouped):
        members = grouped[key]
        groups.append({
            "group_key": key,
            "item_count": len({str(m.get("item_id")) for m in members if m.get("item_id")}),
            "source_pages": sorted({m.get("source_page") for m in members if m.get("source_page") is not None}),
            "chapters": sorted({str(m.get("chapter")) for m in members if m.get("chapter")}),
            "statuses": dict(Counter(str(m.get("status") or "UNKNOWN") for m in members)),
            "root_causes": sorted({str(rc) for m in members for rc in (m.get("root_causes") or [])}),
            "release_eligible": False,
        })
    return {"group_count": len(groups), "item_count": len({str(r.get('item_id')) for r in rows if r.get('item_id')}), "groups": groups}


def _legacy_revalidation(rows: list[dict[str, Any]], legacy_count: int) -> dict[str, Any]:
    legacy = [r for r in rows if r.get("status") == "revalidate_legacy_subset" and r.get("item_id")]
    ids = {str(r["item_id"]) for r in legacy}
    if not ids:
        return {"status": "NOT_AVAILABLE", "scope_count": legacy_count, "v2_evidence_closed_count": 0,
                "v2_evidence_open_count": legacy_count, "pass_count": None, "fail_count": None,
                "note": "No explicit legacy revalidation rows; do not infer pass/fail."}
    closed = {str(r["item_id"]) for r in legacy if r.get("v2_status") == "CLOSED" or r.get("evidence_status") == "CLOSED"}
    return {"status": "MEASURED", "scope_count": len(ids), "v2_evidence_closed_count": len(closed),
            "v2_evidence_open_count": len(ids - closed), "pass_count": len(closed),
            "fail_count": len(ids - closed), "note": "Only explicit v2 closure counts; legacy VERIFIED is not promoted."}


def build_execution_report(state_dir: Path) -> dict[str, Any]:
    closure = _read_json(state_dir / "evidence-closure-summary.json", {})
    roots = _read_json(state_dir / "root-cause-summary.json", {})
    queue = _read_json(state_dir / "work-queue.json", {})
    build = _read_json(state_dir / "build-and-qa.json", {})
    strict_rows = _read_jsonl(state_dir / "strict-findings.jsonl")
    aliases = {
        "formula_bearing_item_count": "formula_bearing_item_count_observed",
        "source_formula_occurrence_count": "source_formula_occurrence_count_observed",
    }
    metrics = {
        key: _int(closure.get(key, closure.get(aliases.get(key, ""), 0)))
        for key in METRIC_KEYS
    }
    # Some persisted strict ledgers use one aggregate row per root cause and
    # carry the number of raw findings in that row.  Count the weighted rows,
    # not just the number of lines; keep line count separately in the report.
    weighted_strict_count = sum(
        _int(row.get("raw_finding_count")) if row.get("aggregate_record") else 1
        for row in strict_rows
    )
    if strict_rows and weighted_strict_count:
        metrics["raw_finding_count"] = weighted_strict_count

    root_groups = roots.get("groups") or []
    formula_groups = [
        g for g in root_groups if isinstance(g, dict) and (
            str(g.get("area") or g.get("category") or "").lower() in
            {"formula", "formula-source-evidence", "formula-authoring-contract"}
            or str(g.get("rule_id") or "").startswith("FORMULA")
        )
    ]
    top_roots = sorted(formula_groups, key=lambda g: (-_int(g.get("raw_finding_count")), str(g.get("root_cause_id") or "")))[:20]
    rows = _flatten_queue(queue)
    final_pass = (
        metrics["evidence_open_item_count"] == 0 and metrics["raw_finding_count"] == 0
        and metrics["release_blocker_count"] == 0 and metrics["blocking_item_count"] == 0
        and str(build.get("status") or "").upper() == "PASS"
    )
    required = {name: (state_dir / name).exists() for name in (
        "strict-findings.jsonl", "root-cause-summary.json", "evidence-closure-summary.json",
        "formula-occurrence-ledger.jsonl", "problem-solution-linkage.json", "work-queue.json", "build-and-qa.json")}
    return {
        "schema": "highend-v2-execution-report-v1",
        "status": "FINAL_PASS" if final_pass else "REVIEW_REQUIRED",
        "metrics": metrics,
        "legacy_revalidation": _legacy_revalidation(rows, metrics["legacy_reviewed_scope_count"]),
        "strict_rerun": {"status": str(build.get("status") or "UNKNOWN"), "stage": build.get("stage"),
                         "raw_ledger_rows": len(strict_rows), "weighted_raw_finding_count": weighted_strict_count,
                         "release_blocker_count": metrics["release_blocker_count"]},
        "root_cause_top20_formula": top_roots,
        "work_queue": _queue_summary(rows),
        "required_files": required,
        "final_pass": final_pass,
        "notes": [
            "291 is a historical scope-minus-legacy reference only; evidence_open_item_count is measured.",
            "Root-cause grouping is diagnostic and never deletes findings or promotes PASS.",
            "Legacy VERIFIED labels are not latest-v2 closure evidence.",
        ],
    }


def _markdown(report: dict[str, Any]) -> str:
    lines = ["# v2 execution report", "", f"- status: **{report['status']}**", f"- final_pass: `{report['final_pass']}`", "", "## Metrics", "", "| field | value |", "|---|---:|"]
    lines.extend(f"| `{k}` | {v} |" for k, v in report["metrics"].items())
    lines += ["", "## Legacy v2 revalidation", "", f"`{json.dumps(report['legacy_revalidation'], ensure_ascii=False)}`", "", "## Formula root-cause candidates (top 20)", "", "| root cause | area | raw findings | resolved |", "|---|---|---:|---|"]
    lines.extend(f"| `{g.get('root_cause_id')}` | {g.get('area') or g.get('category')} | {_int(g.get('raw_finding_count'))} | {bool(g.get('resolved', False))} |" for g in report["root_cause_top20_formula"])
    lines += ["", "## Queue groups", "", f"- groups: `{report['work_queue']['group_count']}`", f"- items: `{report['work_queue']['item_count']}`"]
    lines.extend(f"- `{g['group_key']}`: {g['item_count']} items, pages={g['source_pages']}, status={g['statuses']}" for g in report["work_queue"]["groups"])
    lines += ["", "## Notes", ""] + [f"- {n}" for n in report["notes"]]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Build an auditable HIGH-END v2 execution report")
    parser.add_argument("state_dir", type=Path)
    parser.add_argument("--json", type=Path, required=True)
    parser.add_argument("--md", type=Path)
    args = parser.parse_args()
    report = build_execution_report(args.state_dir)
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.md:
        args.md.parent.mkdir(parents=True, exist_ok=True)
        args.md.write_text(_markdown(report), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
