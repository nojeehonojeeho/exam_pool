"""CLI for the repository-level high-end delivery gate.

Example (PowerShell, paths abbreviated here):

    python tools/highend_delivery_gate.py delivery-v6-comverified-summary.json \
      --scope-root work/highend_four_subjects --json audit.json

The command only reads its inputs.  ``--json`` writes the audit report; when
omitted, the report is printed to stdout.  Exit status is 0 only when FINAL
promotion is independently allowed.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.highend_delivery_gate import REQUIRED_SUBJECTS, audit_delivery_summary_path


_DEFAULT_MANIFEST_NAMES = {
    "고등수학상": ("math_up", "source_inventory.json"),
    "고등수학하": ("math_down", "source_inventory.json"),
    "수학II": ("math2", "source_inventory.json"),
    "확률과_통계": ("probability", "highend_probability_source_manifest.json"),
}


def _scope_paths_from_root(root: Path) -> dict[str, Path]:
    return {subject: root.joinpath(*parts) for subject, parts in _DEFAULT_MANIFEST_NAMES.items()}


def _parse_scope_manifest(values: list[str], root: Path | None) -> dict[str, Path] | None:
    if not values:
        return _scope_paths_from_root(root) if root is not None else None
    result: dict[str, Path] = {}
    for value in values:
        subject, separator, path = value.partition("=")
        if not separator or subject not in REQUIRED_SUBJECTS or not path:
            raise ValueError(f"--scope-manifest must be SUBJECT=PATH for one of {REQUIRED_SUBJECTS!r}: {value!r}")
        result[subject] = Path(path)
    if set(result) != set(REQUIRED_SUBJECTS):
        missing = sorted(set(REQUIRED_SUBJECTS) - set(result))
        raise ValueError(f"one --scope-manifest is required for every subject; missing {missing!r}")
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit a v6 four-subject delivery summary for independent FINAL eligibility.")
    parser.add_argument("summary", type=Path, help="v6 delivery summary JSON")
    parser.add_argument("--scope-root", type=Path, help="directory containing math_up/, math_down/, math2/, and probability/")
    parser.add_argument("--scope-manifest", action="append", default=[], metavar="SUBJECT=PATH", help="repeat exactly four times to override scope-root")
    parser.add_argument("--com-report", type=Path, help="COM serial readback report (defaults to no COM evidence)")
    parser.add_argument("--json", dest="json_path", type=Path, help="write the audit report JSON to this path")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        inferred_root = args.scope_root
        if inferred_root is None:
            candidate_root = args.summary.resolve().parent.parent / "highend_four_subjects"
            if candidate_root.is_dir():
                inferred_root = candidate_root
        scope_paths = _parse_scope_manifest(args.scope_manifest, inferred_root)
        com_report = args.com_report
        if com_report is None:
            with args.summary.open("r", encoding="utf-8") as handle:
                summary_value = json.load(handle)
            if isinstance(summary_value, dict):
                serial = summary_value.get("com_serial")
                if isinstance(serial, dict) and isinstance(serial.get("path"), str):
                    inferred_com = Path(serial["path"])
                    if inferred_com.is_file():
                        com_report = inferred_com
        result = audit_delivery_summary_path(args.summary, scope_manifest_paths=scope_paths, com_report_path=com_report)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        result = {
            "schema": "highend-delivery-gate-v1",
            "status": "FAIL",
            "final": False,
            "promotion_allowed": False,
            "findings": [{"code": "AUDIT_INPUT_INVALID", "blocking": True, "message": str(exc)}],
        }
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.json_path is not None:
        args.json_path.write_text(rendered, encoding="utf-8")
    else:
        sys.stdout.write(rendered)
    return 0 if result.get("promotion_allowed") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
