from __future__ import annotations

import hashlib

from app.pdf_hwp_formula_closure import build_formula_closure


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _source(*, occurrence_id: str | None = "SYN-1-F001", bbox: bool = True) -> dict:
    source = "x^2+1"
    formula = {
        "type": "equation",
        "ordinal": 1,
        "source": source,
        "source_text_sha256": _sha(source),
        "review_status": "VERIFIED",
        "source_crop_sha256": "b" * 64,
        "dpi": 900,
        "mathir": {"root": "power", "source_sha256": _sha(source)},
    }
    if occurrence_id:
        formula["formula_occurrence_id"] = occurrence_id
    if bbox:
        formula["bbox_pt"] = [10, 20, 80, 40]
    return formula


def _reviewed(formula: dict) -> dict:
    return {
        "schema_version": "math-source-manifest-v1",
        "status": "VERIFIED",
        "source_pdf_sha256": "a" * 64,
        "page_count": 1,
        "uncertainties": [],
        "content_sha256": "c" * 64,
        "pages": [{
            "pdf_page": 1,
            "status": "VERIFIED",
            "render_dpi": 600,
            "page_crop_sha256": "d" * 64,
            "items": [{"item_id": "SYN-1", "formulas": [formula]}],
        }],
        "formula_count": 1,
    }


def _authoring(*, occurrence_id: str | None = "SYN-1-F001", mathir: bool = True) -> dict:
    source = "x^2+1"
    block = {
        "type": "equation",
        "ordinal": 1,
        "script": source,
        "script_language": "hancom",
    }
    if occurrence_id:
        block["formula_occurrence_id"] = occurrence_id
    if mathir:
        block["mathir"] = {"root": "power", "source_sha256": _sha(source)}
    return {"items": [{"item_id": "SYN-1", "problem_blocks": [block], "solution_blocks": [{"type": "text", "text": "Synthetic."}]}]}


def test_exact_occurrence_id_closes_and_strict_gate_passes() -> None:
    report = build_formula_closure(_reviewed(_source()), _authoring())
    assert report["status"] == "PASS"
    assert report["candidate_only"] is False
    assert report["counts"]["evidence_closed_item_count"] == 1
    assert report["counts"]["evidence_open_item_count"] == 0
    assert report["formula_occurrences"][0]["closure_status"] == "CLOSED"


def test_unique_composite_key_is_exact_but_not_fuzzy() -> None:
    report = build_formula_closure(_reviewed(_source(occurrence_id=None)), _authoring(occurrence_id=None))
    assert report["status"] == "PASS"
    assert report["formula_occurrences"][0]["match_method"] == "exact_composite_key"

    wrong = _authoring(occurrence_id=None)
    wrong["items"][0]["problem_blocks"][0]["ordinal"] = 2
    report = build_formula_closure(_reviewed(_source(occurrence_id=None)), wrong)
    assert report["status"] == "REVIEW_REQUIRED"
    assert "FORMULA_AUTHORING_LINK_MISSING" in {row["code"] for row in report["findings"]}
    assert report["candidate_only"] is True


def test_conflicting_explicit_occurrence_id_cannot_fall_back_to_composite() -> None:
    report = build_formula_closure(_reviewed(_source()), _authoring(occurrence_id="SYN-1-F999"))
    codes = {row["code"] for row in report["findings"]}
    assert report["status"] == "REVIEW_REQUIRED"
    assert "FORMULA_AUTHORING_OCCURRENCE_ID_MISMATCH" in codes
    assert "FORMULA_AUTHORING_LINK_MISSING" in codes


def test_missing_mathir_stays_candidate_only() -> None:
    report = build_formula_closure(_reviewed(_source()), _authoring(mathir=False))
    codes = {row["code"] for row in report["findings"]}
    assert report["status"] == "REVIEW_REQUIRED"
    assert "FORMULA_AUTHORING_MATHIR_MISSING" in codes
    assert report["formula_occurrences"][0]["source_pdf_verified"] is False


def test_item_level_evidence_cannot_close_formula_geometry() -> None:
    source = _source(bbox=False)
    reviewed = _reviewed(source)
    reviewed["pages"][0]["items"][0]["source_evidence"] = {
        "pdf_page": 1,
        "bbox_pt": [1, 1, 100, 100],
        "source_crop_sha256": "e" * 64,
        "dpi": 900,
    }
    report = build_formula_closure(reviewed, _authoring())
    assert report["status"] == "REVIEW_REQUIRED"
    assert report["formula_occurrences"][0]["source_pdf_verified"] is False
    assert "FORMULA_SOURCE_REVIEW_OPEN" in {row["code"] for row in report["findings"]}
