"""Check the actual native-writer input. A PASS is not a release verdict."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.hwp_authoring_preflight import audit_authoring_items


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--asset-root", type=Path, required=True)
    parser.add_argument("--json", dest="output", type=Path)
    args = parser.parse_args(argv)
    try:
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        items = manifest["items"]
        if not isinstance(items, list) or not items or not all(isinstance(item, dict) for item in items):
            raise ValueError("items must be a nonempty list of objects")
        report = audit_authoring_items(items, asset_root=args.asset_root)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        report = {"status": "FAIL", "source_fidelity_proven": False,
                  "findings": [{"code": "AUTHORING_INPUT_INVALID", "detail": str(exc)}]}
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "equations"}, ensure_ascii=True))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
