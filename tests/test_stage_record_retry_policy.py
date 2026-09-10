from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/PDF_HWP_SOURCE_FIDELITY_V2_WORK_INSTRUCTIONS.md"


def test_stage_record_race_is_bounded_and_fail_closed():
    text = DOC.read_text(encoding="utf-8")
    assert "유한한 재시도 창" in text
    assert "STAGE_RECORD_UNREADABLE" in text
    assert "강제 종료하지 않으며" in text
    assert "PASS" in text and "FINAL" in text
