"""Audit HWPX table widths against their actual owning geometry.

Changing a section's page size does not automatically resize native tables in
HWPX.  In particular, a table nested in a ``tc`` can remain wider than that
cell and its right edge can be clipped after Hanword renders the document.
This module is a read-only structural audit: it never changes the package and
does not require Hanword/COM.

The audit intentionally reports proof states rather than treating missing
geometry as a fit.  A definite overflow is ``FAIL``; missing or invalid
geometry is ``REVIEW_REQUIRED``.  This makes the result safe to use as a
release gate without silently turning an unknown width into a PASS.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable
from zipfile import BadZipFile, ZipFile


_SECTION_RE = re.compile(r"(?:^|/)section(\d+)\.xml$")


def _tag(node: Any) -> str:
    return str(node.tag).rsplit("}", 1)[-1]


def _ancestors(node: Any, parent_map: dict[Any, Any]) -> list[Any]:
    result: list[Any] = []
    cursor = parent_map.get(node)
    while cursor is not None:
        result.append(cursor)
        cursor = parent_map.get(cursor)
    return result


def _nearest(node: Any, tag: str, parent_map: dict[Any, Any]) -> Any | None:
    return next((ancestor for ancestor in _ancestors(node, parent_map) if _tag(ancestor) == tag), None)


def _positive_attr(node: Any | None, name: str) -> int | None:
    if node is None:
        return None
    try:
        value = int(node.attrib.get(name, "0"))
    except (AttributeError, TypeError, ValueError):
        return None
    return value if value > 0 else None


def _page_geometry(root: Any) -> tuple[int | None, int | None, dict[str, int], bool]:
    """Return page width, available text width, raw margins, and margin validity."""
    page = root.find(".//{*}pagePr")
    page_width = _positive_attr(page, "width")
    margin = page.find("./{*}margin") if page is not None else None
    raw: dict[str, int] = {}
    margin_valid = margin is not None
    for key in ("left", "right", "gutter"):
        try:
            raw[key] = max(0, int(margin.attrib.get(key, "0"))) if margin is not None else 0
        except (AttributeError, TypeError, ValueError):
            raw[key] = 0
            margin_valid = False
    available = page_width - sum(raw.values()) if page_width is not None and margin_valid else None
    return page_width, available if available is not None and available > 0 else None, raw, margin_valid


def _table_width(table: Any) -> int | None:
    return _positive_attr(table.find("./{*}sz"), "width")


def _cell_width(cell: Any) -> int | None:
    return _positive_attr(cell.find("./{*}cellSz"), "width")


def _cell_content_width(cell: Any) -> tuple[int | None, dict[str, int] | None]:
    """Return the content-box width used by the normalizer.

    A nested table normally belongs inside the cell content box, rather than
    the outer cell border.  Missing margins are the HWPX default (zero), but
    malformed explicit margins are unknown and therefore cannot establish a
    safe constraint.
    """
    cell_width = _cell_width(cell)
    if cell_width is None:
        return None, None
    margin = cell.find("./{*}cellMargin")
    margins = {"left": 0, "right": 0}
    if margin is not None:
        for side in margins:
            try:
                value = int(margin.attrib.get(side, "0"))
            except (AttributeError, TypeError, ValueError):
                return None, None
            if value < 0:
                return None, None
            margins[side] = value
    content_width = cell_width - margins["left"] - margins["right"]
    return (content_width, margins) if content_width > 0 else (None, margins)


def _column_count(table: Any) -> int | None:
    try:
        value = int(table.attrib.get("colCnt", "0") or 0)
    except (AttributeError, TypeError, ValueError):
        return None
    return value if value > 0 else None


def _row_cell_width_sums(table: Any) -> tuple[list[int | None], list[dict[str, Any]]]:
    """Return each direct row's declared width sum and any geometry findings."""
    sums: list[int | None] = []
    findings: list[dict[str, Any]] = []
    for row_ordinal, row in enumerate(table.findall("./{*}tr"), 1):
        cells = list(row.findall("./{*}tc"))
        widths = [_cell_width(cell) for cell in cells]
        if not cells or not all(width is not None for width in widths):
            sums.append(None)
            continue
        total = sum(width for width in widths if width is not None)
        sums.append(total)
        findings.append({"row_ordinal": row_ordinal, "width_sum": total})
    return sums, findings


def _direct_cells(table: Any) -> list[Any]:
    return list(table.findall("./{*}tr/{*}tc"))


