"""Normalize oversized native table widths after source page-geometry changes.

The legacy HIGH-END authoring files were composed on B4 (257x364 mm) and
contain top-level two-column tables whose absolute width is wider than the
measured source page's text area.  Merely changing ``pagePr`` therefore leaves
the right column clipped.  This helper scales only those top-level table and
direct-cell widths to the available text width, then lets Hanword recalculate
line segments during a serial open/save round trip.

It writes to a fresh output directory and never mutates an input HWPX.  It is
not a content or formula-fidelity proof; those gates remain separate.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile

# Allow the tool to be invoked from either the repository root or its tools/
# directory, matching the other production helpers.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.integrations.hwp_security import create_secure_hwp


HWPUNIT_PER_MM = 283.465


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _tag(node: Any) -> str:
    return str(node.tag).rsplit("}", 1)[-1]


def _patch_section_xml(payload: bytes) -> tuple[bytes, dict[str, Any]]:
    """Patch oversized top-level tables in one section XML payload."""
    import xml.etree.ElementTree as ET

    root = ET.fromstring(payload)
    # Section files may wrap pagePr in a section-properties container; use a
    # descendant lookup while still requiring one concrete page definition.
    page = root.find(".//{*}pagePr")
    if page is None:
        return payload, {"status": "REVIEW_REQUIRED", "reason": "PAGEPR_MISSING", "tables": []}
    try:
        page_width = int(page.attrib["width"])
        margin = page.find("./{*}margin")
        left = int(margin.attrib.get("left", "0")) if margin is not None else 0
        right = int(margin.attrib.get("right", "0")) if margin is not None else 0
        gutter = int(margin.attrib.get("gutter", "0")) if margin is not None else 0
    except (KeyError, TypeError, ValueError) as exc:
        return payload, {"status": "REVIEW_REQUIRED", "reason": f"PAGEPR_INVALID:{exc}", "tables": []}
    available = max(1, page_width - left - right - gutter)
    parent_map = {child: parent for parent in root.iter() for child in parent}
    records: list[dict[str, Any]] = []
    for table in root.iter():
        if _tag(table) != "tbl":
            continue
        parent = parent_map.get(table)
        # Only tables directly inside a paragraph/run in the section are page
        # layout tables.  Nested choice/condition tables must retain their own
        # widths relative to the containing cell.
        ancestors: list[str] = []
        cursor = parent
        while cursor is not None and len(ancestors) < 6:
            ancestors.append(_tag(cursor))
            cursor = parent_map.get(cursor)
        if not ("sec" in ancestors and "tc" not in ancestors):
            continue
        size = table.find("./{*}sz")
        if size is None:
            continue
        try:
            old_width = int(size.attrib.get("width", "0"))
        except ValueError:
            continue
        if old_width <= available:
            continue
        target = available
        size.set("width", str(target))
        cells = [child for child in table.findall("./{*}tr/{*}tc")]
        direct_widths: list[int] = []
        for cell in cells:
            cell_size = cell.find("./{*}cellSz")
            if cell_size is None:
                direct_widths.append(0)
                continue
            try:
                direct_widths.append(max(0, int(cell_size.attrib.get("width", "0"))))
            except ValueError:
                direct_widths.append(0)
        positive_total = sum(direct_widths)
        if cells and positive_total:
            scaled = [round(width * target / positive_total) for width in direct_widths]
            # absorb rounding error in the final cell, preserving exact total
            scaled[-1] += target - sum(scaled)
            for cell, value in zip(cells, scaled, strict=True):
                cell_size = cell.find("./{*}cellSz")
                if cell_size is not None:
                    cell_size.set("width", str(max(1, value)))
        records.append({
            "table_id": table.attrib.get("id"),
            "old_width": old_width,
            "new_width": target,
            "direct_cell_widths_before": direct_widths,
            "direct_cell_widths_after": scaled if cells and positive_total else [],
            "available_text_width": available,
        })
    if not records:
        return payload, {
            "status": "PASS",
            "page_width": page_width,
            "available_text_width": available,
            "tables": [],
        }
    ET.register_namespace("hp", "http://www.hancom.co.kr/hwpml/2011/paragraph")
    ET.register_namespace("hc", "http://www.hancom.co.kr/hwpml/2011/core")
    return ET.tostring(root, encoding="utf-8", xml_declaration=True), {
        "status": "PASS",
        "page_width": page_width,
        "available_text_width": available,
        "tables": records,
    }


def _patched_hwpx(input_path: Path, output_path: Path) -> dict[str, Any]:
    """Create a patched temporary HWPX and return per-section records."""
    records: list[dict[str, Any]] = []
    with ZipFile(input_path) as source, ZipFile(output_path, "w", ZIP_DEFLATED) as target:
        for info in source.infolist():
            payload = source.read(info.filename)
            if info.filename.startswith("Contents/section") and info.filename.endswith(".xml"):
                patched, record = _patch_section_xml(payload)
                payload = patched
                record["section"] = info.filename
                records.append(record)
            target.writestr(info, payload)
    return {"sections": records, "input_sha256": _sha256(input_path), "patched_sha256": _sha256(output_path)}


def normalize_one(input_hwpx: Path, output_dir: Path) -> dict[str, Any]:
    input_hwpx = Path(input_hwpx).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    output_hwp = output_dir / f"{input_hwpx.stem}.hwp"
    output_hwpx = output_dir / f"{input_hwpx.stem}.hwpx"
    row: dict[str, Any] = {
        "input": str(input_hwpx),
        "output_hwp": str(output_hwp.resolve()),
        "output_hwpx": str(output_hwpx.resolve()),
        "status": "FAIL",
    }
    tmp_dir = Path(tempfile.mkdtemp(prefix="hwp-table-width-", dir=str(output_dir)))
    patched = tmp_dir / input_hwpx.name
    hwp = None
    try:
        row["patch"] = _patched_hwpx(input_hwpx, patched)
        hwp = create_secure_hwp(new=True, visible=False, on_quit=False)
        row["register_module_return"] = getattr(getattr(hwp, "_hwp_security_registration", None), "returned", None)
        if not hwp.open(str(patched), format="HWPX", arg="forceopen:true;suspendpassword:true"):
            raise RuntimeError("HWPX_OPEN_FAILED")
        row["page_count_before_save"] = int(getattr(hwp, "PageCount", 0) or 0)
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
            except Exception as exc:  # pragma: no cover
                row["quit_error"] = repr(exc)
        shutil.rmtree(tmp_dir, ignore_errors=True)
    return row


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", action="append", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args(argv)
    rows = [normalize_one(path, args.output_dir) for path in args.input]
    report = {
        "schema": "hwp-table-width-normalization-v1",
        "created_at": _dt.datetime.now().isoformat(timespec="seconds"),
        "document_count": len(rows),
        "status": "PASS" if rows and all(row["status"] == "PASS" for row in rows) else "REVIEW_REQUIRED",
        "rows": rows,
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    path = args.output_dir / "table-width-normalization-report.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "document_count": len(rows), "report": str(path.resolve())}, ensure_ascii=False))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
