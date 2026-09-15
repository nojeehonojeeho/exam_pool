"""Run target-bound, 300dpi automatic visual evidence for a HWP/HWPX pair.

This validates physical page size, rendering coverage, and blank-page signals.
It intentionally does not claim human inspection; a release gate must carry a
separate human-attested representative-page ledger where that is required.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import fitz


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inspect(path: Path) -> dict:
    with fitz.open(path) as pdf:
        pages = []
        bad_sizes = []
        low_signal = []
        for number, page in enumerate(pdf, 1):
            pix = page.get_pixmap(dpi=300, colorspace=fitz.csRGB, alpha=False)
            size = (round(float(page.rect.width), 3), round(float(page.rect.height), 3))
            if abs(size[0] - 728) > 1 or abs(size[1] - 1031) > 1:
                bad_sizes.append(number)
            text = page.get_text("text").strip()
            drawings = len(page.get_drawings())
            images = len(page.get_images(full=True))
            if not text and not drawings and not images:
                low_signal.append(number)
            pages.append({"page": number, "width_px": pix.width, "height_px": pix.height,
                          "render_sha256": hashlib.sha256(pix.samples).hexdigest(),
                          "text_chars": len(text), "drawing_count": drawings, "image_count": images,
                          "size_pt": size})
    return {"sha256": sha(path), "page_count": len(pages), "pages": pages,
            "bad_page_sizes": bad_sizes, "no_signal_pages": low_signal}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hwp-pdf", type=Path, required=True)
    parser.add_argument("--hwpx-pdf", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        raise FileExistsError(args.out)
    hwp = inspect(args.hwp_pdf)
    hwpx = inspect(args.hwpx_pdf)
    checks = {
        "hwp_all_pages_rendered_300dpi": not hwp["bad_page_sizes"] and not hwp["no_signal_pages"],
        "hwpx_all_pages_rendered_300dpi": not hwpx["bad_page_sizes"] and not hwpx["no_signal_pages"],
        "hwp_hwpx_pdf_page_count_equal": hwp["page_count"] == hwpx["page_count"],
    }
    result = {"schema": "teacher-visual-qa/v1", "status": "PASS" if all(checks.values()) else "REVIEW_REQUIRED",
              "dpi": 300, "checks": checks, "hwp": hwp, "hwpx": hwpx,
              "automatic_only": True, "human_reviewed_pages": []}
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": result["status"], "hwp_pages": hwp["page_count"], "hwpx_pages": hwpx["page_count"], "checks": checks}, ensure_ascii=False))
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
