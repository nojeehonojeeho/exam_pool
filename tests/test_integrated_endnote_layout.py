"""Regression tests for the document-end integrated-endnote auditor."""

from __future__ import annotations

import zipfile
from pathlib import Path

from tools.audit_integrated_endnote_layout import REQUIRED_SUBJECTS, audit_hwpx, audit_package


HP = "http://www.hancom.co.kr/schema/2011/hpf"
HC = "http://www.hancom.co.kr/schema/2011/hcf"


def _section_xml(
    *,
    notes: list[str] | None = None,
    endnote_placement: str | None = "END_OF_DOCUMENT",
    include_footnote_each_column: bool = False,
) -> str:
    notes = notes or []
    parts = [f'<hs:sec xmlns:hs="urn:synthetic:section" xmlns:hp="{HP}" xmlns:hc="{HC}">']
    if endnote_placement is not None or include_footnote_each_column:
        parts.append("<hp:secPr>")
        if include_footnote_each_column:
            parts.append('<hp:footNotePr><hp:placement place="EACH_COLUMN"/></hp:footNotePr>')
        if endnote_placement is not None:
            parts.append(
                "<hp:endNotePr>"
                f'<hp:placement place="{endnote_placement}"/>'
                "</hp:endNotePr>"
            )
        parts.append("</hp:secPr>")
    for number, text in enumerate(notes, 1):
        parts.append(
            '<hp:p><hp:run><hp:t>문제 본문</hp:t><hp:ctrl>'
            f'<hp:endNote number="{number}"><hp:subList><hp:p><hp:run>'
            f"<hp:t>{text}</hp:t>"
            "</hp:run></hp:p></hp:subList></hp:endNote>"
            "</hp:ctrl>"
            f'<hp:t>{number}번</hp:t></hp:run></hp:p>'
            f'<hp:autoNum numType="ENDNOTE" num="{number}"/>'
        )
    parts.append("</hs:sec>")
    return "".join(parts)


def _write_hwpx(path: Path, sections: dict[str, str]) -> Path:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as package:
        for name, xml in sections.items():
            package.writestr(f"Contents/{name}", xml)
    return path


def _package_with_subjects(root: Path, subjects: list[str]) -> Path:
    for subject in subjects:
        directory = root / subject
        directory.mkdir(parents=True, exist_ok=True)
        _write_hwpx(
            directory / f"{subject}_미주작업_완료.hwpx",
            {"section0.xml": _section_xml(notes=["정답 풀이 완료"])},
        )
        (directory / f"{subject}_미주작업_완료.hwp").write_bytes(b"synthetic hwp")
    return root


def test_missing_hwpx_path_returns_structured_fail(tmp_path: Path) -> None:
    report = audit_hwpx(tmp_path / "does-not-exist.hwpx")
    assert report["status"] == "FAIL"
    assert report["findings"][0]["code"] == "INVALID_HWPX"


def test_invalid_placement_in_section_without_notes_is_not_ignored(tmp_path: Path) -> None:
    path = _write_hwpx(
        tmp_path / "mixed.hwpx",
        {
            "section0.xml": _section_xml(notes=["정답 풀이 완료"]),
            "section1.xml": _section_xml(notes=[], endnote_placement="EACH_COLUMN"),
        },
    )
    report = audit_hwpx(path)
    assert report["status"] == "FAIL"
    assert any(f["code"] == "ENDNOTE_PLACEMENT_INVALID" for f in report["findings"])


def test_empty_endnote_body_is_not_a_structural_pass(tmp_path: Path) -> None:
    path = _write_hwpx(tmp_path / "empty.hwpx", {"section0.xml": _section_xml(notes=["   "])})
    report = audit_hwpx(path)
    assert report["status"] == "FAIL"
    assert any(f["code"] == "ENDNOTE_BODY_EMPTY" for f in report["findings"])


def test_footnote_each_column_does_not_change_endnote_contract(tmp_path: Path) -> None:
    path = _write_hwpx(
        tmp_path / "footnote.hwpx",
        {
            "section0.xml": _section_xml(
                notes=["정답 풀이 완료"], include_footnote_each_column=True
            )
        },
    )
    report = audit_hwpx(path)
    assert report["status"] == "PASS"
    assert report["findings"] == []


def test_package_requires_all_four_highend_subjects(tmp_path: Path) -> None:
    root = _package_with_subjects(tmp_path / "package", [REQUIRED_SUBJECTS[0]])
    report = audit_package(root)
    assert report["status"] == "FAIL"
    missing = {f["subject"] for f in report["findings"] if f["code"] == "MISSING_REQUIRED_SUBJECT"}
    assert missing == set(REQUIRED_SUBJECTS[1:])


def test_full_four_subject_package_passes_structural_gate(tmp_path: Path) -> None:
    root = _package_with_subjects(tmp_path / "package", list(REQUIRED_SUBJECTS))
    report = audit_package(root)
    assert report["status"] == "PASS"
    assert report["subject_count"] == 4
    assert report["findings"] == []
