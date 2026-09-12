"""Non-COM raster boundary and clipping checks for rendered pages.

The renderer is intentionally outside this module.  Callers provide a rendered
page image and one or more *safe* boundary masks (non-zero pixels are allowed
content).  The check reports evidence only; it never masks, crops, or changes a
rendered artifact.

``page_boundary_mask`` describes the page content area.  Optional
``column_boundary_masks`` describe the allowed content areas of columns.  A
pixel outside a configured safe area is a clipping/spill finding and normally
``FAIL``.  Ink that is still inside, but touches the safe edge, is
``REVIEW_REQUIRED`` so a reviewer can decide whether the edge is intentional.

Legitimate page frames are common in source documents.  By default only
line-like ink in the outer ``ignore_page_border_px`` pixels is excluded from
the decision and its count is preserved in the report as evidence.  Small
text/table spill in that strip is still checked.  Set that option to ``0``
when a full-bleed page must be checked, or provide an explicit ``ignore_mask``
for a known frame/ornament.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, TypeAlias

from PIL import Image, ImageChops, ImageFilter, ImageStat


PixelBBox: TypeAlias = tuple[int, int, int, int]
MaskBBox: TypeAlias = tuple[int, int, int, int]
MaskSource: TypeAlias = Image.Image | Path | str | MaskBBox | Sequence[Sequence[int]]


class RasterBoundaryStatus(str, Enum):
    """Machine-readable verdict for one rendered page."""

    PASS = "PASS"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    FAIL = "FAIL"


class RasterBoundaryIssue(str, Enum):
    """Stable codes emitted in boundary evidence."""

    BOUNDARY_MASK_MISSING = "boundary_mask_missing"
    RENDER_EMPTY = "render_empty"
    SAFE_BOUNDARY_TOUCH = "safe_boundary_touch"
    SAFE_BOUNDARY_SPILL = "safe_boundary_spill"
    COLUMN_BOUNDARY_TOUCH = "column_boundary_touch"
    COLUMN_BOUNDARY_SPILL = "column_boundary_spill"


class BoundaryMaskKind(str, Enum):
    """The scope represented by a named mask."""

    PAGE = "page"
    COLUMN = "column"


@dataclass(frozen=True, slots=True)
class RasterBoundaryMask:
    """A named safe-content mask.

    ``mask`` may be a PIL image, an image path, a ``(left, top, right,
    bottom)`` rectangle, or a small matrix of non-zero/zero values.  Rectangle
    coordinates use the usual half-open convention: ``right`` and ``bottom``
    are outside the safe region.
    """

    mask: MaskSource
    name: str = "boundary"
    kind: BoundaryMaskKind = BoundaryMaskKind.PAGE


# A shorter name is convenient for callers that already use ``BoundaryMask``.
BoundaryMask = RasterBoundaryMask


@dataclass(frozen=True, slots=True)
class RasterBoundaryConfig:
    """Thresholds and mask inputs for :func:`audit_raster_boundary`."""

    page_boundary_mask: MaskSource | RasterBoundaryMask | None = None
    column_boundary_masks: tuple[MaskSource | RasterBoundaryMask, ...] = ()
    ignore_mask: MaskSource | None = None
    ink_threshold: int = 245
    touch_tolerance_px: int = 1
    ignore_page_border_px: int = 4
    minimum_ink_pixels: int = 1
    page_border_min_span_ratio: float = 0.5
    # Tiny spills can be downgraded when a renderer is known to produce an
    # antialiased fringe.  Defaults are strict: every spill is FAIL evidence.
    spill_review_pixels: int = 0
    spill_review_ratio: float = 0.0

    def __post_init__(self) -> None:
        if not 0 <= self.ink_threshold <= 255:
            raise ValueError("ink_threshold must be between 0 and 255")
        for field_name in (
            "touch_tolerance_px", "ignore_page_border_px", "minimum_ink_pixels", "spill_review_pixels",
        ):
            if getattr(self, field_name) < 0:
                raise ValueError(f"{field_name} must be non-negative")
        if not 0.0 <= self.spill_review_ratio <= 1.0:
            raise ValueError("spill_review_ratio must be between 0 and 1")
        if not 0.0 <= self.page_border_min_span_ratio <= 1.0:
            raise ValueError("page_border_min_span_ratio must be between 0 and 1")


# Compatibility alias for code that calls policies rather than configs.
RasterBoundaryPolicy = RasterBoundaryConfig


@dataclass(frozen=True, slots=True)
class RasterBoundaryFinding:
    """One piece of actionable raster evidence."""

    code: RasterBoundaryIssue
    severity: RasterBoundaryStatus
    region: str
    bbox: PixelBBox | None
    ink_pixels: int
    scoped_ink_pixels: int
    ratio: float
    detail: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code.value,
            "severity": self.severity.value,
            "region": self.region,
            "bbox": list(self.bbox) if self.bbox is not None else None,
            "ink_pixels": self.ink_pixels,
            "scoped_ink_pixels": self.scoped_ink_pixels,
            "ratio": self.ratio,
            "detail": self.detail,
        }

    def __getitem__(self, key: str) -> Any:
        """Allow report consumers to treat evidence like existing QA dicts."""
        return self.as_dict()[key]


@dataclass(frozen=True, slots=True)
class RasterBoundaryReport:
    """Aggregate status plus exact pixel evidence; no artifact is mutated."""

    status: RasterBoundaryStatus
    image_size: tuple[int, int]
    page_mask_configured: bool
    column_masks_configured: int
    ink_pixels: int
    ignored_page_border_pixels: int
    ignored_mask_pixels: int
    findings: tuple[RasterBoundaryFinding, ...]

    @property
    def passed(self) -> bool:
        return self.status is RasterBoundaryStatus.PASS

    @property
    def review_required(self) -> bool:
        """Whether a human review is needed (including a hard failure)."""
        return self.status is not RasterBoundaryStatus.PASS

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "passed": self.passed,
            "review_required": self.review_required,
            "image_size": list(self.image_size),
            "page_mask_configured": self.page_mask_configured,
            "column_masks_configured": self.column_masks_configured,
            "ink_pixels": self.ink_pixels,
            "ignored_page_border_pixels": self.ignored_page_border_pixels,
            "ignored_mask_pixels": self.ignored_mask_pixels,
            "findings": [finding.as_dict() for finding in self.findings],
        }

    def __getitem__(self, key: str) -> Any:
        return self.as_dict()[key]


def _open_image(source: Image.Image | Path | str, *, label: str) -> Image.Image:
    if isinstance(source, Image.Image):
        return source.convert("L").copy()
    path = Path(source)
    try:
        with Image.open(path) as opened:
            return opened.convert("L").copy()
    except OSError as error:
        raise ValueError(f"unable to read {label} image: {path}") from error


def _mask_from_matrix(matrix: Sequence[Sequence[int]], size: tuple[int, int], *, label: str) -> Image.Image:
    rows = [list(row) for row in matrix]
    if not rows or not rows[0]:
        raise ValueError(f"{label} matrix must not be empty")
    width = len(rows[0])
    if any(len(row) != width for row in rows):
        raise ValueError(f"{label} matrix rows must have equal width")
    if (width, len(rows)) != size:
        raise ValueError(f"{label} matrix size {(width, len(rows))} does not match image size {size}")
    image = Image.new("L", size, 0)
    image.putdata([255 if value else 0 for row in rows for value in row])
    return image


def _mask_image(source: MaskSource | RasterBoundaryMask, size: tuple[int, int], *, label: str) -> Image.Image:
    if isinstance(source, RasterBoundaryMask):
        source = source.mask
    if isinstance(source, (Image.Image, Path, str)):
        image = _open_image(source, label=label)
    elif (
        isinstance(source, Sequence)
        and len(source) == 4
        and all(isinstance(value, (int, float)) for value in source)
    ):
        left, top, right, bottom = (int(value) for value in source)
        if right <= left or bottom <= top:
            raise ValueError(f"{label} rectangle must have positive width and height")
        image = Image.new("L", size, 0)
        # PIL rectangles are inclusive; safe-mask coordinates are half-open.
        image.paste(255, (max(0, left), max(0, top), min(size[0], right), min(size[1], bottom)))
    else:
        image = _mask_from_matrix(source, size, label=label)
    if image.size != size:
        actual = image.size
        image.close()
        raise ValueError(f"{label} size {actual} does not match image size {size}")
    return image.point(lambda value: 255 if value else 0, mode="L")


def _and(left: Image.Image, right: Image.Image) -> Image.Image:
    return ImageChops.multiply(left, right)


def _or(left: Image.Image, right: Image.Image) -> Image.Image:
    return ImageChops.lighter(left, right)


def _not(image: Image.Image) -> Image.Image:
    return ImageChops.invert(image)


def _count(image: Image.Image) -> int:
    # L masks only contain 0/255, so the mean is an exact pixel count.
    mean = ImageStat.Stat(image).mean[0]
    return int(round(mean * image.width * image.height / 255.0))


def _bbox(image: Image.Image) -> PixelBBox | None:
    return image.getbbox()


def _perimeter_keep_mask(size: tuple[int, int], pixels: int) -> Image.Image:
    image = Image.new("L", size, 255)
    if pixels <= 0:
        return image
    width, height = size
    if pixels * 2 >= width or pixels * 2 >= height:
        image.point(lambda _value: 0, mode="L")
        image.close()
        return Image.new("L", size, 0)
    image.paste(0, (0, 0, width, pixels))
    image.paste(0, (0, height - pixels, width, height))
    image.paste(0, (0, 0, pixels, height))
    image.paste(0, (width - pixels, 0, width, height))
    return image


def _legitimate_page_border_mask(
    border_ink: Image.Image,
    size: tuple[int, int],
    pixels: int,
    min_span_ratio: float,
) -> Image.Image:
    """Keep only line-like ink that is plausibly a page frame.

    A border candidate must be in the configured outer strip and span at least
    ``min_span_ratio`` of the corresponding page dimension.  This deliberately
    does not whitelist a short glyph or a small table cell that happens to
    reach the image edge.
    """
    allowed = Image.new("L", size, 0)
    if pixels <= 0:
        return allowed
    width, height = size
    required_width = max(1, int(round(width * min_span_ratio)))
    required_height = max(1, int(round(height * min_span_ratio)))

    rows = tuple(range(min(pixels, height))) + tuple(range(max(0, height - pixels), height))
    for y in rows:
        row = border_ink.crop((0, y, width, y + 1))
        # Count rather than use bbox: a top/bottom frame can make a mostly
        # empty side column's bbox span the full height.
        if _count(row) >= required_width:
            allowed.paste(row, (0, y))
        row.close()

    columns = tuple(range(min(pixels, width))) + tuple(range(max(0, width - pixels), width))
    for x in columns:
        column = border_ink.crop((x, 0, x + 1, height))
        if _count(column) >= required_height:
            allowed.paste(column, (x, 0))
        column.close()
    return allowed


def _finding(
    code: RasterBoundaryIssue,
    severity: RasterBoundaryStatus,
    region: str,
    evidence: Image.Image,
    scoped: Image.Image,
    detail: str,
) -> RasterBoundaryFinding | None:
    pixels = _count(evidence)
    if pixels <= 0:
        return None
    scoped_pixels = _count(scoped)
    return RasterBoundaryFinding(
        code=code,
        severity=severity,
        region=region,
        bbox=_bbox(evidence),
        ink_pixels=pixels,
        scoped_ink_pixels=scoped_pixels,
        ratio=round(pixels / max(1, scoped_pixels), 6),
        detail=detail,
    )


def _spill_severity(
    pixels: int, scoped_pixels: int, config: RasterBoundaryConfig,
) -> RasterBoundaryStatus:
    if pixels <= config.spill_review_pixels:
        return RasterBoundaryStatus.REVIEW_REQUIRED
    if pixels / max(1, scoped_pixels) <= config.spill_review_ratio:
        return RasterBoundaryStatus.REVIEW_REQUIRED
    return RasterBoundaryStatus.FAIL


def _close_all(images: Sequence[Image.Image]) -> None:
    for image in images:
        image.close()


def audit_raster_boundary(
    image: Image.Image | Path | str,
    *,
    page_boundary_mask: MaskSource | RasterBoundaryMask | None = None,
    column_boundary_masks: Sequence[MaskSource | RasterBoundaryMask] = (),
    config: RasterBoundaryConfig | None = None,
    # Friendly aliases for callers that use shorter mask names.
    page_mask: MaskSource | RasterBoundaryMask | None = None,
    column_masks: Sequence[MaskSource | RasterBoundaryMask] = (),
    ignore_mask: MaskSource | None = None,
    name: str = "rendered page",
) -> RasterBoundaryReport:
    """Inspect raster ink against page/column safe-content masks.

    ``page_mask``/``column_masks`` are aliases for the longer argument names;
    when both forms are supplied the longer names win.  The returned report is
    serializable via :meth:`RasterBoundaryReport.as_dict` and carries bounding
    boxes for every non-empty finding.
    """

    policy = config or RasterBoundaryConfig()
    resolved_page = page_boundary_mask or page_mask or policy.page_boundary_mask
    resolved_columns = tuple(column_boundary_masks) or tuple(column_masks) or policy.column_boundary_masks
    resolved_ignore = ignore_mask or policy.ignore_mask

    opened = _open_image(image, label=name)
    all_images: list[Image.Image] = [opened]
    try:
        size = opened.size
        gray = opened
        raw_ink = gray.point(
            lambda value: 255 if value <= policy.ink_threshold else 0,
            mode="L",
        )
        all_images.append(raw_ink)
        total_raw_ink = _count(raw_ink)
        if total_raw_ink == 0:
            findings = (
                RasterBoundaryFinding(
                    RasterBoundaryIssue.RENDER_EMPTY,
                    RasterBoundaryStatus.REVIEW_REQUIRED,
                    "page",
                    None,
                    0,
                    0,
                    0.0,
                    "render contains no pixels at or below ink_threshold",
                ),
            )
            return RasterBoundaryReport(
                RasterBoundaryStatus.REVIEW_REQUIRED, size, bool(resolved_page), len(resolved_columns),
                0, 0, 0, findings,
            )

        ink = raw_ink.copy()
        all_images.append(ink)
        border_strip = _and(raw_ink, _not(_perimeter_keep_mask(size, policy.ignore_page_border_px)))
        all_images.append(border_strip)
        legitimate_border = _legitimate_page_border_mask(
            border_strip,
            size,
            policy.ignore_page_border_px,
            policy.page_border_min_span_ratio,
        )
        all_images.append(legitimate_border)
        ignored_page_border_pixels = _count(legitimate_border)
        ink_after_border = _and(ink, _not(legitimate_border))
        all_images.append(ink_after_border)
        ink = ink_after_border

        ignored_mask_pixels = 0
        if resolved_ignore is not None:
            ignored = _mask_image(resolved_ignore, size, label="ignore")
            all_images.append(ignored)
            ignored_ink = _and(ink, ignored)
            all_images.append(ignored_ink)
            ignored_mask_pixels = _count(ignored_ink)
            ink_after_ignore = _and(ink, _not(ignored))
            all_images.append(ink_after_ignore)
            ink = ink_after_ignore

        if resolved_page is None and not resolved_columns:
            finding = RasterBoundaryFinding(
                RasterBoundaryIssue.BOUNDARY_MASK_MISSING,
                RasterBoundaryStatus.REVIEW_REQUIRED,
                "page",
                _bbox(ink),
                _count(ink),
                _count(ink),
                1.0,
                "provide page_boundary_mask or column_boundary_masks before release",
            )
            return RasterBoundaryReport(
                RasterBoundaryStatus.REVIEW_REQUIRED, size, False, 0, _count(ink),
                ignored_page_border_pixels, ignored_mask_pixels, (finding,),
            )

        safe_page: Image.Image | None = None
        safe_columns: Image.Image | None = None
        if resolved_page is not None:
            safe_page = _mask_image(resolved_page, size, label="page boundary")
            all_images.append(safe_page)
        if resolved_columns:
            safe_columns = Image.new("L", size, 0)
            all_images.append(safe_columns)
            for index, source in enumerate(resolved_columns, 1):
                current = _mask_image(source, size, label=f"column boundary {index}")
                all_images.append(current)
                combined = _or(safe_columns, current)
                all_images.append(combined)
                safe_columns = combined

        findings: list[RasterBoundaryFinding] = []
        if safe_page is not None:
            outside_page = _and(ink, _not(safe_page))
            all_images.append(outside_page)
            scoped_page = ink
            finding = _finding(
                RasterBoundaryIssue.SAFE_BOUNDARY_SPILL,
                _spill_severity(_count(outside_page), _count(scoped_page), policy),
                "page",
                outside_page,
                scoped_page,
                "ink falls outside the configured page safe-content mask",
            )
            if finding is not None and _count(outside_page) >= policy.minimum_ink_pixels:
                findings.append(finding)

            if policy.touch_tolerance_px:
                near_outside_page = _not(safe_page).filter(
                    ImageFilter.MaxFilter(policy.touch_tolerance_px * 2 + 1),
                )
                all_images.append(near_outside_page)
                inside_touch_page = _and(_and(ink, safe_page), near_outside_page)
                all_images.append(inside_touch_page)
                finding = _finding(
                    RasterBoundaryIssue.SAFE_BOUNDARY_TOUCH,
                    RasterBoundaryStatus.REVIEW_REQUIRED,
                    "page",
                    inside_touch_page,
                    _and(ink, safe_page),
                    "ink touches the configured page safe-content edge",
                )
                if finding is not None and _count(inside_touch_page) >= policy.minimum_ink_pixels:
                    findings.append(finding)

        if safe_columns is not None:
            column_scope = _and(ink, safe_page) if safe_page is not None else ink
            all_images.append(column_scope)
            outside_columns = _and(column_scope, _not(safe_columns))
            all_images.append(outside_columns)
            finding = _finding(
                RasterBoundaryIssue.COLUMN_BOUNDARY_SPILL,
                _spill_severity(_count(outside_columns), _count(column_scope), policy),
                "columns",
                outside_columns,
                column_scope,
                "ink falls outside the union of configured column safe-content masks",
            )
            if finding is not None and _count(outside_columns) >= policy.minimum_ink_pixels:
                findings.append(finding)

            if policy.touch_tolerance_px:
                near_outside_columns = _not(safe_columns).filter(
                    ImageFilter.MaxFilter(policy.touch_tolerance_px * 2 + 1),
                )
                all_images.append(near_outside_columns)
                inside_touch_columns = _and(_and(column_scope, safe_columns), near_outside_columns)
                all_images.append(inside_touch_columns)
                finding = _finding(
                    RasterBoundaryIssue.COLUMN_BOUNDARY_TOUCH,
                    RasterBoundaryStatus.REVIEW_REQUIRED,
                    "columns",
                    inside_touch_columns,
                    _and(column_scope, safe_columns),
                    "ink touches the configured column safe-content edge",
                )
                if finding is not None and _count(inside_touch_columns) >= policy.minimum_ink_pixels:
                    findings.append(finding)

        if any(row.severity is RasterBoundaryStatus.FAIL for row in findings):
            status = RasterBoundaryStatus.FAIL
        elif findings:
            status = RasterBoundaryStatus.REVIEW_REQUIRED
        else:
            status = RasterBoundaryStatus.PASS
        return RasterBoundaryReport(
            status=status,
            image_size=size,
            page_mask_configured=safe_page is not None,
            column_masks_configured=len(resolved_columns),
            ink_pixels=_count(ink),
            ignored_page_border_pixels=ignored_page_border_pixels,
            ignored_mask_pixels=ignored_mask_pixels,
            findings=tuple(findings),
        )
    finally:
        _close_all(all_images)


# A descriptive alias for callers that use "check" in their gate names.
check_raster_boundary = audit_raster_boundary


__all__ = [
    "BoundaryMask",
    "BoundaryMaskKind",
    "MaskSource",
    "PixelBBox",
    "RasterBoundaryConfig",
    "RasterBoundaryFinding",
    "RasterBoundaryIssue",
    "RasterBoundaryMask",
    "RasterBoundaryPolicy",
    "RasterBoundaryReport",
    "RasterBoundaryStatus",
    "audit_raster_boundary",
    "check_raster_boundary",
]
