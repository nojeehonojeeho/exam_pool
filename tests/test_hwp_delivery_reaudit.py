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


def test_audit_delivery_requires_hwp_pair(tmp_path: Path) -> None:
    folder = tmp_path / "subject"
    folder.mkdir()
    _write_hwpx(folder / "문제.hwpx")
    result = audit_delivery(tmp_path)
    assert result["release_status"] == "NOT_VERIFIED"
    assert any(item["code"] == "HWP_HWPX_PAIR_MISSING" for item in result["subjects"]["subject"]["findings"])
