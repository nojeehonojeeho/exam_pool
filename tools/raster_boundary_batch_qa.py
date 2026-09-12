"""Run non-COM raster boundary QA over a rendered-page batch.

The renderer and the HWP/HWPX pipeline are deliberately outside this tool.
Inputs are rendered page images (normally PNGs); the tool only reads those
images and optional masks, delegates each page to :mod:`app.raster_boundary_qa`,
and writes a machine-readable batch summary.  It never edits or deletes an
input artifact.

Examples::

    # Every PNG below ``rendered`` uses a 10px/8px/10px/8px safe page inset.
    python tools/raster_boundary_batch_qa.py \
      --input rendered --page-inset 10 8 10 8 \
      --out work/raster-boundary-batch.json

    # A page mask file is shared by every page.  A mask directory is also
    # accepted; in that mode ``<page stem>.png`` is selected per input page.
    python tools/raster_boundary_batch_qa.py \
      --input "rendered/**/*.png" --page-mask masks/page-safe.png

``--page-inset`` is expressed in pixels as ``left top right bottom``.  The
safe rectangle is constructed separately for each image, so pages at a
different render resolution are not silently compared against the wrong mask.
At least one page-safe inset or page mask is required: a missing boundary is a
review result in the single-page API, but it is a configuration error for a
release batch and is therefore fail-closed here.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from enum import Enum
import glob
import json
from pathlib import Path
import sys
from typing import Any, Iterable, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PIL import Image

from app.raster_boundary_qa import (
    MaskSource,
    RasterBoundaryConfig,
    RasterBoundaryStatus,
    audit_raster_boundary,
)


SUPPORTED_IMAGE_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"})
BATCH_SCHEMA = "raster-boundary-batch-qa-v1"


class BatchStatus(str, Enum):
    """Aggregate status for one input or the complete batch."""

    PASS = "PASS"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    FAIL = "FAIL"


@dataclass(frozen=True, slots=True)
class BatchPageResult:
    """Serializable result for one rendered page."""

    path: Path
    status: BatchStatus
    report: dict[str, Any] | None = None
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "path": str(self.path),
            "status": self.status.value,
        }
        if self.report is not None:
            payload["report"] = self.report
        if self.error is not None:
            payload["error"] = self.error
        return payload


@dataclass(frozen=True, slots=True)
class BatchReport:
    """Aggregate evidence; no input file is modified."""

    status: BatchStatus
    input_count: int
    pass_count: int
    review_count: int
    fail_count: int
    results: tuple[BatchPageResult, ...]
    page_inset: tuple[int, int, int, int] | None
    page_mask: str | None
    column_mask_count: int

    @property
    def passed(self) -> bool:
        return self.status is BatchStatus.PASS

    @property
    def error_count(self) -> int:
        """Number of pages whose audit could not be completed."""

        return sum(result.error is not None for result in self.results)

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": BATCH_SCHEMA,
            "status": self.status.value,
            "passed": self.passed,
            "input_count": self.input_count,
            "pass_count": self.pass_count,
            "review_count": self.review_count,
            "fail_count": self.fail_count,
            "error_count": self.error_count,
            "mask_policy": {
                "page_inset_px": list(self.page_inset) if self.page_inset is not None else None,
                "page_mask": self.page_mask,
                "column_mask_count": self.column_mask_count,
            },
            "results": [result.as_dict() for result in self.results],
        }


def _is_image(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in SUPPORTED_IMAGE_SUFFIXES


def _expand_input(value: str | Path, *, pattern: str) -> Iterable[Path]:
    """Expand one file, directory, or glob into deterministic image paths."""

    raw = str(value)
    candidate = Path(raw)
    if candidate.is_file():
        if not _is_image(candidate):
            raise ValueError(f"input is not a supported rendered image: {candidate}")
        yield candidate.resolve()
        return
    if candidate.is_dir():
        yield from sorted(
            (path.resolve() for path in candidate.rglob(pattern) if _is_image(path)),
            key=lambda path: str(path).casefold(),
        )
        return

    matches = [Path(match) for match in glob.glob(raw, recursive=True)]
    for path in sorted(
        (match.resolve() for match in matches if _is_image(match)),
        key=lambda item: str(item).casefold(),
    ):
        yield path


def collect_inputs(values: Sequence[str | Path], *, pattern: str = "*.png") -> tuple[Path, ...]:
    """Collect and de-duplicate input pages in stable path order."""

    found: dict[str, Path] = {}
    for value in values:
        for path in _expand_input(value, pattern=pattern):
            found[str(path).casefold()] = path
    return tuple(sorted(found.values(), key=lambda path: str(path).casefold()))


def _resolve_optional_mask(reference: Path | None, page: Path, *, label: str) -> Path | None:
    """Resolve a shared mask file or a per-page mask directory.

    A directory uses the rendered page stem (for example, ``page-003.png``
    selects ``masks/page-003.png``).  The directory is intentionally strict:
    no nearest-page or arbitrary-first-file fallback is allowed.
    """

    if reference is None:
        return None
    reference = reference.resolve()
    if reference.is_file():
        return reference
    if not reference.is_dir():
        raise FileNotFoundError(f"{label} does not exist: {reference}")
    candidates = sorted(
        (path for path in reference.glob(f"{page.stem}.*") if path.is_file()),
        key=lambda path: str(path).casefold(),
    )
    candidates = [path for path in candidates if path.suffix.lower() in SUPPORTED_IMAGE_SUFFIXES]
    if len(candidates) != 1:
        if not candidates:
            raise FileNotFoundError(f"{label} missing for {page.name} in {reference}")
        raise ValueError(f"{label} is ambiguous for {page.name}: {candidates}")
    return candidates[0]


def _rect_from_inset(inset: tuple[int, int, int, int], size: tuple[int, int]) -> tuple[int, int, int, int]:
    left, top, right, bottom = inset
    width, height = size
    if min(inset) < 0:
        raise ValueError("page inset values must be non-negative")
    if left + right >= width or top + bottom >= height:
        raise ValueError(f"page inset {inset} leaves no safe area for image size {size}")
    return left, top, width - right, height - bottom


def _ensure_mask_size(mask: Path, page: Path) -> None:
    try:
        with Image.open(mask) as mask_image, Image.open(page) as page_image:
            if mask_image.size != page_image.size:
                raise ValueError(
                    f"page mask size {mask_image.size} does not match {page.name} size {page_image.size}: {mask}"
                )
    except OSError as error:
        raise ValueError(f"unable to read page mask {mask}: {error}") from error


def run_batch(
    inputs: Sequence[Path],
    *,
    page_inset: tuple[int, int, int, int] | None = None,
    page_mask: Path | None = None,
    column_masks: Sequence[Path] = (),
    ignore_mask: Path | None = None,
    config: RasterBoundaryConfig | None = None,
) -> BatchReport:
    """Run one-page audits serially and return a fail-closed batch report."""

    if page_inset is None and page_mask is None:
        raise ValueError("provide page_inset or page_mask for a release batch")
    if page_inset is not None and len(page_inset) != 4:
        raise ValueError("page_inset must contain left, top, right, bottom")
    pages = tuple(Path(page).resolve() for page in inputs)
    if not pages:
        raise ValueError("batch input is empty")

    results: list[BatchPageResult] = []
    for page in pages:
        try:
            resolved_page_mask = _resolve_optional_mask(page_mask, page, label="page mask")
            resolved_columns = tuple(
                _resolve_optional_mask(mask, page, label=f"column mask {index}") or mask
                for index, mask in enumerate(column_masks, 1)
            )
            resolved_ignore = _resolve_optional_mask(ignore_mask, page, label="ignore mask")
            if resolved_page_mask is not None:
                _ensure_mask_size(resolved_page_mask, page)
            for mask in resolved_columns:
                _ensure_mask_size(mask, page)
            if resolved_ignore is not None:
                _ensure_mask_size(resolved_ignore, page)

            with Image.open(page) as image:
                safe_rect = _rect_from_inset(page_inset, image.size) if page_inset is not None else None
            policy = config or RasterBoundaryConfig()
            page_report = audit_raster_boundary(
                page,
                page_boundary_mask=resolved_page_mask or safe_rect,
                column_boundary_masks=resolved_columns,
                config=policy,
                ignore_mask=resolved_ignore,
                name=str(page),
            )
            results.append(BatchPageResult(page, BatchStatus(page_report.status.value), page_report.as_dict()))
        except (OSError, ValueError, TypeError) as error:
            results.append(
                BatchPageResult(page, BatchStatus.FAIL, error=f"{type(error).__name__}: {error}")
            )

    pass_count = sum(result.status is BatchStatus.PASS for result in results)
    review_count = sum(result.status is BatchStatus.REVIEW_REQUIRED for result in results)
    fail_count = sum(result.status is BatchStatus.FAIL for result in results)
    if fail_count:
        status = BatchStatus.FAIL
    elif review_count:
        status = BatchStatus.REVIEW_REQUIRED
    else:
        status = BatchStatus.PASS
    return BatchReport(
        status=status,
        input_count=len(results),
        pass_count=pass_count,
        review_count=review_count,
        fail_count=fail_count,
        results=tuple(results),
        page_inset=page_inset,
        page_mask=str(page_mask) if page_mask is not None else None,
        column_mask_count=len(column_masks),
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input", dest="inputs", action="append", required=True,
        help="rendered image, directory (recursive), or glob; repeat for multiple roots",
    )
    parser.add_argument("--pattern", default="*.png", help="directory pattern (default: *.png)")
    parser.add_argument(
        "--page-inset", nargs=4, type=int, metavar=("LEFT", "TOP", "RIGHT", "BOTTOM"),
        help="safe page inset in pixels; mutually exclusive with --page-mask",
    )
    parser.add_argument(
        "--page-mask", type=Path,
        help="shared mask file or directory containing one mask named after each page stem",
    )
    parser.add_argument(
        "--column-mask", action="append", type=Path, default=[],
        help="shared column mask file or per-page mask directory; repeat per column",
    )
    parser.add_argument("--ignore-mask", type=Path, help="shared or per-page known-frame mask")
    parser.add_argument("--ink-threshold", type=int, default=245)
    parser.add_argument("--touch-tolerance-px", type=int, default=1)
    parser.add_argument("--ignore-page-border-px", type=int, default=4)
    parser.add_argument("--minimum-ink-pixels", type=int, default=1)
    parser.add_argument("--spill-review-pixels", type=int, default=0)
    parser.add_argument("--spill-review-ratio", type=float, default=0.0)
    parser.add_argument("--out", type=Path, help="write JSON report to this path; otherwise print it")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.page_inset is not None and args.page_mask is not None:
        parser.error("--page-inset and --page-mask are mutually exclusive")
    if args.page_inset is None and args.page_mask is None:
        parser.error("one of --page-inset or --page-mask is required")
    try:
        inputs = collect_inputs(args.inputs, pattern=args.pattern)
        if not inputs:
            raise ValueError("no supported rendered images matched --input")
        config = RasterBoundaryConfig(
            ink_threshold=args.ink_threshold,
            touch_tolerance_px=args.touch_tolerance_px,
            ignore_page_border_px=args.ignore_page_border_px,
            minimum_ink_pixels=args.minimum_ink_pixels,
            spill_review_pixels=args.spill_review_pixels,
            spill_review_ratio=args.spill_review_ratio,
        )
        report = run_batch(
            inputs,
            page_inset=tuple(args.page_inset) if args.page_inset is not None else None,
            page_mask=args.page_mask,
            column_masks=tuple(args.column_mask),
            ignore_mask=args.ignore_mask,
            config=config,
        )
    except (OSError, ValueError, TypeError) as error:
        parser.error(str(error))
    payload = json.dumps(report.as_dict(), ensure_ascii=False, indent=2) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(payload, encoding="utf-8")
    else:
        print(payload, end="")
    if report.status is BatchStatus.FAIL:
        return 2
    if report.status is BatchStatus.REVIEW_REQUIRED:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "BATCH_SCHEMA",
    "BatchPageResult",
    "BatchReport",
    "BatchStatus",
    "collect_inputs",
    "run_batch",
]
