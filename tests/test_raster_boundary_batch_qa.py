from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw

from tools.raster_boundary_batch_qa import BatchStatus, collect_inputs, main, run_batch


def _render(path: Path, *, mark: tuple[int, int, int, int] | None = None) -> None:
    image = Image.new("L", (100, 80), 255)
    if mark is not None:
        ImageDraw.Draw(image).rectangle(mark, fill=0)
    image.save(path)


def test_directory_batch_passes_with_page_inset(tmp_path: Path) -> None:
    rendered = tmp_path / "rendered"
    rendered.mkdir()
    _render(rendered / "page-002.png", mark=(60, 30, 70, 34))
    _render(rendered / "page-001.png", mark=(20, 20, 30, 24))

    report = run_batch(collect_inputs((rendered,)), page_inset=(10, 8, 10, 8))

    assert report.status is BatchStatus.PASS
    assert report.input_count == 2
    assert report.error_count == 0
    assert [row.path.name for row in report.results] == ["page-001.png", "page-002.png"]
    assert all(row.report is not None for row in report.results)


def test_batch_is_fail_closed_for_spill_and_writes_summary(tmp_path: Path) -> None:
    rendered = tmp_path / "rendered"
    rendered.mkdir()
    _render(rendered / "page-001.png", mark=(7, 30, 14, 34))
    output = tmp_path / "qa.json"

    exit_code = main([
        "--input", str(rendered), "--page-inset", "10", "8", "10", "8", "--out", str(output),
    ])

    assert exit_code == 2
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["schema"] == "raster-boundary-batch-qa-v1"
    assert payload["status"] == "FAIL"
    assert payload["fail_count"] == 1
    assert payload["error_count"] == 0
    assert payload["results"][0]["report"]["findings"]


def test_edge_touch_is_review_required_not_fail(tmp_path: Path) -> None:
    page = tmp_path / "page.png"
    _render(page, mark=(10, 30, 14, 34))

    report = run_batch((page,), page_inset=(10, 8, 10, 8))

    assert report.status is BatchStatus.REVIEW_REQUIRED
    assert report.review_count == 1
    assert report.fail_count == 0


def test_page_mask_directory_resolves_by_stem(tmp_path: Path) -> None:
    rendered = tmp_path / "rendered"
    masks = tmp_path / "masks"
    rendered.mkdir()
    masks.mkdir()
    page = rendered / "page-001.png"
    _render(page, mark=(20, 20, 30, 24))
    mask = Image.new("L", (100, 80), 0)
    ImageDraw.Draw(mask).rectangle((10, 8, 90, 72), fill=255)
    mask.save(masks / "page-001.png")

    report = run_batch((page,), page_mask=masks)

    assert report.status is BatchStatus.PASS
    assert report.page_mask == str(masks)


def test_missing_page_safe_configuration_is_rejected(tmp_path: Path) -> None:
    page = tmp_path / "page.png"
    _render(page, mark=(20, 20, 30, 24))

    try:
        run_batch((page,))
    except ValueError as error:
        assert "page_inset or page_mask" in str(error)
    else:
        raise AssertionError("missing page-safe configuration must fail closed")


def test_empty_batch_is_rejected_even_with_a_safe_inset() -> None:
    try:
        run_batch((), page_inset=(10, 8, 10, 8))
    except ValueError as error:
        assert "input is empty" in str(error)
    else:
        raise AssertionError("an empty batch must fail closed")
