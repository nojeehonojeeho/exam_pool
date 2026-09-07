"""CLI for the conservative reviewed-source/formula-authoring closure ledger."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.pdf_hwp_formula_closure import build_formula_closure


def main() -> int:
    parser = argparse.ArgumentParser(description="Join reviewed PDF formula evidence to authoring MathIR without guessing")
    parser.add_argument("reviewed_manifest", type=Path)
    parser.add_argument("authoring_manifest", type=Path)
    parser.add_argument("--json", dest="output", type=Path, required=True)
    args = parser.parse_args()
    try:
        reviewed = json.loads(args.reviewed_manifest.read_text(encoding="utf-8"))
        authoring = json.loads(args.authoring_manifest.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        report = {"status": "REVIEW_REQUIRED", "release_status": "REVIEW_REQUIRED", "candidate_only": True, "findings": [{"code": "MANIFEST_READ_ERROR", "detail": str(exc)}]}
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False))
        return 1
    report = build_formula_closure(reviewed, authoring)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "counts": report.get("counts", {})}, ensure_ascii=False))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
