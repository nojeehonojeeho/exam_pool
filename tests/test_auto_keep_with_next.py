from __future__ import annotations

import hashlib
import xml.etree.ElementTree as ET
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from tools.auto_keep_with_next import _paragraph_text, patch_keep_with_next_blocks


HEAD = "http://www.hancom.co.kr/hwpml/2011/head"
HP = "http://www.hancom.co.kr/hwpml/2011/paragraph"
HS = "http://www.hancom.co.kr/hwpml/2011/section"


HEADER = f'''<?xml version="1.0" encoding="UTF-8"?>
<hh:head xmlns:hh="{HEAD}">
  <hh:paraProperties itemCnt="1">
    <hh:paraPr id="0"><hh:breakSetting keepWithNext="0" keepLines="1"/></hh:paraPr>
  </hh:paraProperties>
</hh:head>
'''


SECTION = f'''<?xml version="1.0" encoding="UTF-8"?>
<hs:sec xmlns:hs="{HS}" xmlns:hp="{HP}">
  <hp:p paraPrIDRef="0"><hp:run><hp:t>before</hp:t></hp:run></hp:p>
  <hp:p paraPrIDRef="0"><hp:run><hp:t>Q1</hp:t></hp:run></hp:p>
  <hp:p paraPrIDRef="0"><hp:run><hp:t>first body</hp:t></hp:run></hp:p>
  <hp:p paraPrIDRef="0"><hp:run><hp:tbl><hp:tr><hp:tc><hp:subList>
    <hp:p paraPrIDRef="0"><hp:run><hp:t>nested one</hp:t></hp:run></hp:p>
    <hp:p paraPrIDRef="0"><hp:run><hp:t>nested last</hp:t></hp:run></hp:p>
  </hp:subList></hp:tc></hp:tr></hp:tbl></hp:run></hp:p>
  <hp:p paraPrIDRef="0"><hp:run><hp:t>Q2 direct</hp:t></hp:run></hp:p>
  <hp:p paraPrIDRef="0"><hp:run><hp:t>second last</hp:t></hp:run></hp:p>
  <hp:p paraPrIDRef="0"><hp:run><hp:t>01 01 해설정답 ② solution must be outside Q2</hp:t></hp:run></hp:p>
  <hp:p paraPrIDRef="0"><hp:run><hp:t>after solution</hp:t></hp:run></hp:p>
</hs:sec>
'''


def _write_package(path: Path, section: str = SECTION, header: str = HEADER) -> None:
    with ZipFile(path, "w", ZIP_DEFLATED) as archive:
        archive.writestr("Contents/header.xml", header)
        archive.writestr("Contents/section0.xml", section)
        archive.writestr("BinData/preserve.bin", b"unchanged")


def _read(path: Path, member: str) -> bytes:
    with ZipFile(path) as archive:
        return archive.read(member)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _text(node: ET.Element) -> str:
    return "".join(part.text or "" for part in node.iter() if _local(part.tag) == "t")


def test_auto_blocks_include_nested_paragraphs_and_exclude_each_last(tmp_path: Path) -> None:
    source = tmp_path / "source.hwpx"
    output = tmp_path / "auto.hwpx"
    _write_package(source)

    report = patch_keep_with_next_blocks(
        source,
        output,
        heading_texts=("Q2 direct",),
    )

    assert report["status"] == "PASS"
    assert report["block_count"] == 2
    assert report["patched_paragraph_count"] == 5
    assert report["style_count_before"] == 1
    assert report["style_count_after"] == 6
    assert report["item_counts_before"] == ["1"]
    assert report["item_counts_after"] == ["6"]
    with ZipFile(output) as archive:
        header = ET.fromstring(archive.read("Contents/header.xml"))
        section = ET.fromstring(archive.read("Contents/section0.xml"))

    styles = {
        node.get("id"): node
        for node in header.iter()
        if _local(node.tag) == "paraPr"
    }
    paragraphs = [node for node in section.iter() if _local(node.tag) == "p"]
    kept = {
        _paragraph_text(node): styles[node.get("paraPrIDRef")]
        for node in paragraphs
        if node.get("paraPrIDRef") not in {"0", None}
    }
    assert set(kept) == {"", "Q1", "first body", "nested one", "Q2 direct"}
    assert all(
        next(child for child in style.iter() if _local(child.tag) == "breakSetting").get("keepWithNext") == "1"
        for style in kept.values()
    )
    # The final nested paragraph of Q1 and the final paragraph before the
    # solution boundary remain on the original style and are not chained.
    refs = { _text(node): node.get("paraPrIDRef") for node in paragraphs }
    assert refs["nested last"] == "0"
    assert refs["01 01 해설정답 ② solution must be outside Q2"] == "0"
    assert refs["second last"] == "0"
    assert refs["after solution"] == "0"


