"""Copyright-free policy/entrypoint consistency, not document production QA."""

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "config/pdf_hwp_v12_workflow.json"
INSTRUCTIONS = "PDF_HWP_V12_ONE_REQUEST_WORK_INSTRUCTIONS.md"
TRACE = "PDF_HWP_V12_FEEDBACK_TRACEABILITY.md"


def test_v12_one_request_policy_preserves_native_delivery_and_checkpoints():
    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    assert policy["workflow_id"] == "math-pdf-native-hwp-v12"
    assert policy["version"] == "1.0.0"
    assert policy["deliverable_roles"] == ["question", "solution", "integrated_endnote"]
    assert policy["deliverable_formats"] == ["hwp", "hwpx"]
    assert policy["per_item_delivery_default"] is False
    assert policy["preserve_variant_ids"] is True
    assert policy["com_parallelism"] == 1
    assert policy["endnotes"]["mode"] == "staged_atomic"
    assert policy["endnotes"]["placement"] == "END_OF_DOCUMENT"
    for key in ("independent_boundary_review_required", "native_transfer_test_required", "same_content_revision_required"):
        assert policy["endnotes"][key] is True
    assert policy["source_review_dpi"] == 600
    assert policy["high_risk_crop_dpi"] == 900
    assert policy["render_review_min_dpi"] >= 300
    assert policy["missing_solution"] == "continue_question_work_no_invented_solution"
    assert policy["source_content_in_git"] is False
    assert (ROOT / policy["default_style_file"]).is_file()


def test_next_task_entrypoints_link_the_same_v12_instructions():
    for name in ("AGENTS.md", "README.md", "docs/PDF_HWP_SOURCE_FIDELITY_V2_WORK_INSTRUCTIONS.md",
                 "docs/NATIVE_ENDNOTE_DOCUMENT_ORDER_POLICY.md", "docs/PDF_HWP_RELEASE_GATING_WORK_INSTRUCTIONS.md"):
        assert INSTRUCTIONS in (ROOT / name).read_text(encoding="utf-8"), name
    text = (ROOT / "docs" / INSTRUCTIONS).read_text(encoding="utf-8")
    assert TRACE in text
    for stage in range(8):
        assert f"| S{stage} |" in text


def test_feedback_requirement_ids_are_complete_unique_and_explicit():
    text = (ROOT / "docs" / TRACE).read_text(encoding="utf-8")
    identifiers = re.findall(r"^\| (V12-\d\d) \|", text, re.MULTILINE)
    assert identifiers == [f"V12-{index:02}" for index in range(1, 43)]
    for name in (INSTRUCTIONS, TRACE):
        body = (ROOT / "docs" / name).read_text(encoding="utf-8")
        for link in re.findall(r"\]\(([^)]+)\)", body):
            if not link.startswith("https://"):
                assert (ROOT / "docs" / link.split("#")[0]).is_file(), link


def test_model_defaults_do_not_silently_inherit_one_run_astra_override():
    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    assert policy["production_model_default"] == "gpt-5.6-luna"
    assert policy["production_reasoning_default"] == "max"
    assert policy["fast_mode"] is False
    assert policy["service_tier"] == "default"
    assert policy["automatic_model_switch"] is False
    assert "not_universal_converter" in policy["execution_kind"]
