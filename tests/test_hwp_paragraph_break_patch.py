from pathlib import Path
from zipfile import ZipFile

import pytest

from tools.patch_hwp_paragraph_break import patch_paragraph_break


SECTION = """<?xml version='1.0' encoding='UTF-8'?>
<hs:sec xmlns:hs='http://www.hancom.co.kr/hwpml/2011/section' xmlns:hp='http://www.hancom.co.kr/hwpml/2011/paragraph'>
  <hp:p id='0' pageBreak='0' columnBreak='0'><hp:run><hp:t>앞 문단</hp:t></hp:run></hp:p>
  <hp:p id='1' pageBreak='0' columnBreak='0'><hp:run><hp:t>최고차항의 계수가 모두 1인 삼차식</hp:t></hp:run></hp:p>
</hs:sec>
"""


def _write_package(path: Path) -> None:
    with ZipFile(path, "w") as archive:
        archive.writestr("Contents/section0.xml", SECTION)
        archive.writestr("BinData/dummy.bin", b"keep")


def test_patch_matching_paragraph_sets_page_break(tmp_path: Path) -> None:
    source = tmp_path / "source.hwpx"
    target = tmp_path / "target.hwpx"
    _write_package(source)

    report = patch_paragraph_break(
        source,
        target,
        anchor="최고차항의 계수가 모두 1인 삼차식",
    )

    assert report["status"] == "PASS"
    assert report["match_count"] == 1
    with ZipFile(target) as archive:
        payload = archive.read("Contents/section0.xml").decode("utf-8")
    assert "id=\"1\" pageBreak=\"1\"" in payload or "pageBreak='1'" in payload


def test_missing_anchor_fails_closed(tmp_path: Path) -> None:
    source = tmp_path / "source.hwpx"
    target = tmp_path / "target.hwpx"
    _write_package(source)
    with pytest.raises(ValueError, match="anchor occurrence not found"):
        patch_paragraph_break(source, target, anchor="not present")
    assert not target.exists()


def test_input_is_not_overwritten(tmp_path: Path) -> None:
    source = tmp_path / "source.hwpx"
    target = tmp_path / "target.hwpx"
    _write_package(source)
    before = source.read_bytes()
    patch_paragraph_break(source, target, anchor="앞 문단")
    assert source.read_bytes() == before
