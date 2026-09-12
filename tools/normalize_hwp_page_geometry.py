"""Apply measured source-PDF page geometry to HWP/HWPX files.

This helper is deliberately serial and writes only to a caller-provided new
directory.  It does not mutate the source document.  The source PDF is used
only to measure the median MediaBox across pages; the caller supplies the
input HWPX files and a role (problem, solution, or integrated).  Integrated
documents use the problem geometry because the main body is the problem
sequence and native endnote bodies render at document end.

The helper is a geometry normalizer, not a source-fidelity proof.  A release
still requires the source manifest, formula evidence, COM readback, visual
review, and native-endnote gates.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
from pathlib import Path
import statistics
from typing import Any

import fitz

from app.integrations.hwp_security import create_secure_hwp


def median_media_box_mm(pdf: Path) -> tuple[float, float, dict[str, Any]]:
    """Return the median source page width/height in millimetres."""
    pdf = Path(pdf)
    doc = fitz.open(pdf)
    try:
        widths = [float(page.rect.width) * 25.4 / 72.0 for page in doc]
        heights = [float(page.rect.height) * 25.4 / 72.0 for page in doc]
    finally:
        doc.close()
    if not widths:
        raise ValueError(f"source PDF has no pages: {pdf}")
    width = round(statistics.median(widths), 1)
    height = round(statistics.median(heights), 1)
    return width, height, {
        "method": "median_media_box_pt_to_mm",
        "pdf": str(pdf.resolve()),
        "page_count": len(widths),
        "width_mm": width,
        "height_mm": height,
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_one(
    input_hwpx: Path,
    output_dir: Path,
    *,
    width_mm: float,
    height_mm: float,
    source_geometry: dict[str, Any],
) -> dict[str, Any]:
    """Open one HWPX, set all-section geometry, and save HWP/HWPX pair."""
    input_hwpx = Path(input_hwpx)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_hwp = output_dir / f"{input_hwpx.stem}.hwp"
    output_hwpx = output_dir / f"{input_hwpx.stem}.hwpx"
    row: dict[str, Any] = {
        "input": str(input_hwpx.resolve()),
        "output_hwp": str(output_hwp.resolve()),
        "output_hwpx": str(output_hwpx.resolve()),
        "source_geometry": source_geometry,
        "status": "FAIL",
    }
    hwp = None
    try:
        hwp = create_secure_hwp(new=True, visible=False, on_quit=False)
        row["register_module_return"] = getattr(
            getattr(hwp, "_hwp_security_registration", None), "returned", None
        )
        if not hwp.open(str(input_hwpx), format="HWPX", arg="forceopen:true;suspendpassword:true"):
            raise RuntimeError("HWPX_OPEN_FAILED")
        row["input_page_count"] = int(getattr(hwp, "PageCount", 0) or 0)
        before = hwp.get_pagedef_as_dict("eng")
        page_def = dict(before)
        page_def.update({"PaperWidth": float(width_mm), "PaperHeight": float(height_mm), "Landscape": 0})
        if not hwp.set_pagedef(page_def, apply="all"):
            raise RuntimeError("PAGEDEF_SET_FAILED")
        row["pagedef_before"] = before
        row["pagedef_after"] = hwp.get_pagedef_as_dict("eng")
        if not hwp.save_as(str(output_hwp), format="HWP", arg="backup:false;autosave:false"):
            raise RuntimeError("HWP_SAVE_FAILED")
        if not hwp.save_as(str(output_hwpx), format="HWPX", arg="backup:false;autosave:false"):
            raise RuntimeError("HWPX_SAVE_FAILED")
        row["outputs"] = {
            "hwp": {"exists": output_hwp.is_file(), "sha256": _sha256(output_hwp)},
            "hwpx": {"exists": output_hwpx.is_file(), "sha256": _sha256(output_hwpx)},
        }
        row["status"] = "PASS"
    except Exception as exc:  # pragma: no cover - requires Windows Hanword
        row["error"] = repr(exc)
    finally:
        if hwp is not None:
            try:
                hwp.quit(save=False)
            except Exception as exc:  # pragma: no cover - COM cleanup
                row["quit_error"] = repr(exc)
    return row


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", action="append", required=True, type=Path,
                        help="input HWPX path; repeat for each role")
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--source-pdf", required=True, type=Path,
                        help="source PDF whose median MediaBox is applied")
    args = parser.parse_args(argv)
    width, height, source_geometry = median_media_box_mm(args.source_pdf)
    rows = [normalize_one(path, args.output_dir, width_mm=width, height_mm=height,
                          source_geometry=source_geometry) for path in args.input]
    report = {
        "schema": "hwp-page-geometry-normalization-v1",
        "created_at": _dt.datetime.now().isoformat(timespec="seconds"),
        "source_geometry": source_geometry,
        "document_count": len(rows),
        "status": "PASS" if rows and all(row["status"] == "PASS" for row in rows) else "REVIEW_REQUIRED",
        "rows": rows,
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    report_path = args.output_dir / "page-geometry-normalization-report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": report["status"], "document_count": len(rows),
                      "report": str(report_path.resolve())}, ensure_ascii=False))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
