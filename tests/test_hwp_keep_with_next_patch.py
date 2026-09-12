from pathlib import Path
from zipfile import ZipFile

import pytest

from tools.patch_hwp_keep_with_next import patch_keep_with_next


HEADER = """<?xml version='1.0' encoding='UTF-8'?>
<hh:head xmlns:hh='http://www.hancom.co.kr/hwpml/2011/head'>
  <hh:paraProperties itemCnt='1'>
    <hh:paraPr id='0'><hh:breakSetting keepWithNext='0' keepLines='1'/></hh:paraPr>
  </hh:paraProperties>
</hh:head>
"""
SECTION = """<?xml version='1.0' encoding='UTF-8'?>
<hs:sec xmlns:hs='http://www.hancom.co.kr/hwpml/2011/section' xmlns:hp='http://www.hancom.co.kr/hwpml/2011/paragraph'>
  <hp:p paraPrIDRef='0'><hp:run><hp:t>머리</hp:t></hp:run></hp:p>
  <hp:p paraPrIDRef='0'><hp:run><hp:t>문항 anchor</hp:t></hp:run></hp:p>
  <hp:p paraPrIDRef='0'><hp:run><hp:t>조건</hp:t></hp:run></hp:p>
</hs:sec>
"""


def _write_package(path: Path) -> None:
    with ZipFile(path, "w") as archive:
        archive.writestr("Contents/header.xml", HEADER)
        archive.writestr("Contents/section0.xml", SECTION)


def test_keep_with_next_clones_styles_for_requested_span(tmp_path: Path) -> None:
    source = tmp_path / "source.hwpx"
    target = tmp_path / "target.hwpx"
    _write_package(source)

    report = patch_keep_with_next(source, target, anchor="문항 anchor", span=2)

    assert report["status"] == "PASS"
    assert len(report["records"]) == 2
    with ZipFile(target) as archive:
        header = archive.read("Contents/header.xml").decode("utf-8")
        section = archive.read("Contents/section0.xml").decode("utf-8")
    assert header.count("keepWithNext=\"1\"") == 2
    assert section.count("paraPrIDRef=\"") == 3


def test_missing_anchor_fails_closed(tmp_path: Path) -> None:
    source = tmp_path / "source.hwpx"
    target = tmp_path / "target.hwpx"
    _write_package(source)
    with pytest.raises(ValueError, match="anchor occurrence not found"):
        patch_keep_with_next(source, target, anchor="없음")
    assert not target.exists()


def test_input_is_unchanged(tmp_path: Path) -> None:
    source = tmp_path / "source.hwpx"
    target = tmp_path / "target.hwpx"
    _write_package(source)
    before = source.read_bytes()
    patch_keep_with_next(source, target, anchor="머리", span=1)
    assert source.read_bytes() == before
