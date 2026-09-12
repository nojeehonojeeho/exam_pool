"""Run the read-only HIGH-END native-equation reconciliation audit."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.highend_native_equation_audit import load_and_audit


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("problem_page_manifest", type=Path)
    parser.add_argument("reviewed_manifest", type=Path)
    parser.add_argument("reviewed_scope_manifest", type=Path)
    parser.add_argument("hwpx", type=Path)
    parser.add_argument("--json", dest="json_path", type=Path, help="write the evidence report")
    args = parser.parse_args(argv)

    report = load_and_audit(
        args.problem_page_manifest,
        args.reviewed_manifest,
        args.reviewed_scope_manifest,
        args.hwpx,
    )
    payload = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.json_path:
        args.json_path.parent.mkdir(parents=True, exist_ok=True)
        args.json_path.write_text(payload, encoding="utf-8")
    print(
        json.dumps(
            {
                "status": report.get("status"),
                "counts": report.get("counts", {}),
                "gates": report.get("gates", {}),
            },
            ensure_ascii=False,
        )
    )
    return 0 if report.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
