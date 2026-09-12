import xml.etree.ElementTree as ET

import pytest

from app.hwp_process_lifecycle import HwpProcessIdentity, HwpProcessSnapshot
from tools.normalize_hwp_table_widths import (
    _open_tracked_hwp,
    _patch_section_xml,
    _quit_tracked_hwp,
)


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


def test_oversized_top_level_and_nested_tables_use_their_own_constraints():
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
    assert len(report["tables"]) == 2
    assert report["tables"][0]["old_width"] == 2000
    assert report["tables"][0]["new_width"] == 800
    assert report["tables"][0]["level"] == 0
    assert report["tables"][0]["parent_constraint"]["kind"] == "page_text_area"
    assert report["tables"][1]["table_id"] == "nested"
    assert report["tables"][1]["level"] == 1
    assert report["tables"][1]["parent_table_id"] == "outer"
    assert report["tables"][1]["parent_cell_width"] == 400
    assert report["tables"][1]["available_width"] == 400
    assert report["tables"][1]["parent_constraint"]["available_width"] == 400

    result = ET.fromstring(patched)
    outer_after = result.find(f"./{_q('p')}/{_q('run')}/{_q('tbl')}")
    assert outer_after.find(_q("sz")).attrib["width"] == "800"
    cells = outer_after.findall(f"./{_q('tr')}/{_q('tc')}")
    assert [cell.find(_q("cellSz")).attrib["width"] for cell in cells] == ["400", "400"]

    nested_after = cells[0].find(_q("tbl"))
    assert nested_after.find(_q("sz")).attrib["width"] == "400"
    assert [
        cell.find(_q("cellSz")).attrib["width"]
        for cell in nested_after.findall(f"./{_q('tr')}/{_q('tc')}")
    ] == ["200", "200"]


def test_nested_table_that_fits_its_parent_cell_is_preserved():
    root = ET.Element(_q("sec"))
    ET.SubElement(root, _q("pagePr"), {"width": "1000", "height": "1500"})
    margin = root.find(_q("pagePr"))
    ET.SubElement(margin, _q("margin"), {"left": "100", "right": "100"})

    paragraph = ET.SubElement(root, _q("p"))
    run = ET.SubElement(paragraph, _q("run"))
    outer = _table("outer", 1200, [600, 600])
    run.append(outer)
    nested_cell = outer.find(f"./{_q('tr')}/{_q('tc')}")
    nested = _table("nested-fit", 350, [175, 175])
    nested_cell.append(nested)
    original = ET.tostring(root, encoding="utf-8")

    patched, report = _patch_section_xml(original)

    assert report["status"] == "PASS"
    assert [record["table_id"] for record in report["tables"]] == ["outer"]
    result = ET.fromstring(patched)
    outer_after = result.find(f"./{_q('p')}/{_q('run')}/{_q('tbl')}")
    nested_after = outer_after.find(f"./{_q('tr')}/{_q('tc')}/{_q('tbl')}")
    assert outer_after.find(_q("sz")).attrib["width"] == "800"
    assert nested_after.find(_q("sz")).attrib["width"] == "350"
    assert [
        cell.find(_q("cellSz")).attrib["width"]
        for cell in nested_after.findall(f"./{_q('tr')}/{_q('tc')}")
    ] == ["175", "175"]


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


def test_nested_table_uses_owner_cell_content_box_after_margins():
    root = ET.Element(_q("sec"))
    ET.SubElement(root, _q("pagePr"), {"width": "60000", "height": "80000"})
    margin = root.find(_q("pagePr"))
    ET.SubElement(margin, _q("margin"), {"left": "500", "right": "500"})

    paragraph = ET.SubElement(root, _q("p"))
    run = ET.SubElement(paragraph, _q("run"))
    outer = _table("outer", 50003, [25002, 25001])
    run.append(outer)
    owner = outer.find(f"./{_q('tr')}/{_q('tc')}")
    ET.SubElement(owner, _q("cellMargin"), {"left": "1133", "right": "1133"})
    owner.append(_table("nested", 27640, [27640]))

    patched, report = _patch_section_xml(ET.tostring(root, encoding="utf-8"))

    assert report["status"] == "PASS"
    record = next(item for item in report["tables"] if item["table_id"] == "nested")
    assert record["parent_cell_width"] == 25002
    assert record["parent_cell_content_width"] == 22736
    assert record["parent_cell_margins"] == {"left": 1133, "right": 1133}
    assert record["constraint_kind"] == "immediate_cell_content"
    assert record["new_width"] == 22736
    assert record["direct_cell_widths_after_by_row"] == [[22736]]

    result = ET.fromstring(patched)
    nested = result.find(f"./{_q('p')}/{_q('run')}/{_q('tbl')}/{_q('tr')}/{_q('tc')}/{_q('tbl')}")
    assert nested.find(_q("sz")).attrib["width"] == "22736"


