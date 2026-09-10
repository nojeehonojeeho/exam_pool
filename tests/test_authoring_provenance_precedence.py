from app.hwp_authoring_preflight import audit_authoring_items


def test_reviewed_formula_provenance_is_not_overwritten_by_compiler_defaults(tmp_path):
    reviewed = {
        "item_id": "SYN-PROV-1",
        "review_status": "VERIFIED",
        "uncertainties": [],
        "problem_blocks": [{
            "type": "equation",
            "script": "x^2+1",
            "script_language": "latex",
            "formula_occurrence_id": "SYN-PROV-F001",
            "source_pdf_verified": True,
            "mathir": {"tree": {"kind": "synthetic"}},
            "source_evidence": {"dpi": 900, "review_status": "VERIFIED"},
            "source_text_sha256": "abc",
        }],
        "solution_blocks": [{"type": "text", "text": "Synthetic explanation."}],
        "solution_completeness": {"source_block_count": 1, "included_block_count": 1},
    }

    result = audit_authoring_items([reviewed], asset_root=tmp_path)
    assert result["status"] == "PASS"
    equation = result["equations"][0]
    assert equation["formula_occurrence_id"] == "SYN-PROV-F001"
    assert equation["source_pdf_verified"] is True
    assert equation["mathir"] == {"tree": {"kind": "synthetic"}}
    assert equation["source_evidence"]["dpi"] == 900
