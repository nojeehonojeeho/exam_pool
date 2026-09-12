from pathlib import Path

import fitz

from tools.normalize_hwp_page_geometry import median_media_box_mm


def test_median_media_box_is_converted_to_mm(tmp_path: Path) -> None:
    source = tmp_path / "source.pdf"
    document = fitz.open()
    try:
        document.new_page(width=612.0, height=852.0)
        document.new_page(width=614.0, height=854.0)
        document.save(source)
    finally:
        document.close()

    width, height, evidence = median_media_box_mm(source)

    assert width == round(613.0 * 25.4 / 72.0, 1)
    assert height == round(853.0 * 25.4 / 72.0, 1)
    assert evidence["method"] == "median_media_box_pt_to_mm"
    assert evidence["page_count"] == 2
