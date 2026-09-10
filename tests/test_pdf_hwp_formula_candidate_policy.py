from app.pdf_hwp_formula_candidate_policy import demote_standalone_numeric_equations


def test_bare_numeric_ocr_equation_is_demoted_to_text() -> None:
    value = {"type": "equation", "source_text_exact": "6", "script": "6"}
    assert demote_standalone_numeric_equations(value) == {"type": "text", "text": "6"}


def test_structured_formula_candidate_is_preserved() -> None:
    value = {
        "type": "equation",
        "source_text_exact": "28+8=36",
        "script": "28+8=36",
    }
    assert demote_standalone_numeric_equations(value) == value


def test_nested_table_scalars_are_demoted_without_mutating_input() -> None:
    value = {"rows": [[{"type": "equation", "source_text_exact": "320"}], ["ordinary"]]}
    result = demote_standalone_numeric_equations(value)
    assert result["rows"][0][0] == {"type": "text", "text": "320"}
    assert value["rows"][0][0]["type"] == "equation"
