"""Normalize oversized native table widths after source page-geometry changes.

The legacy HIGH-END authoring files were composed on B4 (257x364 mm) and
contain top-level two-column tables whose absolute width is wider than the
measured source page's text area.  Merely changing ``pagePr`` therefore leaves
the right column clipped.  This helper scales oversized top-level tables to the
available text width and recursively scales a nested table only when it is
wider than its owning cell.  Direct-cell widths are scaled with their table,
then Hanword recalculates line segments during a serial open/save round trip.

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
from app.hwp_owned_quit import OwnedQuitError, quit_tracked_with_safe_fallback
from app.hwp_process_lifecycle import (
    HwpProcessSnapshot,
    HwpProcessWait,
    newly_started_hwp_processes,
    snapshot_hwp_processes,
    wait_for_hwp_processes_to_exit,
)


HWPUNIT_PER_MM = 283.465


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _tag(node: Any) -> str:
    return str(node.tag).rsplit("}", 1)[-1]


def _ancestors(node: Any, parent_map: dict[Any, Any]) -> list[Any]:
    """Return ancestors from the nearest parent outwards."""
    result: list[Any] = []
    cursor = parent_map.get(node)
    while cursor is not None:
        result.append(cursor)
        cursor = parent_map.get(cursor)
    return result


def _nearest_ancestor(node: Any, tag: str, parent_map: dict[Any, Any]) -> Any | None:
    """Return the nearest ancestor with ``tag``, if any."""
    return next((ancestor for ancestor in _ancestors(node, parent_map) if _tag(ancestor) == tag), None)


def _positive_width(node: Any, attribute: str = "width") -> int | None:
    """Read a positive HWP unit width without guessing when it is invalid."""
    try:
        value = int(node.attrib.get(attribute, "0"))
    except (AttributeError, TypeError, ValueError):
        return None
    return value if value > 0 else None


def _direct_cell_widths(table: Any) -> tuple[list[Any], list[int]]:
    """Return direct row cells and their declared widths.

    A zero marks a cell whose width is absent or invalid.  Such a table is
    still eligible for table-width normalization, but its cell widths are left
    untouched because there is no safe proportional basis for them.
    """
    cells = [
        cell
        for row in table.findall("./{*}tr")
        for cell in row.findall("./{*}tc")
    ]
    widths: list[int] = []
    for cell in cells:
        cell_size = cell.find("./{*}cellSz")
        widths.append(_positive_width(cell_size) if cell_size is not None else 0)
    return cells, widths


def _direct_cell_width_rows(table: Any) -> list[tuple[list[Any], list[int]]]:
    """Return direct cells grouped by row, preserving row-specific geometry."""
    rows: list[tuple[list[Any], list[int]]] = []
    for row in table.findall("./{*}tr"):
        cells = list(row.findall("./{*}tc"))
        widths: list[int] = []
        for cell in cells:
            cell_size = cell.find("./{*}cellSz")
            widths.append(_positive_width(cell_size) if cell_size is not None else 0)
        rows.append((cells, widths))
    return rows


def _scale_direct_cell_widths(
    table: Any,
    target: int,
) -> tuple[list[int], list[int], list[list[int]], list[list[int]]]:
    """Scale every direct row independently and return before/after snapshots.

    HWPX tables may have row-specific cell spans/width declarations.  Scaling
    only the first row (the former behavior) leaves later rows wider than the
    corrected table and can still clip a three-column answer table.  Each row
    with complete positive widths is therefore scaled so its own cell sum is
    exactly ``target``.  A row with incomplete geometry is left unchanged.
    """
    row_records = _direct_cell_width_rows(table)
    before_by_row = [widths[:] for _, widths in row_records]
    after_by_row: list[list[int]] = []
    for cells, before in row_records:
        if not cells or not all(before):
            after_by_row.append(before[:])
            continue
        positive_total = sum(before)
        scaled = [round(width * target / positive_total) for width in before]
        # Absorb rounding error in the final cell, preserving the row total.
        scaled[-1] += target - sum(scaled)
        for cell, value in zip(cells, scaled, strict=True):
            cell_size = cell.find("./{*}cellSz")
            if cell_size is not None:
                cell_size.set("width", str(max(1, value)))
        after_by_row.append(scaled)
    before = [width for row in before_by_row for width in row]
    after = [width for row in after_by_row for width in row]
    return before, after, before_by_row, after_by_row


def _cell_content_width(cell: Any) -> tuple[int | None, dict[str, int] | None]:
    """Return ``cellSz.width - cellMargin.left - cellMargin.right``.

    ``cellMargin`` is the HWPX content-box boundary, not the table's outer
    width.  Missing margins mean zero margin (the HWPX default); malformed
    explicit values are treated as unknown so the normalizer never guesses.
    """
    cell_size = cell.find("./{*}cellSz")
    cell_width = _positive_width(cell_size) if cell_size is not None else None
    if cell_width is None:
        return None, None
    margin_node = cell.find("./{*}cellMargin")
    margins = {"left": 0, "right": 0}
    if margin_node is not None:
        for side in margins:
            raw = margin_node.attrib.get(side, "0")
            try:
                value = int(raw)
            except (TypeError, ValueError):
                return None, None
            if value < 0:
                return None, None
            margins[side] = value
    content_width = cell_width - margins["left"] - margins["right"]
    if content_width <= 0:
        return None, margins
    return content_width, margins


def _patch_section_xml(payload: bytes) -> tuple[bytes, dict[str, Any]]:
    """Patch oversized tables in one section XML payload.

    Tables are visited in document order.  That makes an outer table's
    normalized direct-cell width the constraint seen by a nested table in the
    same cell, and likewise propagates through deeper nesting levels.
    """
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
        ancestors = _ancestors(table, parent_map)
        if not any(_tag(ancestor) == "sec" for ancestor in ancestors):
            continue

        owner_cell = _nearest_ancestor(table, "tc", parent_map)
        parent_table = _nearest_ancestor(owner_cell, "tbl", parent_map) if owner_cell is not None else None
        # A table without an owning cell is a page-level layout table.  A
        # table with an owning cell is nested and must use that immediate cell
        # as its available-width constraint.
        if owner_cell is None and parent_table is not None:
            continue
        parent_cell_width = None
        parent_cell_content_width = None
        parent_cell_margins = None
        constraint_kind = "page_text_area"
        if owner_cell is not None:
            parent_cell_size = owner_cell.find("./{*}cellSz")
            parent_cell_width = _positive_width(parent_cell_size) if parent_cell_size is not None else None
            parent_cell_content_width, parent_cell_margins = _cell_content_width(owner_cell)
            # Unknown cell geometry is not a license to guess.  Leave the
            # nested table unchanged and allow a later diagnostic to surface
            # the missing constraint.
            if parent_cell_width is None or parent_cell_content_width is None:
                continue

        size = table.find("./{*}sz")
        if size is None:
            continue
        try:
            old_width = int(size.attrib.get("width", "0"))
        except ValueError:
            continue
        if owner_cell is None:
            constraint_width = available
            constraint_kind = "page_text_area"
        else:
            try:
                column_count = int(table.attrib.get("colCnt", "0") or 0)
            except (TypeError, ValueError):
                column_count = 0
            if old_width > available and column_count >= 3:
                # A child declared wider than the whole page is a page-wide
                # object in HWP's column-relative coordinate system (e.g. a
                # 3-column answer table inside an endnote wrapper).  Capping
                # it at the page text width preserves that intent while
                # preventing right-edge clipping.  Smaller nested objects use
                # the owner's actual content box below.
                constraint_width = available
                constraint_kind = "page_text_area_nested_overflow"
            else:
                constraint_width = parent_cell_content_width
                constraint_kind = "immediate_cell_content"
        if constraint_width is None:  # pragma: no cover - guarded above
            continue
        if old_width <= constraint_width:
            continue
        target = constraint_width
        size.set("width", str(target))
        direct_widths, scaled, direct_widths_by_row, scaled_by_row = _scale_direct_cell_widths(table, target)
        level = sum(1 for ancestor in ancestors if _tag(ancestor) == "tbl")
        parent_table_id = parent_table.attrib.get("id") if parent_table is not None else None
        parent_cell_id = owner_cell.attrib.get("id") if owner_cell is not None else None
        parent_constraint = {
            "kind": constraint_kind,
            "available_width": constraint_width,
            "table_id": parent_table_id,
            "cell_id": parent_cell_id,
        }
        records.append({
            "table_id": table.attrib.get("id"),
            "level": level,
            "parent_table_id": parent_table_id,
            "parent_cell_id": parent_cell_id,
            "parent_cell_width": parent_cell_width,
            "parent_cell_content_width": parent_cell_content_width,
            "parent_cell_margins": parent_cell_margins,
            "parent_cell_available_width": parent_cell_content_width,
            "available_width": constraint_width,
            "constraint_kind": constraint_kind,
            "parent_constraint": parent_constraint,
            "old_width": old_width,
            "new_width": target,
            "direct_cell_widths_before": direct_widths,
            "direct_cell_widths_after": scaled,
            "direct_cell_widths_before_by_row": direct_widths_by_row,
            "direct_cell_widths_after_by_row": scaled_by_row,
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


def _require_hwp_process_snapshot(
    snapshot_fn: Any = None,
) -> HwpProcessSnapshot:
    """Take one fail-closed process snapshot before a COM lifecycle edge."""
    snapshot_fn = snapshot_fn or snapshot_hwp_processes
    snapshot = snapshot_fn()
    if snapshot.status != "OK":
        raise RuntimeError("HWP_PID_ENUMERATION_UNAVAILABLE")
    return snapshot


def _open_tracked_hwp(
    *,
    snapshot_fn: Any = None,
    hwp_factory: Any = None,
) -> tuple[Any, dict[str, Any]]:
    """Create a secure HWP session only when its process identity is observed.

    A pre-existing Hwp.exe is never treated as ownership evidence.  If the
    process enumerator is unavailable or no new PID+creation-time identity is
    observed, this function fails closed before any document operation.  It
    intentionally does not call ``quit`` in that case: ownership was not
    proven, so closing a pre-existing user's HWP session would be unsafe.
    """
    snapshot_fn = snapshot_fn or snapshot_hwp_processes
    hwp_factory = hwp_factory or create_secure_hwp
    before = _require_hwp_process_snapshot(snapshot_fn)
    hwp = hwp_factory(new=True, visible=False, on_quit=False)
    after = _require_hwp_process_snapshot(snapshot_fn)
    delta = newly_started_hwp_processes(before, after)
    if delta.status != "OK":
        raise RuntimeError("HWP_PID_ENUMERATION_UNAVAILABLE")
    if not delta.processes:
        raise RuntimeError("HWP_COM_PROCESS_NOT_OBSERVED")
    lifecycle: dict[str, Any] = {
        "before_start": before.as_dict(),
        "after_start": after.as_dict(),
        "delta": delta.as_dict(),
        "after_quit": None,
        "wait": None,
    }
    return hwp, {"tracked": delta.processes, "lifecycle": lifecycle}


def _quit_tracked_hwp(
    hwp: Any,
    tracking: dict[str, Any],
    *,
    snapshot_fn: Any = None,
    wait_timeout: float = 20.0,
) -> HwpProcessWait:
    """Quit one owned HWP session and require its observed process to exit."""
    snapshot_fn = snapshot_fn or snapshot_hwp_processes
    quit_error: BaseException | None = None
    quit_record: dict[str, Any] | None = None
    identities = tracking["tracked"]
    try:
        # Ownership has already been proven by _open_tracked_hwp.  The
        # fallback itself still checks that evidence and IsModified=False.
        quit_record = quit_tracked_with_safe_fallback(hwp, tracked=identities)
    except Exception as exc:  # pragma: no cover - COM path
        quit_error = exc
        quit_record = getattr(exc, "record", None)

    lifecycle = tracking["lifecycle"]
    if not isinstance(lifecycle, dict):  # pragma: no cover - defensive
        raise RuntimeError("HWP_LIFECYCLE_RECORD_INVALID")
    lifecycle["quit"] = quit_record
    after_quit = _require_hwp_process_snapshot(snapshot_fn)
    lifecycle["after_quit"] = after_quit.as_dict()
    if not identities:
        raise RuntimeError("HWP_COM_PROCESS_NOT_OBSERVED")
    result = wait_for_hwp_processes_to_exit(
        identities,
        snapshot=snapshot_fn,
        timeout=wait_timeout,
    )
    lifecycle["wait"] = result.as_dict()
    if not result.exited:
        raise RuntimeError(f"HWP_COM_PROCESS_NOT_EXITED:{result.status}")
    if quit_error is not None:
        code = getattr(quit_error, "code", "HWP_COM_QUIT_FAILED")
        raise RuntimeError(str(code)) from quit_error
    return result


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
    tracking: dict[str, Any] | None = None
    try:
        row["patch"] = _patched_hwpx(input_hwpx, patched)
        hwp, tracking = _open_tracked_hwp()
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
        if hwp is not None and tracking is not None:
            try:
                _quit_tracked_hwp(hwp, tracking)
            except Exception as exc:  # pragma: no cover
                row["quit_error"] = repr(exc)
                row["status"] = "FAIL"
            row["hwp_process_lifecycle"] = tracking.get("lifecycle")
        elif hwp is not None:
            # This branch is defensive; _open_tracked_hwp normally either
            # returns an owned session or raises before assignment.  Never
            # close an HWP session whose process identity was not proven.
            row["error"] = row.get("error", "HWP_COM_PROCESS_NOT_OBSERVED")
            row["status"] = "FAIL"
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
