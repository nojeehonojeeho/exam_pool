"""Create a hash-bound exception only for a compact rendered 2+1+2 layout.

Most five-choice multiple-choice questions must be rendered 3+2.  This tool
does not loosen that rule generally.  It makes an exception document only when
a particular target PDF proves the narrow compact 2+1+2 pattern required by a
wide mathematical choice; the evidence collector rechecks its hashes and
positions before accepting it.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.teacher_workflow import file_hash, json_hash, write_json
from tools.teacher_release_evidence import compact_two_one_two


def args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--target-hwp", type=Path, required=True)
    parser.add_argument("--target-hwpx", type=Path, required=True)
    parser.add_argument("--pdf", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    a = args()
    if a.out.exists():
        raise FileExistsError(a.out)
    workspace = json.loads(a.workspace.read_text(encoding="utf-8-sig"))
    target = {"hwp": file_hash(a.target_hwp), "hwpx": file_hash(a.target_hwpx)}
    if workspace.get("schema") != "teacher-evidence/v1" or workspace.get("kind") != "workspace":
        raise ValueError("WORKSPACE_SCHEMA")
    if workspace.get("target_sha256") != target:
        raise ValueError("WORKSPACE_TARGET_HASH")
    rows = []
    rejected = []
    for choice in workspace.get("choice_layouts", []):
        if choice.get("three_plus_two") is not False:
            continue
        positions = choice.get("positions", [])
        if not compact_two_one_two(positions):
            rejected.append({"id": choice.get("id"), "reason": "NONCOMPACT_OR_UNSUPPORTED_FIVE_CHOICE_LAYOUT"})
            continue
        rows.append({
            "id": str(choice["id"]),
            "status": "PASS",
            "layout_pattern": "2+1+2",
            "reason": "WIDE_MATHEMATICAL_CHOICES_COMPACT_2_1_2_PRESERVES_APPROVED_FONT_AND_FORMULA_SIZE",
            "page": choice.get("page"),
            "positions_sha256": json_hash(positions),
            "source_workspace_choice": choice,
        })
    checks = {
        "workspace_target_matches_live_hwp_hwpx": True,
        "all_observed_non_3plus2_layouts_are_compact_evidenced_2_1_2": not rejected,
        "at_least_one_evidenced_exception": bool(rows),
    }
    result = {
        "schema": "teacher-choice-layout-exceptions/v1",
        "target_sha256": target,
        "target_pdf_sha256": file_hash(a.pdf),
        "source_workspace": {"path": str(a.workspace.resolve()), "sha256": file_hash(a.workspace)},
        "rows": rows,
        "rejected": rejected,
        "checks": checks,
        "status": "PASS" if all(checks.values()) else "REVIEW_REQUIRED",
    }
    write_json(a.out, result)
    print(json.dumps({"status": result["status"], "exception_ids": [row["id"] for row in rows], "rejected": rejected}, ensure_ascii=False))
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
