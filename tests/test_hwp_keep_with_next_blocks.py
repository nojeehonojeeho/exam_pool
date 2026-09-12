from pathlib import Path
from zipfile import ZipFile

from tools.patch_hwp_keep_with_next_blocks import patch_blocks


HEADER = """<?xml version='1.0' encoding='UTF-8'?>
<hh:head xmlns:hh='http://www.hancom.co.kr/hwpml/2011/head'>
  <hh:paraProperties itemCnt='2'>
    <hh:paraPr id='0'><hh:breakSetting keepWithNext='0'/></hh:paraPr>
    <hh:paraPr id='29'><hh:breakSetting keepWithNext='0'/></hh:paraPr>
  </hh:paraProperties>
</hh:head>
"""
SECTION = """<?xml version='1.0' encoding='UTF-8'?>
<hs:sec xmlns:hs='http://www.hancom.co.kr/hwpml/2011/section' xmlns:hp='http://www.hancom.co.kr/hwpml/2011/paragraph'>
  <hp:subList>
    <hp:p paraPrIDRef='29'><hp:run><hp:t>문항 1</hp:t></hp:run></hp:p>
    <hp:p paraPrIDRef='0'><hp:run><hp:t>조건</hp:t></hp:run></hp:p>
    <hp:p paraPrIDRef='0'><hp:run><hp:t>보기</hp:t></hp:run></hp:p>
    <hp:p paraPrIDRef='29'><hp:run><hp:t>문항 2</hp:t></hp:run></hp:p>
    <hp:p paraPrIDRef='0'><hp:run><hp:t>조건 2</hp:t></hp:run></hp:p>
  </hp:subList>
</hs:sec>
"""


def _write_package(path: Path) -> None:
    with ZipFile(path, "w") as archive:
        archive.writestr("Contents/header.xml", HEADER)
        archive.writestr("Contents/section0.xml", SECTION)


def test_all_heading_blocks_are_patched_without_id_reuse(tmp_path: Path) -> None:
    source = tmp_path / "source.hwpx"
    target = tmp_path / "target.hwpx"
    _write_package(source)

    report = patch_blocks(source, target)

    assert report["status"] == "PASS"
    assert report["question_block_count"] == 2
    assert report["patched_paragraph_count"] == 3
    with ZipFile(target) as archive:
        header = archive.read("Contents/header.xml").decode("utf-8")
        section = archive.read("Contents/section0.xml").decode("utf-8")
    assert header.count("keepWithNext=\"1\"") == 3
    ids = [part.split("paraPrIDRef=\"")[1].split("\"")[0] for part in section.split("<hp:p ")[1:]]
    generated_ids = [ident for ident in ids if ident != "0"]
    assert len(set(generated_ids)) == len(generated_ids)


def test_source_is_unchanged_and_target_is_fresh(tmp_path: Path) -> None:
    source = tmp_path / "source.hwpx"
    target = tmp_path / "target.hwpx"
    _write_package(source)
    before = source.read_bytes()
    patch_blocks(source, target)
    assert source.read_bytes() == before
