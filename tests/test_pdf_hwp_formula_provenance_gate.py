import hashlib

from app.pdf_hwp_formula_provenance_gate import audit_formula_provenance


def _formula(**overrides):
    source = "x^2+1"
    source_hash = hashlib.sha256(source.encode()).hexdigest()
    record = {
        "type": "equation",
        "formula_occurrence_id": "SYN-1-F001",
        "source_order": 1,
        "script": source,
        "script_language": "hancom",
        "source_pdf_verified": True,
        "source_text_sha256": source_hash,
        "source_pdf_sha256": "a" * 64,
        "mathir": {"root": "power", "source_sha256": source_hash},
        "source_evidence": {
            "pdf_page": 11,
            "bbox_pt": [10, 20, 80, 40],
            "source_crop_sha256": "b" * 64,
            "dpi": 900,
            "review_status": "SOURCE_REVIEWED_600_AND_900",
        },
    }
    record.update(overrides)
    return record


def _manifest(formulas):
    return {
        "source_pdf_sha256": "a" * 64,
        "items": [{
            "item_id": "SYN-1",
            "problem_blocks": formulas,
            "solution_blocks": [{"type": "text", "text": "Synthetic solution."}],
        }],
    }


def test_script_only_formula_is_not_source_verified():
    value = _manifest([{"type": "equation", "script": "x^2+1", "script_language": "hancom"}])
    result = audit_formula_provenance(value)
    codes = {row["code"] for row in result["findings"]}
    assert result["status"] == "FAIL"
    assert {"FORMULA_OCCURRENCE_ID_MISSING", "FORMULA_SOURCE_EVIDENCE_MISSING", "MATHIR_MISSING"} <= codes


def test_complete_formula_provenance_passes():
    result = audit_formula_provenance(_manifest([_formula()]))
    assert result["status"] == "PASS"
    assert result["passed"] is True
    assert result["counts"]["formula_occurrences"] == 1
    assert result["counts"]["findings"] == 0


def test_mathir_hash_and_crop_are_independent_gates():
    value = _manifest([_formula(mathir={"root": "power", "source_sha256": "c" * 64})])
    value["items"][0]["problem_blocks"][0]["source_evidence"]["source_crop_sha256"] = "not-a-hash"
    codes = {row["code"] for row in audit_formula_provenance(value)["findings"]}
    assert {"MATHIR_SOURCE_HASH_MISMATCH", "FORMULA_SOURCE_CROP_HASH_MISSING"} <= codes


def test_duplicate_occurrence_ids_are_not_collapsed():
    first = _formula()
    second = _formula(source_order=2)
    result = audit_formula_provenance(_manifest([first, second]))
    assert "FORMULA_OCCURRENCE_ID_DUPLICATE" in {row["code"] for row in result["findings"]}
