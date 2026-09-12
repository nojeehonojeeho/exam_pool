from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

from app.raster_boundary_qa import (
    RasterBoundaryConfig,
    RasterBoundaryIssue,
    RasterBoundaryStatus,
    audit_raster_boundary,
)


def _page() -> Image.Image:
    image = Image.new("L", (100, 80), 255)
    draw = ImageDraw.Draw(image)
    # A legitimate page frame is intentionally outside the content mask.  It
    # must not become a clipping finding.
    draw.rectangle((0, 0, 99, 79), outline=0, width=2)
    return image


def test_clean_columns_and_page_frame_pass_without_border_false_positive() -> None:
    image = _page()
    draw = ImageDraw.Draw(image)
    draw.rectangle((20, 20, 30, 24), fill=0)
    draw.rectangle((62, 30, 70, 34), fill=0)

    report = audit_raster_boundary(
        image,
        page_boundary_mask=(10, 8, 90, 72),
        column_boundary_masks=((14, 12, 45, 68), (55, 12, 86, 68)),
    )

    assert report.status is RasterBoundaryStatus.PASS
    assert report.findings == ()
    assert report.ignored_page_border_pixels > 0


def test_short_overflow_in_outer_strip_is_not_mistaken_for_page_frame() -> None:
    image = _page()
    # Unlike the full-width frame, this small glyph-like mark is clipping
    # evidence even though it reaches the image edge.
    ImageDraw.Draw(image).rectangle((0, 30, 3, 34), fill=0)

    report = audit_raster_boundary(image, page_boundary_mask=(10, 8, 90, 72))

    assert report.status is RasterBoundaryStatus.FAIL
    assert any(row.code is RasterBoundaryIssue.SAFE_BOUNDARY_SPILL for row in report.findings)


def test_ink_touching_safe_page_edge_requires_review() -> None:
    image = Image.new("L", (100, 80), 255)
    ImageDraw.Draw(image).rectangle((10, 30, 14, 34), fill=0)

    report = audit_raster_boundary(image, page_boundary_mask=(10, 8, 90, 72))

    assert report.status is RasterBoundaryStatus.REVIEW_REQUIRED
    assert any(row.code is RasterBoundaryIssue.SAFE_BOUNDARY_TOUCH for row in report.findings)
    finding = next(row for row in report.findings if row.code is RasterBoundaryIssue.SAFE_BOUNDARY_TOUCH)
    assert finding.bbox is not None
    assert finding.bbox[0] == 10


def test_ink_outside_safe_page_edge_fails_with_pixel_evidence() -> None:
    image = Image.new("L", (100, 80), 255)
    ImageDraw.Draw(image).rectangle((7, 30, 14, 34), fill=0)

    report = audit_raster_boundary(image, page_boundary_mask=(10, 8, 90, 72))

    assert report.status is RasterBoundaryStatus.FAIL
    finding = next(row for row in report.findings if row.code is RasterBoundaryIssue.SAFE_BOUNDARY_SPILL)
    assert finding.severity is RasterBoundaryStatus.FAIL
    assert finding.ink_pixels >= 3
    assert finding.bbox == (7, 30, 10, 35)
    assert finding["code"] == "safe_boundary_spill"


def test_column_gutter_spill_fails_even_when_page_boundary_is_valid() -> None:
    image = Image.new("L", (100, 80), 255)
    ImageDraw.Draw(image).rectangle((45, 30, 54, 34), fill=0)

    report = audit_raster_boundary(
        image,
        page_boundary_mask=(10, 8, 90, 72),
        column_boundary_masks=((14, 12, 45, 68), (55, 12, 86, 68)),
    )

    assert report.status is RasterBoundaryStatus.FAIL
    finding = next(row for row in report.findings if row.code is RasterBoundaryIssue.COLUMN_BOUNDARY_SPILL)
    assert finding.region == "columns"
    assert finding.bbox == (45, 30, 55, 35)


def test_explicit_ignore_mask_can_exclude_a_known_inner_ornament() -> None:
    image = Image.new("L", (100, 80), 255)
    ImageDraw.Draw(image).rectangle((6, 4, 12, 7), fill=0)
    ignore = Image.new("L", image.size, 0)
    ImageDraw.Draw(ignore).rectangle((6, 4, 12, 7), fill=255)

    report = audit_raster_boundary(
        image,
        page_boundary_mask=(10, 8, 90, 72),
        ignore_mask=ignore,
    )

    assert report.status is RasterBoundaryStatus.PASS
    assert report.findings == ()
    assert report.ignored_mask_pixels > 0


def test_config_object_controls_border_and_touch_policy() -> None:
    image = _page()
    draw = ImageDraw.Draw(image)
    draw.rectangle((20, 20, 30, 24), fill=0)
    policy = RasterBoundaryConfig(
        page_boundary_mask=(10, 8, 90, 72),
        ignore_page_border_px=0,
        touch_tolerance_px=0,
    )

    report = audit_raster_boundary(image, config=policy)

    assert report.status is RasterBoundaryStatus.FAIL
    assert any(row.code is RasterBoundaryIssue.SAFE_BOUNDARY_SPILL for row in report.findings)


def test_missing_mask_is_review_required_and_fail_closed() -> None:
    image = Image.new("L", (40, 30), 255)
    ImageDraw.Draw(image).rectangle((15, 10, 20, 14), fill=0)

    report = audit_raster_boundary(image)

    assert report.status is RasterBoundaryStatus.REVIEW_REQUIRED
    assert report.findings[0].code is RasterBoundaryIssue.BOUNDARY_MASK_MISSING


def test_render_path_is_supported(tmp_path: Path) -> None:
    image_path = tmp_path / "render.png"
    image = Image.new("RGB", (40, 30), "white")
    ImageDraw.Draw(image).rectangle((15, 10, 20, 14), fill="black")
    image.save(image_path)

    report = audit_raster_boundary(image_path, page_mask=(4, 4, 36, 26))

    assert report.status is RasterBoundaryStatus.PASS
