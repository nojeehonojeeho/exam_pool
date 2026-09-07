"""Run the strict PDF-to-native-equation provenance gate on a JSON manifest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.pdf_hwp_formula_provenance_gate import audit_formula_provenance


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--json", dest="output", type=Path)
    args = parser.parse_args(argv)
    try:
        payload = json.loads(args.manifest.read_text(encoding="utf-8"))
        report = audit_formula_provenance(payload, require_source_evidence=True)
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        report = {
            "status": "FAIL",
            "passed": False,
            "check_scope": "strict_formula_source_provenance_only",
            "counts": {"formula_occurrences": 0, "findings": 1},
            "findings": [{"code": "PROVENANCE_INPUT_INVALID", "detail": str(exc)}],
        }
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    compact = {key: value for key, value in report.items() if key not in {"findings", "formula_occurrences"}}
    print(json.dumps(compact, ensure_ascii=False))
    return 0 if report.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
