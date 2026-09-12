"""Run non-COM raster boundary QA against one rendered page image.

Example::

    python tools/raster_boundary_qa.py --image rendered-page.png \
      --page-mask page-safe-mask.png --column-mask column-1.png \
      --column-mask column-2.png --out raster-boundary-report.json

The command is read-only with respect to the input image and masks.  ``--out``
is optional; without it the JSON report is printed to stdout.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.raster_boundary_qa import RasterBoundaryConfig, RasterBoundaryStatus, audit_raster_boundary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, required=True, help="rendered page PNG/JPEG")
    parser.add_argument("--page-mask", "--page-boundary-mask", dest="page_mask", type=Path)
    parser.add_argument(
        "--column-mask", "--column-boundary-mask", dest="column_masks", action="append", type=Path,
        default=[], help="safe mask for one column; repeat once per column",
    )
    parser.add_argument("--ignore-mask", type=Path, help="explicit mask of known frame/ornament pixels")
    parser.add_argument("--ink-threshold", type=int, default=245)
    parser.add_argument("--touch-tolerance-px", type=int, default=1)
    parser.add_argument("--ignore-page-border-px", type=int, default=4)
    parser.add_argument("--minimum-ink-pixels", type=int, default=1)
    parser.add_argument("--spill-review-pixels", type=int, default=0)
    parser.add_argument("--spill-review-ratio", type=float, default=0.0)
    parser.add_argument("--out", type=Path, help="write JSON report to this path")
    args = parser.parse_args(argv)

    config = RasterBoundaryConfig(
        ink_threshold=args.ink_threshold,
        touch_tolerance_px=args.touch_tolerance_px,
        ignore_page_border_px=args.ignore_page_border_px,
        minimum_ink_pixels=args.minimum_ink_pixels,
        spill_review_pixels=args.spill_review_pixels,
        spill_review_ratio=args.spill_review_ratio,
    )
    report = audit_raster_boundary(
        args.image,
        page_boundary_mask=args.page_mask,
        column_boundary_masks=tuple(args.column_masks),
        config=config,
        ignore_mask=args.ignore_mask,
        name=str(args.image),
    )
    payload = json.dumps(report.as_dict(), ensure_ascii=False, indent=2) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(payload, encoding="utf-8")
    else:
        print(payload, end="")
    if report.status is RasterBoundaryStatus.FAIL:
        return 2
    if report.status is RasterBoundaryStatus.REVIEW_REQUIRED:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
