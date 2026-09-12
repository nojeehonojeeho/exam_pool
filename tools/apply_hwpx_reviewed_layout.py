"""Apply an explicit hash-bound reviewed HWPX layout plan to a fresh file."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.hwpx_reviewed_layout import revise_package


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('source', type=Path)
    parser.add_argument('target', type=Path)
    parser.add_argument('plan', type=Path)
    args = parser.parse_args()
    plan = json.loads(args.plan.read_text(encoding='utf-8'))
    print(json.dumps(revise_package(args.source, args.target, plan), ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
