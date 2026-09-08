import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "config/run_overrides/highend_4subjects_20260908_astra_low.json"


def test_single_run_not_global():
    p = json.loads(POLICY.read_text(encoding="utf-8"))
    assert p["applies_to"] == "current_run_only"
    assert p["change_global_settings"] is False
    assert p["automatic_model_fallback"] is False
    assert p["metadata_is_execution_proof"] is False


def test_requested_model_and_serial_operation():
    p = json.loads(POLICY.read_text(encoding="utf-8"))
    assert (p["requested_model"], p["reasoning_effort"]) == ("gpt-6-astra", "low")
    assert p["fast_mode"] is False
    assert p["production_subagents"] == 0
    assert p["max_concurrent_heavy_jobs"] == 1
    assert p["preserve_existing_artifacts"] is True


def test_required_evidence_is_not_relaxed():
    p = json.loads(POLICY.read_text(encoding="utf-8"))
    assert (p["source_review_dpi"], p["unclear_crop_dpi"], p["output_visual_min_dpi"]) == (600, 900, 300)
    assert {"source_content", "mathir_lineage", "endnote_linkage", "com_roundtrip", "all_page_visual", "remote_commit"} <= set(p["required_gates"])
    assert {"evidence_open_item_count", "approval_dialog_count", "owned_pid_remaining"} <= set(p["zero_required"])


def test_instruction_entrypoints_link_override():
    name = "HIGHEND_4SUBJECT_ASTRA_LOW_FINAL_EXECUTION_20260908.md"
    for path in ("AGENTS.md", "docs/PDF_HWP_SOURCE_FIDELITY_V2_WORK_INSTRUCTIONS.md", "docs/PDF_HWP_RELEASE_GATING_WORK_INSTRUCTIONS.md"):
        assert name in (ROOT / path).read_text(encoding="utf-8")
