from copy import deepcopy
import hashlib

from app.hwp_authoring_preflight import audit_authoring_items


def item():
    return {"item_id": "SYN-1", "review_status": "VERIFIED", "uncertainties": [],
            "problem_blocks": [{"type": "equation", "script": "x^2+1", "script_language": "latex"}],
            "solution_blocks": [{"type": "text", "text": "Synthetic explanation."}],
            "solution_completeness": {"source_block_count": 1, "included_block_count": 1}}


def codes(value, tmp_path):
    return {row["code"] for row in audit_authoring_items([value], asset_root=tmp_path)["findings"]}


def test_input_check_does_not_claim_source_fidelity(tmp_path):
    result = audit_authoring_items([item()], asset_root=tmp_path)
    assert result["status"] == "PASS"
    assert result["equations"][0]["script"] == "x^{2} + 1"
    assert result["source_fidelity_proven"] is False


def test_verified_label_does_not_bypass_unknown_command(tmp_path):
    value = item()
    value["problem_blocks"][0]["script"] = r"\unsupported{x}"
    assert "UNSUPPORTED_COMMAND" in codes(value, tmp_path)


def test_python_escape_control_character_in_formula_source_fails_closed(tmp_path):
    value = item()
    # This emulates a non-raw Python literal "\\alpha", where \\a became BEL.
    value["problem_blocks"][0]["script"] = "\x07lpha+x"
    assert "FORMULA_CONTROL_CHARACTER" in codes(value, tmp_path)


def test_split_latex_operator_is_not_accepted_as_atoms(tmp_path):
    value = item()
    value["problem_blocks"][0]["script"] = "8 s q r t ( 3 ) + p i"
    assert "FORMULA_OPERATOR_TOKENIZATION" in codes(value, tmp_path)
    value["problem_blocks"][0]["script"] = r"8\sqrt{3}+\pi"
    assert "FORMULA_OPERATOR_TOKENIZATION" not in codes(value, tmp_path)


def test_missing_dialect_or_math_in_native_text_fails(tmp_path):
    value = item()
    value["problem_blocks"][0].pop("script_language")
    value["solution_blocks"][0]["text"] = r"x^{2}=4"
    assert {"DIALECT_REQUIRED", "FORMULA_MARKUP_IN_TEXT"} <= codes(value, tmp_path)


def test_nested_description_table_cannot_replace_original_graph(tmp_path):
    value = item()
    value["problem_blocks"].append({"type": "condition_box", "rows": [[{"type": "figure_reference", "description": "Curve with two intersections."}]]})
    assert "FIGURE_DESCRIPTION_REPLACEMENT" in codes(value, tmp_path)
    for kind in ("diagram", "figure_axis_labels", "figure_bundle"):
        check = deepcopy(value)
        check["problem_blocks"] = [{"type": kind, "description": "Diagram"}]
        assert "FIGURE_DESCRIPTION_REPLACEMENT" in codes(check, tmp_path)


def test_missing_figure_never_falls_back_to_description(tmp_path):
    value = item()
    value["problem_blocks"].append({"type": "figure", "path": "missing.png", "allowed": True, "reason": "pure_geometry", "description": "A triangle"})
    assert "FIGURE_ASSET_MISSING" in codes(value, tmp_path)


def test_actual_hash_required_and_block_metadata_compared(tmp_path):
    asset = tmp_path / "fixture.bin"
    asset.write_bytes(b"synthetic asset bytes, not an exam illustration")
    value = item()
    value["problem_blocks"].append({"type": "figure", "path": str(asset), "allowed": True, "reason": "pure_geometry", "sha256": hashlib.sha256(asset.read_bytes()).hexdigest()})
    assert codes(value, tmp_path) == set()
    value["problem_blocks"][-1]["sha256"] = "0" * 64
    value["solution_completeness"]["included_block_count"] = 2
    assert {"FIGURE_ASSET_HASH_MISMATCH", "SOLUTION_DECLARED_COUNT_MISMATCH"} <= codes(value, tmp_path)


def test_verified_text_wrapper_must_not_hide_unwritten_choices(tmp_path):
    value = item()
    value["problem_blocks"] = [{"type": "text", "text": "Choices", "choices": [{"label": "A", "value": "1/2"}]}]
    assert "AUTHORING_UNCONSUMED_CONTENT" in codes(value, tmp_path)


def test_ocr_hard_break_and_disguised_figure_description_fail(tmp_path):
    value = item()
    value["solution_blocks"] = [{"type": "text", "role": "card_layout_figure", "text": "First row\nsecond row"}]
    assert {"FIGURE_DESCRIPTION_REPLACEMENT", "NATIVE_PARAGRAPH_REQUIRED"} <= codes(value, tmp_path)


def test_numeric_choices_and_formula_cells_need_typed_native_segments(tmp_path):
    value = item()
    value["problem_blocks"].append({"type": "choices", "cells": [["① 17", "x^2+1"]]})
    assert "FORMULA_UNTYPED_CELL" in codes(value, tmp_path)


def test_empty_or_duplicate_items_never_pass(tmp_path):
    assert audit_authoring_items([], asset_root=tmp_path)["status"] == "FAIL"
    assert "ITEM_ID_DUPLICATE" in {x["code"] for x in audit_authoring_items([item(), item()], asset_root=tmp_path)["findings"]}
    value = item()
    value["solution_blocks"] = []
    assert "AUTHORING_BODY_MISSING" in codes(value, tmp_path)


def test_two_competing_content_payloads_are_not_silently_ignored(tmp_path):
    value = item()
    value["problem_blocks"][0]["segments"] = [{"type": "text", "text": "Different input"}]
    assert "AUTHORING_AMBIGUOUS_CONTENT" in codes(value, tmp_path)


def test_piecewise_compiles_as_one_native_equation_with_conditions(tmp_path):
    value = item()
    value["problem_blocks"] = [{"type": "piecewise_function", "script_language": "latex", "name": "f(x)",
                                  "cases": [{"expression": "x^2", "condition": r"x\leq 0"}, {"expression": "x+1", "condition": "x>0"}]}]
    result = audit_authoring_items([value], asset_root=tmp_path)
    assert result["status"] == "PASS"
    assert result["counts"]["equations"] == 1
    assert "cases" in result["equations"][0]["script"]
    value["problem_blocks"][0]["cases"][1]["condition"] = ""
    assert "PIECEWISE_NATIVE_REQUIRED" in codes(value, tmp_path)


def test_source_aware_checkpoint_metadata_is_typed_and_traceable(tmp_path):
    value = item()
    value["problem_blocks"] = [{
        "type": "choices",
        "source_block_id": "SYN-1-P-01",
        "source_block_sequence": 1,
        "source_cells": [["① x^2"]],
        "cells": [[[
            {"type": "text", "text": "① "},
            {"type": "equation", "source_script": "x^{2}", "script_language": "hancom", "source_cell": "① x^{2}"},
        ]]],
    }]
    result = audit_authoring_items([value], asset_root=tmp_path)
    codes_seen = {row["code"] for row in result["findings"]}
    assert "AUTHORING_UNKNOWN_FIELD" not in codes_seen
    assert "FORMULA_UNTYPED_CELL" not in codes_seen
    assert "DIALECT_REQUIRED" not in codes_seen
    assert result["equations"]
    assert result["equations"][0]["script"] == "x^{2}"
