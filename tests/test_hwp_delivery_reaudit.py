from __future__ import annotations

from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

from app.hwp_delivery_reaudit import audit_delivery, audit_hwpx


def _write_hwpx(path: Path, script: str = "x over y") -> None:
    section = (
        '<hp:sec xmlns:hp="urn:test">'
        '<hp:p><hp:run><hp:t>문항 본문</hp:t>'
        f'<hp:equation font="HYhwpEQ" baseUnit="1100"><hp:script>{script}</hp:script></hp:equation>'
        '</hp:run></hp:p></hp:sec>'
    ).encode("utf-8")
    with ZipFile(path, "w", ZIP_DEFLATED) as package:
        package.writestr("Contents/section0.xml", section)


def test_audit_hwpx_passes_native_profile(tmp_path: Path) -> None:
    path = tmp_path / "문제.hwpx"
    _write_hwpx(path)
    result = audit_hwpx(path)
    assert result["zip_test"] is None
    assert result["equations"] == 1
    assert result["structural_status"] == "PASS"
    assert result["source_fidelity_checked"] is False


def test_audit_hwpx_rejects_raw_backslash(tmp_path: Path) -> None:
    path = tmp_path / "문제.hwpx"
    _write_hwpx(path, r"\sum")
    result = audit_hwpx(path)
    assert result["structural_status"] == "FAIL"
    assert any(item["code"] == "FORMULA_RAW_BACKSLASH" for item in result["findings"])


def test_audit_hwpx_rejects_raw_backslash_in_visible_text(tmp_path: Path) -> None:
    path = tmp_path / "문제.hwpx"
    section = (
        '<hp:sec xmlns:hp="urn:test">'
        '<hp:p><hp:run><hp:t>정답 E(X)=E(\\bar{X})=18</hp:t>'
        '<hp:equation font="HYhwpEQ" baseUnit="1100"><hp:script>x</hp:script></hp:equation>'
        '</hp:run></hp:p></hp:sec>'
    ).encode("utf-8")
    with ZipFile(path, "w", ZIP_DEFLATED) as package:
        package.writestr("Contents/section0.xml", section)
    result = audit_hwpx(path)
    assert result["structural_status"] == "FAIL"
    assert result["raw_backslash_text"][0]["paragraph_index"] == 1
    assert any(item["code"] == "FORMULA_RAW_BACKSLASH_TEXT" for item in result["findings"])


def test_audit_hwpx_does_not_duplicate_nested_table_text(tmp_path: Path) -> None:
    path = tmp_path / "nested.hwpx"
    section = (
        '<hp:sec xmlns:hp="urn:test">'
        '<hp:p><hp:run><hp:t>바깥 문단</hp:t></hp:run>'
        '<hp:tbl><hp:tr><hp:tc><hp:p><hp:run><hp:t>정답 \\sum</hp:t></hp:run></hp:p></hp:tc></hp:tr></hp:tbl>'
        '</hp:p></hp:sec>'
    ).encode("utf-8")
    with ZipFile(path, "w", ZIP_DEFLATED) as package:
        package.writestr("Contents/section0.xml", section)
    result = audit_hwpx(path)
    assert result["structural_status"] == "FAIL"
    assert len(result["raw_backslash_text"]) == 1
    assert result["raw_backslash_text"][0]["text"] == r"정답 \sum"


def test_audit_hwpx_rejects_internal_diagnostic_text_leak(tmp_path: Path) -> None:
    path = tmp_path / "diagnostic.hwpx"
    section = (
        '<hp:sec xmlns:hp="urn:test">'
        '<hp:p><hp:run><hp:t>문항과 무관한 스캔 잔여점으로 semantic 내용 없음.</hp:t>'
        '<hp:equation font="HYhwpEQ" baseUnit="1100"><hp:script>x</hp:script></hp:equation>'
        '</hp:run></hp:p></hp:sec>'
    ).encode("utf-8")
    with ZipFile(path, "w", ZIP_DEFLATED) as package:
        package.writestr("Contents/section0.xml", section)
    result = audit_hwpx(path)
    assert result["structural_status"] == "FAIL"
    assert result["internal_diagnostic_text"] == ["문항과 무관한 스캔 잔여점으로 semantic 내용 없음."]
    assert any(item["code"] == "INTERNAL_DIAGNOSTIC_TEXT_LEAK" for item in result["findings"])


def test_audit_delivery_requires_hwp_pair(tmp_path: Path) -> None:
    folder = tmp_path / "subject"
    folder.mkdir()
    _write_hwpx(folder / "문제.hwpx")
    result = audit_delivery(tmp_path)
    assert result["release_status"] == "NOT_VERIFIED"
    assert any(item["code"] == "HWP_HWPX_PAIR_MISSING" for item in result["subjects"]["subject"]["findings"])
