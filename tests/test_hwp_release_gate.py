from __future__ import annotations

import sys
import hashlib
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.hwp_content_invariant_qa import compare_content
from app.hwp_endnote_mapping_qa import validate_endnote_mapping
from app.hwp_release_gate import GATE_FIELDS, can_promote_final, evaluate_release, new_status
from app.hwp_visual_release_qa import validate_visual_report

_EVIDENCE_ROOT = Path(tempfile.mkdtemp(prefix="hwp-release-evidence-"))
_EVIDENCE = _EVIDENCE_ROOT / "qa.json"
_EVIDENCE.write_text('{"synthetic":true}\n', encoding="utf-8")
_EVIDENCE_SHA256 = hashlib.sha256(_EVIDENCE.read_bytes()).hexdigest()


def passing_status():
    s = new_status(document="x", source_document="s", generated=True, hwp_sha256="a" * 64, hwpx_sha256="b" * 64)
    s["evidence_root"] = str(_EVIDENCE_ROOT)
    s["evidence_files"] = [{"path": "qa.json", "sha256": _EVIDENCE_SHA256}]
    for field in GATE_FIELDS:
        s[field] = True
    return s


def test_all_gates_promote_final():
    assert can_promote_final(passing_status())
    assert evaluate_release(passing_status())["status"] == "FINAL"


def test_content_change_blocks_final():
    assert compare_content({"text": "1"}, {"text": "2"})["status"] == "FAIL"


def test_number_change_blocks_final():
    s = passing_status(); s["findings"] = [{"code": "NUMBER_CHANGED", "blocking": True}]
    assert not can_promote_final(s)


def test_formula_change_blocks_final():
    assert compare_content({"script": "x^2"}, {"script": "x^3"})["status"] == "FAIL"


def test_formula_count_mismatch_is_blocking():
    s = passing_status(); s["findings"] = [{"code": "FORMULA_COUNT_MISMATCH", "blocking": True}]
    assert evaluate_release(s)["final"] is False


def test_endnote_reference_missing_blocks():
    r = validate_endnote_mapping(["1"], [], [{"item_id": "1", "endnote_number": 1}])
    assert r["status"] == "FAIL"


def test_endnote_order_change_blocks():
    r = validate_endnote_mapping(["1", "2"], [{"item_id": "2"}, {"item_id": "1"}], [{"item_id": "1"}, {"item_id": "2"}])
    assert r["status"] == "FAIL"


def test_placeholder_blocks():
    s = passing_status(); s["evidence_files"] = ["pending OCR review"]
    assert evaluate_release(s)["final"] is False


def test_visual_finding_blocks():
    r = validate_visual_report({"expected_pages": 1, "checked_pages": 1, "pages": [{"findings": [{"code": "CLIPPED"}]}]})
    assert r["status"] == "FAIL"


def test_missing_status_evidence_cannot_promote():
    s = passing_status(); s.pop("hwpx_sha256")
    assert not can_promote_final(s)


def test_missing_evidence_file_list_cannot_promote():
    s = passing_status(); s["evidence_files"] = []
    assert not can_promote_final(s)


def test_partial_scope_cannot_promote():
    s = passing_status(); s["findings"] = [{"code": "PARTIAL_SCOPE", "blocking": True}]
    assert not can_promote_final(s)


def test_filename_is_not_a_gate():
    s = passing_status(); s["document"] = "x_FINAL.hwp"; s["visual_pass"] = False
    assert not can_promote_final(s)


def test_mapping_pass_requires_same_ids_and_order():
    fp = "f" * 64
    r = validate_endnote_mapping(
        ["1", "2"],
        [{"item_id": "1", "endnote_number": 1, "body_fingerprint": fp}, {"item_id": "2", "endnote_number": 2, "body_fingerprint": fp}],
        [{"item_id": "1", "endnote_number": 1, "body_fingerprint": fp}, {"item_id": "2", "endnote_number": 2, "body_fingerprint": fp}],
    )
    assert r["status"] == "PASS"


def test_visual_empty_pages_cannot_pass():
    r = validate_visual_report({"expected_pages": 2, "checked_pages": 2, "pages": []})
    assert r["status"] == "FAIL"


def test_visual_duplicate_page_numbers_cannot_pass():
    page = {"page": 1, "render_sha256": "a" * 64, "width_px": 100, "height_px": 100, "dpi": 300, "manual_review_completed": True}
    r = validate_visual_report({"expected_pages": 2, "checked_pages": 2, "pages": [page, dict(page)]})
    assert r["status"] == "FAIL"


def test_endnote_missing_identity_fields_cannot_pass():
    r = validate_endnote_mapping(["1"], [{"item_id": "1"}], [{"item_id": "1"}])
    assert r["status"] == "FAIL"
