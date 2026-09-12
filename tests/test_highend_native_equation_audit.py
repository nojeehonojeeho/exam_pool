from __future__ import annotations

from pathlib import Path
import zipfile

from app.highend_native_equation_audit import audit_highend_math2, audit_hwpx_equations


HP = "http://www.hancom.co.kr/hwpml/2011/paragraph"


def _record(kind: str, **extra: object) -> dict[str, object]:
    return {"type": kind, **extra}


def _piecewise(*expressions: str) -> dict[str, object]:
    return {
        "type": "piecewise_function",
        "name": "f(x)",
        "cases": [{"expression": expression, "condition": "all"} for expression in expressions],
    }


def _manifests() -> tuple[dict, dict, dict]:
    detailed_items = [
        {
            "item_id": "M2-P-001",
            "source_page": 1,
            "column": "left",
            "printed_num": 1,
            "review_status": "VERIFIED",
            "problem_blocks": [_record("equation", script="x"), _piecewise("a", "b")],
            "solution_blocks": [_record("display_equation", script="x=1")],
        },
        {
            "item_id": "M2-P-027",
            "source_page": 27,
            "column": "left",
            "printed_num": 3,
            "review_status": "VERIFIED",
            "problem_blocks": [],
            "solution_blocks": [_piecewise("a", "b", "c")],
        },
    ]
    scoped_items = [
        {
            "item_id": "M2-P-001",
            "source_page": 1,
            "column": "left",
            "column_order": 0,
            "printed_num": 1,
            "problem_typed_equation_count": 1,
            "solution_typed_equation_count": 1,
        },
        {
            "item_id": "M2-P-027",
            "source_page": 27,
            "column": "left",
            "column_order": 0,
            "printed_num": 3,
            "problem_typed_equation_count": 0,
            "solution_typed_equation_count": 0,
        },
    ]
    page_items = [
        {
            "item_id": "M2-P-001",
            "source_pdf_page": 1,
            "source_column": "left",
            "printed_item_number": 1,
        },
        {
            "item_id": "M2-P-027",
            "source_pdf_page": 27,
            "source_column": "right",  # Deliberate evidence mismatch.
            "printed_item_number": 3,
        },
    ]
    return (
        {"status": "CANDIDATE_WITH_EXPLICIT_HUMAN_REVIEW_GATES", "items": page_items},
        {"review_status": "VERIFIED", "items": detailed_items},
        {
            "strict_pass": False,
            "full_book_pass_claimed": False,
            "items": scoped_items,
            "validations": {"source_order": {"mismatches": []}},
        },
    )


def _write_hwpx(path: Path, *, main_counts: list[int], solution_counts: list[int]) -> Path:
    parts = [f'<hs:sec xmlns:hs="urn:synthetic:section" xmlns:hp="{HP}">']
    for index, (main_count, solution_count) in enumerate(zip(main_counts, solution_counts), 1):
        parts.append(
            "<hp:p><hp:run><hp:ctrl>"
            f'<hp:endNote number="{index}"><hp:subList><hp:p>'
        )
        for equation_index in range(solution_count):
            parts.append(f'<hp:run><hp:equation id="s{index}-{equation_index}"/></hp:run>')
        parts.append("</hp:p></hp:subList></hp:endNote></hp:ctrl>")
        for equation_index in range(main_count):
            parts.append(f'<hp:equation id="m{index}-{equation_index}"/>')
        parts.append("</hp:run></hp:p>")
    parts.append("</hs:sec>")
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as package:
        package.writestr("Contents/section0.xml", "".join(parts))
    return path


def test_piecewise_cases_explain_native_count_delta_without_release_pass(tmp_path: Path) -> None:
    page, reviewed, scope = _manifests()
    hwpx = _write_hwpx(tmp_path / "result.hwpx", main_counts=[3, 0], solution_counts=[1, 3])

    report = audit_highend_math2(page, reviewed, scope, hwpx)

    assert report["status"] == "REVIEW_REQUIRED"
    assert report["source_fidelity_release_pass"] is False
    assert report["counts"] == {
        "source_explicit_total": 2,
        "source_piecewise_case_total": 5,
        "source_expanded_expected_total": 7,
        "output_native_equation_total": 7,
        "output_main_equations": 3,
        "output_endnote_equations": 4,
        "output_endnotes": 2,
        "delta_vs_explicit_source": 5,
        "delta_vs_expanded_expected": 0,
    }
    assert report["gates"]["source_explicit_count_matches_output"] is False
    assert report["gates"]["source_piecewise_expanded_count_matches_output"] is True
    assert report["gates"]["problem_per_item_expanded_count_exact"] is True
    assert report["gates"]["solution_per_item_expanded_count_exact"] is True
    assert report["gates"]["item_sequence_exact"] is True
    assert report["gates"]["item_column_exact"] is False
    assert report["alignment"]["m2_p_027"] == {
        "item_id": "M2-P-027",
        "problem_page_source_column": "right",
        "reviewed_column": "left",
        "scope_column": "left",
        "source_pdf_page": 27,
        "printed_item_number": 3,
    }
    assert any(
        finding["code"] == "COUNT_DELTA_EXPLAINED_BY_PIECEWISE_CASES"
        for finding in report["findings"]
    )
    assert any(
        finding["code"] == "ITEM_COLUMN_MISMATCH" and finding["item_id"] == "M2-P-027"
        for finding in report["findings"]
    )


def test_hwpx_equation_reader_is_read_only_and_fail_closed(tmp_path: Path) -> None:
    missing = audit_hwpx_equations(tmp_path / "missing.hwpx")
    assert missing["status"] == "FAIL"
    assert missing["findings"][0]["code"] == "HWPX_NOT_FOUND"

    path = _write_hwpx(tmp_path / "counts.hwpx", main_counts=[1], solution_counts=[2])
    before = path.read_bytes()
    result = audit_hwpx_equations(path)
    after = path.read_bytes()
    assert before == after
    assert result["status"] == "PASS"
    assert result["counts"] == {
        "equations": 3,
        "main_equations": 1,
        "endnote_equations": 2,
        "endnotes": 1,
    }
    assert result["sections"][0]["main_equations_by_endnote"] == [1]
    assert result["sections"][0]["endnote_equations"] == [2]
