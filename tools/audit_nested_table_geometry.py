"""CLI for the read-only HWPX nested-table geometry auditor."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.hwpx_nested_table_geometry import audit_many, write_report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", action="append", required=True, type=Path, help="HWPX path; repeatable")
    parser.add_argument("--output", type=Path, help="JSON report destination")
    args = parser.parse_args(argv)
    report = audit_many(args.input)
    if args.output:
        write_report(report, args.output)
    print(json.dumps({
        "status": report["status"],
        "document_count": report["document_count"],
        "report": str(args.output.resolve()) if args.output else None,
    }, ensure_ascii=False))
    return 0 if report["status"] == "PASS" else (1 if report["status"] == "FAIL" else 2)


if __name__ == "__main__":
    raise SystemExit(main())