def audit_section_xml(payload: bytes | str, *, section: str = "section.xml") -> dict[str, Any]:
    """Audit one HWPX section XML payload without modifying it."""
    import xml.etree.ElementTree as ET

    findings: list[dict[str, Any]] = []
    info: list[dict[str, Any]] = []
    try:
        root = ET.fromstring(payload)
    except (ET.ParseError, TypeError, ValueError) as exc:
        return {
            "section": section,
            "status": "FAIL",
            "tables_scanned": 0,
            "findings": [{"code": "SECTION_XML_INVALID", "section": section, "detail": str(exc)}],
        }

    page_width, available_text_width, margins, margin_valid = _page_geometry(root)
    if page_width is None:
        findings.append({"code": "PAGE_WIDTH_MISSING_OR_INVALID", "section": section})
    if not margin_valid:
        findings.append({"code": "PAGE_MARGIN_MISSING_OR_INVALID", "section": section})
    if available_text_width is None:
        findings.append({"code": "PAGE_TEXT_WIDTH_MISSING_OR_INVALID", "section": section})

    parent_map = {child: parent for parent in root.iter() for child in parent}
    tables = [node for node in root.iter() if _tag(node) == "tbl"]
    records: list[dict[str, Any]] = []
    for ordinal, table in enumerate(tables, 1):
        owner_cell = _nearest(table, "tc", parent_map)
        parent_table = _nearest(owner_cell, "tbl", parent_map) if owner_cell is not None else None
        width_node = table.find("./{*}sz")
        table_width = _table_width(table)
        level = sum(1 for ancestor in _ancestors(table, parent_map) if _tag(ancestor) == "tbl")
        record: dict[str, Any] = {
            "ordinal": ordinal,
            "table_id": table.attrib.get("id"),
            "level": level,
            "parent_table_id": parent_table.attrib.get("id") if parent_table is not None else None,
            "owner_cell_id": owner_cell.attrib.get("id") if owner_cell is not None else None,
            "declared_width": table_width,
            "column_count": _column_count(table),
            "constraint_kind": "owner_cell" if owner_cell is not None else "page_text_area",
            "constraint_width": None,
        }
        if width_node is None or table_width is None:
            findings.append({
                "code": "TABLE_WIDTH_MISSING_OR_INVALID",
                "section": section,
                **record,
            })
            records.append(record)
            continue

        row_sums, row_records = _row_cell_width_sums(table)
        record["direct_row_width_sums"] = row_sums
        if owner_cell is not None:
            constraint = _cell_width(owner_cell)
            content_width, cell_margins = _cell_content_width(owner_cell)
            record["constraint_width"] = constraint
            record["owner_cell_content_width"] = content_width
            record["owner_cell_margins"] = cell_margins
            if constraint is None:
                findings.append({
                    "code": "OWNER_CELL_WIDTH_MISSING_OR_INVALID",
                    "section": section,
                    **record,
                })
            elif content_width is None:
                findings.append({
                    "code": "OWNER_CELL_CONTENT_WIDTH_MISSING_OR_INVALID",
                    "section": section,
                    **record,
                })
            elif (
                table_width > constraint
                and available_text_width is not None
                and table_width > available_text_width
            ):
                # A page-wide object that is still wider than the page is a
                # definite clipping error; the normalizer can only make it
                # safe by capping it to available_text_width.
                findings.append({
                    "code": "TABLE_WIDTH_EXCEEDS_PAGE_TEXT_AREA",
                    "section": section,
                    **record,
                    "overflow": table_width - (available_text_width or 0),
                })
            elif (
                table_width > content_width
                and available_text_width is not None
                and table_width == available_text_width
                and (record["column_count"] or 0) >= 3
            ):
                # HWP's column-relative coordinates can encode a 3+ column
                # page-wide table inside a narrow wrapper/endnote cell.  The
                # normalizer explicitly caps such a table at page text width;
                # treating it as an ordinary child-cell overflow would be a
                # false FAIL.  Keep an INFO record and require row sums to be
                # closed below.
                exception = {
                    "code": "PAGE_WIDE_NESTED_TABLE_ALLOWED",
                    "section": section,
                    **record,
                    "page_text_width": available_text_width,
                    "owner_cell_content_width": content_width,
                    "row_width_records": row_records,
                }
                info.append(exception)
                record["geometry_exception"] = "page_wide_nested_table"
            elif table_width > content_width:
                findings.append({
                    "code": "TABLE_WIDTH_EXCEEDS_OWNER_CELL",
                    "section": section,
                    **record,
                    "overflow": table_width - content_width,
                })
        else:
            record["constraint_width"] = available_text_width
            if available_text_width is not None and table_width > available_text_width:
                findings.append({
                    "code": "TABLE_WIDTH_EXCEEDS_PAGE_TEXT_AREA",
                    "section": section,
                    **record,
                    "overflow": table_width - available_text_width,
                })

        # A complete row whose direct cells do not fill the declared table is
        # not safe evidence of a closed layout.  Overfull rows are definite
        # clipping; underfull rows are review-only because spans/omissions can
        # be intentional in HWPX.
        for row_record in row_records:
            if row_record["width_sum"] > table_width:
                findings.append({
                    "code": "TABLE_ROW_WIDTH_SUM_EXCEEDS_TABLE",
                    "section": section,
                    **record,
                    **row_record,
                    "overflow": row_record["width_sum"] - table_width,
                })
            elif row_record["width_sum"] != table_width:
                findings.append({
                    "code": "TABLE_ROW_WIDTH_SUM_MISMATCH",
                    "section": section,
                    **record,
                    **row_record,
                    "difference": row_record["width_sum"] - table_width,
                })

        # A row cell wider than its table is an independent, definite source
        # of clipping even when the table itself fits its owner.
        for cell_ordinal, cell in enumerate(_direct_cells(table), 1):
            cell_width = _cell_width(cell)
            if cell_width is not None and cell_width > table_width:
                findings.append({
                    "code": "CELL_WIDTH_EXCEEDS_TABLE",
                    "section": section,
                    **record,
                    "cell_ordinal": cell_ordinal,
                    "cell_id": cell.attrib.get("id"),
                    "cell_width": cell_width,
                    "overflow": cell_width - table_width,
                })
        records.append(record)

    definite = [item for item in findings if item["code"] in {
        "TABLE_WIDTH_EXCEEDS_OWNER_CELL",
        "TABLE_WIDTH_EXCEEDS_PAGE_TEXT_AREA",
        "CELL_WIDTH_EXCEEDS_TABLE",
        "TABLE_ROW_WIDTH_SUM_EXCEEDS_TABLE",
        "SECTION_XML_INVALID",
    }]
    status = "FAIL" if definite else ("REVIEW_REQUIRED" if findings else "PASS")
    return {
        "section": section,
        "status": status,
        "page_width": page_width,
        "margins": margins,
        "margin_geometry_valid": margin_valid,
        "available_text_width": available_text_width,
        "tables_scanned": len(tables),
        "tables": records,
        "info": info,
        "findings": findings,
    }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _section_names(names: Iterable[str]) -> list[str]:
    return sorted(
        (name for name in names if _SECTION_RE.search(name)),
        key=lambda name: int(_SECTION_RE.search(name).group(1)),
    )


