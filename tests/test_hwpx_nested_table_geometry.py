from __future__ import annotations

import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from app.hwpx_nested_table_geometry import audit_hwpx, audit_section_xml


NS = "http://www.hancom.co.kr/hwpml/2011/paragraph"


def q(name: str) -> str:
    return f"{{{NS}}}{name}"


def table(table_id: str, width: int, cell_widths: list[int]) -> ET.Element:
    value = ET.Element(q("tbl"), {"id": table_id})
    ET.SubElement(value, q("sz"), {"width": str(width), "height": "100"})
    row = ET.SubElement(value, q("tr"))
    for ordinal, cell_width in enumerate(cell_widths, 1):
        cell = ET.SubElement(row, q("tc"), {"id": f"{table_id}-c{ordinal}"})
        ET.SubElement(cell, q("cellSz"), {"width": str(cell_width), "height": "100"})
    return value


def section(*tables: ET.Element, page_width: int = 1000, left: int = 100, right: int = 100) -> bytes:
    root = ET.Element(q("sec"))
    page = ET.SubElement(root, q("pagePr"), {"width": str(page_width), "height": "1500"})
    ET.SubElement(page, q("margin"), {"left": str(left), "right": str(right), "gutter": "0"})
    para = ET.SubElement(root, q("p"))
    run = ET.SubElement(para, q("run"))
    for value in tables:
        run.append(value)
    return ET.tostring(root, encoding="utf-8")


def test_definite_page_and_nested_overflow_are_distinguished() -> None:
    outer = table("outer", 1200, [600, 600])
    first = outer.find(f"./{q('tr')}/{q('tc')}")
    assert first is not None
    first.append(table("nested", 700, [350, 350]))
    report = audit_section_xml(section(outer))
    assert report["status"] == "FAIL"
    codes = [finding["code"] for finding in report["findings"]]
    assert "TABLE_WIDTH_EXCEEDS_PAGE_TEXT_AREA" in codes
    assert "TABLE_WIDTH_EXCEEDS_OWNER_CELL" in codes
    nested = next(record for record in report["tables"] if record["table_id"] == "nested")
    assert nested["constraint_kind"] == "owner_cell"
    assert nested["constraint_width"] == 600


def test_fitting_nested_table_has_no_finding() -> None:
    outer = table("outer", 800, [400, 400])
    first = outer.find(f"./{q('tr')}/{q('tc')}")
    assert first is not None
    first.append(table("nested-fit", 350, [175, 175]))
    report = audit_section_xml(section(outer))
    assert report["status"] == "PASS"
    assert report["findings"] == []


def test_page_wide_three_column_nested_table_is_info_not_owner_overflow() -> None:
    outer = table("wrapper", 800, [400, 400])
    first = outer.find(f"./{q('tr')}/{q('tc')}")
    assert first is not None
    page_wide = table("answer-grid", 800, [200, 300, 300])
    page_wide.set("colCnt", "3")
    first.append(page_wide)
    report = audit_section_xml(section(outer))
    assert report["status"] == "PASS"
    assert report["findings"] == []
    assert [item["code"] for item in report["info"]] == ["PAGE_WIDE_NESTED_TABLE_ALLOWED"]
    assert report["info"][0]["direct_row_width_sums"] == [800]


def test_page_wide_nested_table_still_fails_if_above_page_width() -> None:
    outer = table("wrapper", 800, [400, 400])
    first = outer.find(f"./{q('tr')}/{q('tc')}")
    assert first is not None
    page_wide = table("answer-grid", 801, [267, 267, 267])
    page_wide.set("colCnt", "3")
    first.append(page_wide)
    report = audit_section_xml(section(outer))
    assert report["status"] == "FAIL"
    assert any(finding["code"] == "TABLE_WIDTH_EXCEEDS_PAGE_TEXT_AREA" for finding in report["findings"])
    assert not report["info"]


def test_page_wide_nested_table_requires_exact_direct_row_sum() -> None:
    outer = table("wrapper", 800, [400, 400])
    first = outer.find(f"./{q('tr')}/{q('tc')}")
    assert first is not None
    page_wide = table("answer-grid", 800, [200, 300, 200])
    page_wide.set("colCnt", "3")
    first.append(page_wide)
    report = audit_section_xml(section(outer))
    assert report["status"] == "REVIEW_REQUIRED"
    assert any(finding["code"] == "TABLE_ROW_WIDTH_SUM_MISMATCH" for finding in report["findings"])
    assert report["info"]


def test_missing_owner_width_is_review_required_not_fit() -> None:
    outer = table("outer", 800, [400, 400])
    first = outer.find(f"./{q('tr')}/{q('tc')}")
    assert first is not None
    first.find(q("cellSz")).attrib.pop("width")
    first.append(table("nested", 350, [175, 175]))
    report = audit_section_xml(section(outer))
    assert report["status"] == "REVIEW_REQUIRED"
    assert any(finding["code"] == "OWNER_CELL_WIDTH_MISSING_OR_INVALID" for finding in report["findings"])


def test_zip_audit_reports_input_hash_and_section_summary(tmp_path: Path) -> None:
    path = tmp_path / "sample.hwpx"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as package:
        package.writestr("Contents/section10.xml", section(table("fit", 800, [400, 400])))
        package.writestr("Contents/section2.xml", section(table("fit2", 800, [400, 400])))
    report = audit_hwpx(path)
    assert report["status"] == "PASS"
    assert report["input_sha256"]
    assert [section_report["section"] for section_report in report["sections"]] == [
        "Contents/section2.xml",
        "Contents/section10.xml",
    ]
    assert report["summary"]["table_count"] == 2
