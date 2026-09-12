from __future__ import annotations

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from tools.patch_hwp_page_geometry import patch_page_margins


def _fixture(path: Path) -> None:
    payload = b'<hs:sec xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section"><hp:secPr xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph"><hp:pagePr width="61370" height="85266"><hp:margin top="5669" bottom="4251" left="5669" right="5669"/></hp:pagePr></hp:secPr></hs:sec>'
    with ZipFile(path, "w", ZIP_DEFLATED) as package:
        package.writestr("Contents/section0.xml", payload)


def test_page_margin_patch_is_fresh_and_explicit(tmp_path: Path) -> None:
    source = tmp_path / "source.hwpx"
    output = tmp_path / "output.hwpx"
    _fixture(source)
    report = patch_page_margins(source, output, bottom=8502)
    assert report["status"] == "PASS"
    assert report["records"][0]["after"]["bottom"] == "8502"
    with ZipFile(source) as package:
        assert b'bottom="4251"' in package.read("Contents/section0.xml")
