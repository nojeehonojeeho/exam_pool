from __future__ import annotations

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from app.hwp_delivery_reaudit import audit_hwpx
from tools.repair_hwpx_native_formula_fallback import DEFAULT_TEXT, repair_hwpx


def _write_fixture(path: Path) -> None:
    section = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>'
        '<hp:sec xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph">'
        '<hp:p><hp:run charPrIDRef="6">'
        f"<hp:t>{DEFAULT_TEXT}</hp:t>"
        '<hp:equation id="11" zOrder="7" font="HYhwpEQ" baseUnit="1100">'
        '<hp:sz width="12000" height="1350"/><hp:script>x=1</hp:script>'
        '</hp:equation>'
        '<hp:t>다음 문장</hp:t>'
        '</hp:run></hp:p></hp:sec>'
    ).encode("utf-8")
    with ZipFile(path, "w", ZIP_DEFLATED) as package:
        package.writestr("Contents/section0.xml", section)


def test_repair_converts_exact_visible_span_to_native_equation(tmp_path: Path) -> None:
    source = tmp_path / "source.hwpx"
    output = tmp_path / "patched.hwpx"
    _write_fixture(source)
    result = repair_hwpx(source, output)
    assert result["status"] == "PASS"
    assert result["replacements"][0]["formula_script"] == "E(X)=E(bar{X})=18"
    audit = audit_hwpx(output)
    assert audit["structural_status"] == "PASS"
    assert audit["raw_backslash_text"] == []
    assert audit["equations"] == 2
    with ZipFile(output) as package:
        xml = package.read("Contents/section0.xml").decode("utf-8")
    assert "정답 ④" in xml and "이므로" in xml
    assert "E(X)=E(\\bar{X})=18" not in xml
    assert "<hp:script>E(X)=E(bar{X})=18</hp:script>" in xml


def test_repair_refuses_ambiguous_target(tmp_path: Path) -> None:
    source = tmp_path / "source.hwpx"
    output = tmp_path / "patched.hwpx"
    _write_fixture(source)
    with ZipFile(source, "a", ZIP_DEFLATED) as package:
        package.writestr(
            "Contents/section1.xml",
            '<hp:sec xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph">'
            f"<hp:p><hp:run><hp:t>{DEFAULT_TEXT}</hp:t></hp:run></hp:p></hp:sec>",
        )
    try:
        repair_hwpx(source, output)
    except ValueError as exc:
        assert "expected exactly one target span" in str(exc)
    else:  # pragma: no cover - defensive
        raise AssertionError("ambiguous source span must fail closed")
