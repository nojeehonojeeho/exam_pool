import xml.etree.ElementTree as ET

from tools.normalize_hwp_table_widths import _patch_section_xml


NS = "http://www.hancom.co.kr/hwpml/2011/paragraph"


def _q(name: str) -> str:
    return f"{{{NS}}}{name}"


def _table(table_id: str, width: int, cell_widths: list[int]) -> ET.Element:
    table = ET.Element(_q("tbl"), {"id": table_id})
    ET.SubElement(table, _q("sz"), {"width": str(width), "height": "100"})
    row = ET.SubElement(table, _q("tr"))
    for value in cell_widths:
        cell = ET.SubElement(row, _q("tc"))
        ET.SubElement(cell, _q("cellSz"), {"width": str(value), "height": "100"})
    return table


def test_only_oversized_top_level_tables_are_scaled_to_text_width():
    root = ET.Element(_q("sec"))
    ET.SubElement(
        root,
        _q("pagePr"),
        {"width": "1000", "height": "1500"},
    )
    margin = root.find(_q("pagePr"))
    ET.SubElement(margin, _q("margin"), {"left": "100", "right": "100", "gutter": "0"})

    paragraph = ET.SubElement(root, _q("p"))
    run = ET.SubElement(paragraph, _q("run"))
    outer = _table("outer", 2000, [1000, 1000])
    run.append(outer)

    nested_cell = outer.find(f"./{_q('tr')}/{_q('tc')}")
    nested_cell.append(_table("nested", 1800, [900, 900]))

    patched, report = _patch_section_xml(ET.tostring(root, encoding="utf-8"))
    assert report["status"] == "PASS"
    assert len(report["tables"]) == 1
    assert report["tables"][0]["old_width"] == 2000
    assert report["tables"][0]["new_width"] == 800

    result = ET.fromstring(patched)
    outer_after = result.find(f"./{_q('p')}/{_q('run')}/{_q('tbl')}")
    assert outer_after.find(_q("sz")).attrib["width"] == "800"
    cells = outer_after.findall(f"./{_q('tr')}/{_q('tc')}")
    assert [cell.find(_q("cellSz")).attrib["width"] for cell in cells] == ["400", "400"]

    nested_after = cells[0].find(_q("tbl"))
    assert nested_after.find(_q("sz")).attrib["width"] == "1800"


def test_tables_that_fit_are_left_byte_semantically_unchanged():
    root = ET.Element(_q("sec"))
    ET.SubElement(root, _q("pagePr"), {"width": "1000", "height": "1500"})
    margin = root.find(_q("pagePr"))
    ET.SubElement(margin, _q("margin"), {"left": "100", "right": "100"})
    paragraph = ET.SubElement(root, _q("p"))
    run = ET.SubElement(paragraph, _q("run"))
    run.append(_table("fit", 800, [400, 400]))
    original = ET.tostring(root, encoding="utf-8")

    patched, report = _patch_section_xml(original)
    assert report["status"] == "PASS"
    assert report["tables"] == []
    assert ET.tostring(ET.fromstring(patched), encoding="utf-8") == original