def test_nested_page_wide_three_column_table_scales_every_row_to_page_width():
    root = ET.Element(_q("sec"))
    ET.SubElement(root, _q("pagePr"), {"width": "52000", "height": "80000"})
    margin = root.find(_q("pagePr"))
    ET.SubElement(margin, _q("margin"), {"left": "1041", "right": "1041"})

    paragraph = ET.SubElement(root, _q("p"))
    run = ET.SubElement(paragraph, _q("run"))
    outer = _table("outer", 49918, [24959, 24959])
    run.append(outer)
    owner = outer.find(f"./{_q('tr')}/{_q('tc')}")
    ET.SubElement(owner, _q("cellMargin"), {"left": "1133", "right": "1133"})
    nested = ET.Element(_q("tbl"), {"id": "nested-3x3", "rowCnt": "3", "colCnt": "3"})
    ET.SubElement(nested, _q("sz"), {"width": "60942", "height": "100"})
    for row_index in range(3):
        row = ET.SubElement(nested, _q("tr"))
        for col_index in range(3):
            cell = ET.SubElement(row, _q("tc"))
            ET.SubElement(cell, _q("cellSz"), {"width": "20314", "height": "100"})
    owner.append(nested)

    patched, report = _patch_section_xml(ET.tostring(root, encoding="utf-8"))

    record = next(item for item in report["tables"] if item["table_id"] == "nested-3x3")
    assert record["constraint_kind"] == "page_text_area_nested_overflow"
    assert record["new_width"] == 49918
    assert record["direct_cell_widths_before_by_row"] == [[20314, 20314, 20314]] * 3
    assert record["direct_cell_widths_after_by_row"] == [[16639, 16639, 16640]] * 3
    assert all(sum(row) == 49918 for row in record["direct_cell_widths_after_by_row"])

    result = ET.fromstring(patched)
    nested_after = result.find(f"./{_q('p')}/{_q('run')}/{_q('tbl')}/{_q('tr')}/{_q('tc')}/{_q('tbl')}")
    assert nested_after.find(_q("sz")).attrib["width"] == "49918"
    for row in nested_after.findall(f"./{_q('tr')}"):
        assert [cell.find(_q("cellSz")).attrib["width"] for cell in row.findall(_q("tc"))] == [
            "16639", "16639", "16640"
        ]


class _FakeHwp:
    def __init__(self):
        self.quit_called = False

    def quit(self, *, save=False):
        self.quit_called = True


def test_com_open_requires_a_new_observed_process_and_keeps_secure_factory():
    existing = HwpProcessIdentity(pid=10, create_time=100.0)
    created = HwpProcessIdentity(pid=11, create_time=200.0)
    snapshots = iter(
        [
            HwpProcessSnapshot(status="OK", processes=frozenset({existing})),
            HwpProcessSnapshot(status="OK", processes=frozenset({existing, created})),
        ]
    )
    factory_calls = []
    fake = _FakeHwp()

    def factory(**kwargs):
        factory_calls.append(kwargs)
        return fake

    hwp, tracking = _open_tracked_hwp(snapshot_fn=lambda: next(snapshots), hwp_factory=factory)

    assert hwp is fake
    assert tracking["tracked"] == frozenset({created})
    assert factory_calls == [{"new": True, "visible": False, "on_quit": False}]


def test_com_open_fails_closed_when_no_new_process_is_observed():
    existing = HwpProcessIdentity(pid=10, create_time=100.0)
    snapshots = iter(
        [
            HwpProcessSnapshot(status="OK", processes=frozenset({existing})),
            HwpProcessSnapshot(status="OK", processes=frozenset({existing})),
        ]
    )
    fake = _FakeHwp()

    with pytest.raises(RuntimeError, match="HWP_COM_PROCESS_NOT_OBSERVED"):
        _open_tracked_hwp(snapshot_fn=lambda: next(snapshots), hwp_factory=lambda **_: fake)

    # Ownership was not proven, so the helper never closes a pre-existing
    # session or guesses which HWP process belongs to this call.
    assert fake.quit_called is False


def test_com_quit_requires_tracked_process_exit():
    identity = HwpProcessIdentity(pid=11, create_time=200.0)
    fake = _FakeHwp()
    tracking = {"tracked": frozenset({identity}), "lifecycle": {}}
    snapshots = iter(
        [
            HwpProcessSnapshot(status="OK"),
            HwpProcessSnapshot(status="OK"),
        ]
    )

    result = _quit_tracked_hwp(fake, tracking, snapshot_fn=lambda: next(snapshots), wait_timeout=0)

    assert result.exited
    assert fake.quit_called
    assert tracking["lifecycle"]["wait"]["status"] == "OK"
