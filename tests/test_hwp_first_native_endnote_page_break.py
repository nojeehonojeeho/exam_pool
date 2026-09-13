"""Regression coverage for the physical new-page boundary before endnotes."""

from __future__ import annotations

from pathlib import Path
from zipfile import ZipFile

import fitz
import pytest

from tools.audit_hwp_endnote_page_boundary import audit_endnote_page_boundary
from tools.patch_hwp_first_native_endnote_page_break import patch_first_native_endnote_page_break


SECTION = """<?xml version='1.0' encoding='UTF-8'?>
<hs:sec xmlns:hs='http://www.hancom.co.kr/hwpml/2011/section' xmlns:hp='http://www.hancom.co.kr/hwpml/2011/paragraph'>
  <hp:secPr><hp:endNotePr><hp:placement place='END_OF_DOCUMENT'/></hp:endNotePr></hp:secPr>
  <hp:p id='0'><hp:run><hp:t>problem body</hp:t></hp:run><hp:ctrl><hp:endNote number='1'><hp:subList><hp:p id='1' pageBreak='0'><hp:run><hp:t>NOTE_ONE</hp:t></hp:run></hp:p></hp:subList></hp:endNote></hp:ctrl></hp:p>
  <hp:p id='2'><hp:run><hp:t>another problem</hp:t></hp:run><hp:ctrl><hp:endNote number='2'><hp:subList><hp:p id='3' pageBreak='0'><hp:run><hp:t>NOTE_TWO</hp:t></hp:run></hp:p></hp:subList></hp:endNote></hp:ctrl></hp:p>
  <hp:p id='4' pageBreak='0' columnBreak='0'><hp:run/><hp:linesegarray><hp:lineseg/></hp:linesegarray></hp:p>
</hs:sec>
"""


def _write_hwpx(path: Path) -> None:
    with ZipFile(path, "w") as archive:
        archive.writestr("Contents/section0.xml", SECTION)


def _write_pdf(path: Path, pages: list[tuple[str, float]]) -> None:
    document = fitz.open()
    for text, y in pages:
        page = document.new_page()
        page.insert_text((72, y), text)
    document.save(path)
    document.close()


def test_first_native_endnote_patch_changes_only_terminal_main_story_paragraph(tmp_path: Path) -> None:
    source = tmp_path / "source.hwpx"
    target = tmp_path / "target.hwpx"
    _write_hwpx(source)

    report = patch_first_native_endnote_page_break(source, target)

    assert report["status"] == "PASS"
    assert report["page_break_before"] == "0"
    assert report["page_break_after"] == "1"
    assert source.read_bytes() != target.read_bytes()
    with ZipFile(target) as archive:
        xml = archive.read("Contents/section0.xml").decode("utf-8")
    assert "id=\"1\" pageBreak=\"0\"" in xml
    assert "id=\"3\" pageBreak=\"0\"" in xml
    assert "id=\"4\" pageBreak=\"1\"" in xml


def test_patch_fails_closed_when_endnote_placement_is_not_document_end(tmp_path: Path) -> None:
    source = tmp_path / "source.hwpx"
    target = tmp_path / "target.hwpx"
    _write_hwpx(source)
    with ZipFile(source, "a") as archive:
        archive.writestr("Contents/section1.xml", SECTION.replace("END_OF_DOCUMENT", "EACH_PAGE"))

    with pytest.raises(ValueError, match="END_OF_DOCUMENT"):
        patch_first_native_endnote_page_break(source, target)
    assert not target.exists()


def test_rendered_boundary_requires_a_fresh_page_after_problem_pages(tmp_path: Path) -> None:
    hwpx = tmp_path / "integrated.hwpx"
    problem_pdf = tmp_path / "problem.pdf"
    good_pdf = tmp_path / "good.pdf"
    bad_pdf = tmp_path / "bad.pdf"
    _write_hwpx(hwpx)
    _write_pdf(problem_pdf, [("problem text", 72)])
    _write_pdf(good_pdf, [("problem text", 72), ("NOTE_ONE\nanswer text", 72)])
    _write_pdf(bad_pdf, [("problem text\nNOTE_ONE\nanswer text", 650)])

    assert audit_endnote_page_boundary(problem_pdf, good_pdf, hwpx)["status"] == "PASS"
    failed = audit_endnote_page_boundary(problem_pdf, bad_pdf, hwpx)
    assert failed["status"] == "FAIL"
    assert any(finding["code"] == "ENDNOTE_PAGE_BOUNDARY_NOT_FRESH_PAGE" for finding in failed["findings"])