def audit_hwpx(path: str | Path) -> dict[str, Any]:
    """Audit all section XML files in one HWPX package."""
    source = Path(path)
    base: dict[str, Any] = {
        "schema": "hwpx-nested-table-geometry-audit-v1",
        "input": str(source.resolve()),
        "status": "FAIL",
        "findings": [],
        "sections": [],
    }
    if not source.is_file():
        base["findings"] = [{"code": "INPUT_MISSING"}]
        return base
    base["input_sha256"] = _sha256(source)
    try:
        with ZipFile(source) as package:
            names = _section_names(info.filename for info in package.infolist())
            if not names:
                base["findings"] = [{"code": "SECTION_XML_MISSING"}]
                return base
            for name in names:
                section_report = audit_section_xml(package.read(name), section=name)
                base["sections"].append(section_report)
                base["findings"].extend(section_report["findings"])
    except (BadZipFile, OSError, KeyError) as exc:
        base["findings"] = [{"code": "HWPX_PACKAGE_INVALID", "detail": str(exc)}]
        return base
    if any(section["status"] == "FAIL" for section in base["sections"]):
        base["status"] = "FAIL"
    elif any(section["status"] == "REVIEW_REQUIRED" for section in base["sections"]):
        base["status"] = "REVIEW_REQUIRED"
    else:
        base["status"] = "PASS"
    base["summary"] = {
        "section_count": len(base["sections"]),
        "table_count": sum(section["tables_scanned"] for section in base["sections"]),
        "finding_count": len(base["findings"]),
        "info_count": sum(len(section.get("info", [])) for section in base["sections"]),
        "definite_overflow_count": sum(
            1 for finding in base["findings"] if finding["code"].endswith("EXCEEDS_OWNER_CELL")
            or finding["code"].endswith("EXCEEDS_PAGE_TEXT_AREA")
            or finding["code"] == "CELL_WIDTH_EXCEEDS_TABLE"
        ),
    }
    return base


def audit_many(paths: Iterable[str | Path]) -> dict[str, Any]:
    reports = [audit_hwpx(path) for path in paths]
    statuses = [report["status"] for report in reports]
    status = (
        "FAIL"
        if "FAIL" in statuses
        else ("REVIEW_REQUIRED" if "REVIEW_REQUIRED" in statuses or not reports else "PASS")
    )
    return {
        "schema": "hwpx-nested-table-geometry-audit-v1",
        "status": status,
        "document_count": len(reports),
        "info_count": sum(report.get("summary", {}).get("info_count", 0) for report in reports),
        "reports": reports,
    }


def write_report(report: dict[str, Any], path: str | Path) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return destination