def test_style29_and_solution_boundary_do_not_cross_blocks(tmp_path: Path) -> None:
    source = tmp_path / "source.hwpx"
    output = tmp_path / "auto.hwpx"
    header = HEADER.replace('itemCnt="1"', 'itemCnt="2"').replace(
        '</hh:paraPr>\n  </hh:paraProperties>',
        '</hh:paraPr>\n    <hh:paraPr id="29"><hh:breakSetting keepWithNext="0"/></hh:paraPr>\n  </hh:paraProperties>',
    )
    section = SECTION.replace('paraPrIDRef="0"><hp:run><hp:t>Q1</hp:t>', 'paraPrIDRef="29"><hp:run><hp:t>Q1</hp:t>')
    _write_package(source, section=section, header=header)

    report = patch_keep_with_next_blocks(source, output, heading_texts=("Q2 direct",))

    assert report["block_count"] == 2
    with ZipFile(output) as archive:
        root = ET.fromstring(archive.read("Contents/section0.xml"))
        header_root = ET.fromstring(archive.read("Contents/header.xml"))
    paragraphs = [node for node in root.iter() if _local(node.tag) == "p"]
    by_text = {_text(node): node for node in paragraphs}
    assert by_text["Q1"].get("paraPrIDRef") != "29"
    assert by_text["nested last"].get("paraPrIDRef") == "0"
    assert by_text["01 01 해설정답 ② solution must be outside Q2"].get("paraPrIDRef") == "0"
    properties = next(node for node in header_root.iter() if _local(node.tag) == "paraProperties")
    assert properties.get("itemCnt") == str(len([node for node in properties if _local(node.tag) == "paraPr"]))


def test_native_endnote_anchor_style_is_a_solution_boundary(tmp_path: Path) -> None:
    source = tmp_path / "source.hwpx"
    output = tmp_path / "auto.hwpx"
    # Native integrated files use an anchor paragraph with only an automatic
    # number.  The solution body is carried by hp:endNote, so its heading is
    # not available as direct paragraph text.
    section = SECTION.replace(
        '<hp:t>01 01 해설정답 ② solution must be outside Q2</hp:t>',
        '<hp:t>01</hp:t><hp:endNote><hp:p paraPrIDRef="0"><hp:run><hp:t>해설정답 본문</hp:t></hp:run></hp:p></hp:endNote>',
    ).replace(
        '<hp:p paraPrIDRef="0"><hp:run><hp:t>01</hp:t>',
        '<hp:p paraPrIDRef="34"><hp:run><hp:t>01</hp:t>',
    )
    _write_package(source, section=section)

    report = patch_keep_with_next_blocks(source, output, heading_texts=("Q2 direct",))

    assert report["block_count"] == 2
    assert report["boundary_para_pr_ids"] == ["20", "34"]
    assert report["blocks"][1]["boundary_kind"] == "solution_heading"
    assert report["blocks"][1]["boundary_text"] == "01"
    with ZipFile(output) as archive:
        root = ET.fromstring(archive.read("Contents/section0.xml"))
    paragraphs = [node for node in root.iter() if _local(node.tag) == "p"]
    by_text = {_text(node): node for node in paragraphs}
    assert by_text["Q2 direct"].get("paraPrIDRef") != "0"
    assert by_text["second last"].get("paraPrIDRef") == "0"
    assert by_text["after solution"].get("paraPrIDRef") == "0"


def test_source_is_unchanged_and_existing_output_is_not_overwritten(tmp_path: Path) -> None:
    source = tmp_path / "source.hwpx"
    output = tmp_path / "auto.hwpx"
    _write_package(source)
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    _write_package(output, section=SECTION.replace("before", "sentinel"))
    with pytest.raises(FileExistsError):
        patch_keep_with_next_blocks(source, output, heading_texts=("Q2 direct",))
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before
    assert b"sentinel" in _read(output, "Contents/section0.xml")


def test_missing_heading_fails_closed_without_creating_output(tmp_path: Path) -> None:
    source = tmp_path / "source.hwpx"
    output = tmp_path / "auto.hwpx"
    _write_package(source, section=SECTION.replace("Q1", "ordinary" ).replace("Q2 direct", "ordinary 2"))
    with pytest.raises(ValueError, match="no question headings"):
        patch_keep_with_next_blocks(source, output, heading_texts=("not present",))
    assert not output.exists()


def test_unknown_paragraph_style_fails_before_output_creation(tmp_path: Path) -> None:
    source = tmp_path / "source.hwpx"
    output = tmp_path / "auto.hwpx"
    _write_package(source, section=SECTION.replace('paraPrIDRef="0"><hp:run><hp:t>Q1', 'paraPrIDRef="404"><hp:run><hp:t>Q1'))
    with pytest.raises(ValueError, match="unknown paraPrIDRef"):
        patch_keep_with_next_blocks(source, output, heading_texts=("Q2 direct",))
    assert not output.exists()


def test_formula_q_subscript_is_not_mistaken_for_a_direct_heading(tmp_path: Path) -> None:
    source = tmp_path / "source.hwpx"
    output = tmp_path / "auto.hwpx"
    section = SECTION.replace("Q1", "Q_1(x)=2x^5").replace("Q2 direct", "ordinary 2")
    _write_package(source, section=section)
    with pytest.raises(ValueError, match="no question headings"):
        patch_keep_with_next_blocks(source, output)
    assert not output.exists()
