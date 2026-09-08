from app.hwp_solution_flow import bind_solution_flow
from app.hwp_authoring_preflight import audit_authoring_items
from pathlib import Path


def test_source_group_stays_together_without_rewriting():
    source=[{"type":"text","text":"합은"},{"type":"display_equation","script":"2+3=5"},
            {"type":"text","role":"supplement","text":"설명"},{"type":"text","text":"다음 문장"}]
    result=bind_solution_flow(source)
    assert result[0]["keep_with_next"] is True
    assert result[1]["keep_with_next"] is True
    assert "keep_with_next" not in result[2]
    assert "keep_with_next" not in source[0]
    assert [{k:v for k,v in b.items() if k!="keep_with_next"} for b in result]==source


def test_does_not_bind_unrelated_following_paragraph():
    blocks=[{"type":"display_equation","script":"a=b"},{"type":"text","text":"다른 문단"}]
    assert bind_solution_flow(blocks)==blocks


def test_real_authoring_boundary_accepts_explicit_flow_properties():
    blocks=bind_solution_flow([{"type":"text","text":"합은"},
         {"type":"display_equation","script":"2+3=5","script_language":"hancom"},
         {"type":"text","role":"supplement","text":"설명"}])
    result=audit_authoring_items([{"item_id":"synthetic-1","problem_blocks":blocks,"solution_blocks":blocks}],asset_root=Path("."))
    assert not result["findings"]


def test_string_false_is_not_a_valid_flow_flag():
    from app.pdf_hwp_source_fidelity_v2 import normalize_content_blocks
    _, _, findings = normalize_content_blocks([{"type": "text", "text": "합성", "keep_with_next": "false"}])
    assert any(f["code"] == "AUTHORING_FLOW_FLAG_INVALID" for f in findings)
