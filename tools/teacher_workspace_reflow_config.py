"""Derive an evidence-bound workspace-reflow configuration without mutating it.

The original successful configuration remains immutable.  This helper creates
one new configuration whose only content/layout change is an explicit list of
questions that must start on a fresh physical page because rendered semantic
object endpoints proved their writing space insufficient.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.teacher_workflow import file_hash, write_json


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--workspace-evidence", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--output-name", default="workspace-reflow.hwpx")
    args = parser.parse_args()
    if args.out.exists():
        raise FileExistsError(args.out)
    config = json.loads(args.base.read_text(encoding="utf-8-sig"))
    evidence = json.loads(args.workspace_evidence.read_text(encoding="utf-8-sig"))
    rows_ref = evidence.get("rows_artifact", {})
    rows_path = Path(rows_ref.get("path", ""))
    if not rows_path.is_file() or file_hash(rows_path) != rows_ref.get("sha256"):
        raise ValueError("WORKSPACE_ROWS_EVIDENCE_HASH")
    rows = json.loads(rows_path.read_text(encoding="utf-8-sig"))
    shortfalls = [r for r in rows if r.get("status") == "REVIEW_REQUIRED"]
    failed_choices = [r for r in evidence.get("choice_layouts", []) if r.get("three_plus_two") is False]
    if not shortfalls and not failed_choices:
        raise ValueError("NO_WORKSPACE_SHORTFALLS")
    row_ids = [str(r["id"]) for r in rows]
    next_ids = {current: row_ids[index + 1] for index, current in enumerate(row_ids[:-1])}
    # A question which continues into a fresh page/column cannot gain writing
    # room by moving itself again: the next question must begin on a fresh
    # page, leaving the continuation tail and its workspace intact.  A question
    # ending at a physical bottom instead moves itself.  Retain earlier proven
    # breaks because removing them would reintroduce a previously fixed defect.
    requested = set(map(str, config.get("question_page_break_before_item_ids", [])))
    rationale: list[dict] = []
    for row in shortfalls:
        current = str(row["id"])
        if row.get("boundary_kind") == "next_question_marker_same_column":
            target = next_ids.get(current)
            if target is None:
                raise ValueError("WORKSPACE_SHORTFALL_HAS_NO_NEXT_ITEM")
            rationale.append({"shortfall_id": current, "break_before_id": target, "reason": "continuation_tail_requires_following_question_page_break"})
        else:
            target = current
            rationale.append({"shortfall_id": current, "break_before_id": target, "reason": "physical_bottom_shortfall_requires_item_page_break"})
        requested.add(target)
    for choice in failed_choices:
        positions = choice.get("positions", [])
        ys = [float(value[1]) for value in positions if len(value) >= 2]
        # A 3+2 group split across a physical page has one group near the
        # bottom and the remainder near the top.  Reflow that question; a
        # compact 2+1+2 wide-fraction layout remains an explicit exception for
        # a separate geometry review rather than being silently reshaped.
        if ys and max(ys) - min(ys) > 500:
            current = str(choice["id"])
            requested.add(current)
            rationale.append({"shortfall_id": current, "break_before_id": current, "reason": "five_choice_group_split_across_physical_page"})
    ids = [item for item in row_ids if item in requested]
    selected = set(map(str, config.get("selected_item_ids", [])))
    if not set(ids) <= selected:
        raise ValueError("WORKSPACE_SHORTFALL_OUTSIDE_SELECTION")
    config["question_page_break_before_item_ids"] = ids
    config["question_layout_exception_evidence"] = {
        "path": str(args.workspace_evidence.resolve()),
        "sha256": file_hash(args.workspace_evidence),
    }
    config["output"] = args.output_name
    config["run_id"] = "teacher-native-workspace-reflow-" + file_hash(args.workspace_evidence)[:12]
    config["workspace_reflow_rationale"] = {
        "method": "PDF_LEAF_OBJECT_ENDPOINT",
        "minimum_mm": 60,
        "item_ids": ids,
        "rationale": rationale,
        "source_rows_sha256": file_hash(rows_path),
    }
    write_json(args.out, config)
    print(json.dumps({"output": str(args.out), "item_count": len(ids), "item_ids": ids}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
