"""Regression coverage for the physical new-page boundary before endnotes."""

from __future__ import annotations

from pathlib import Path
from zipfile import ZipFile
import hashlib
import json

import fitz
import pytest

from tools.audit_hwp_endnote_page_boundary import audit_endnote_page_boundary
from tools.patch_hwp_first_native_endnote_page_break import patch_first_native_endnote_page_break


SECTION = """<?xml version='1.0' encoding='UTF-8'?>
<hs:sec xmlns:hs='http://www.hancom.co.kr/hwpml/2011/section' xmlns:hp='http://www.hancom.co.kr/hwpml/2011/paragraph'>
  <hp:secPr><hp:endNotePr><hp:placement place='END_OF_DOCUMENT'/></hp:endNotePr></hp:secPr>
  <hp:p id='0'><hp:run><hp:t>problem body</hp:t></hp:run><hp:ctrl><hp:endNote number='1'><hp:subList><hp:p id='1' pageBreak='0'><hp:run><hp:t>NOTE_ONE</hp:t></hp:run></hp:p></hp:subList></hp:endNote></hp:ctrl></hp:p>
  <hp:p id='2'><hp:run><hp:t>another problem</hp:t></hp:run><hp:ctrl><hp:endNote number='2'><hp:subList><hp:p id='3' pageBreak='0'><hp:run><hp:t>NOTE_TWO</hp:t></hp:run></hp:p></hp:subList></hp:endNote></hp:ctrl></hp:p>
  <hp:p id='4' pageBreak='0' columnBreak='0'><hp:run/><hp:linesegarray><hp:lineseg/></hp:linesegarray></hp:p>
</hs:sec>
"""


def _write_hwpx(path: Path) -> None:
    with ZipFile(path, "w") as archive:
        archive.writestr("Contents/section0.xml", SECTION)


def _write_pdf(path: Path, pages: list[tuple[str, float]]) -> None:
    document = fitz.open()
    for text, y in pages:
        page = document.new_page()
        page.insert_text((72, y), text)
    document.save(path)
    document.close()


def _review(path: Path, problem: Path, pdf: Path, hwpx: Path, last: int, first: int) -> Path:
    """Synthetic reviewer fixture, never used to mark actual pages reviewed."""
    records = []
    with fitz.open(pdf) as document:
        for page in sorted({last, first}):
            image = path.parent / f"{pdf.stem}-page-{page}.png"
            document[page - 1].get_pixmap(dpi=300).save(image)
            records.append({"page": page, "path": image.name, "dpi": 300,
                            "sha256": hashlib.sha256(image.read_bytes()).hexdigest(), "actual_viewed": True,
                            "renderer": "pymupdf", "renderer_version": fitz.VersionBind})
    value = {"schema": "hwp-endnote-boundary-review-v1", "reviewer": "synthetic-only",
             "reviewed_at": "2026-09-13T00:00:00Z", "last_question_id": "S-Q2",
             "first_endnote_item_id": "S-Q1", "first_native_endnote_heading": "NOTE_ONE",
             "last_main_story_page": last, "first_endnote_page": first, "pages": records,
             "bindings": {key + "_sha256": hashlib.sha256(file.read_bytes()).hexdigest()
                          for key, file in {"problem_pdf": problem, "integrated_pdf": pdf, "integrated_hwpx": hwpx}.items()}}
    for key in ("actual_viewed", "last_question_tail_seen", "first_endnote_seen",
                "all_questions_before_notes", "no_solutions_in_main", "notes_only_after_boundary", "no_blank_gap"):
        value[key] = True
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def test_first_native_endnote_patch_changes_only_terminal_main_story_paragraph(tmp_path: Path) -> None:
    source = tmp_path / "source.hwpx"
    target = tmp_path / "target.hwpx"
    _write_hwpx(source)

    report = patch_first_native_endnote_page_break(source, target)

    assert report["status"] == "PASS"
    assert report["page_break_before"] == "0"
    assert report["page_break_after"] == "1"
    assert source.read_bytes() != target.read_bytes()
    with ZipFile(target) as archive:
        xml = archive.read("Contents/section0.xml").decode("utf-8")
    assert "id=\"1\" pageBreak=\"0\"" in xml
    assert "id=\"3\" pageBreak=\"0\"" in xml
    assert "id=\"4\" pageBreak=\"1\"" in xml


def test_patch_fails_closed_when_endnote_placement_is_not_document_end(tmp_path: Path) -> None:
    source = tmp_path / "source.hwpx"
    target = tmp_path / "target.hwpx"
    _write_hwpx(source)
    with ZipFile(source, "a") as archive:
        archive.writestr("Contents/section1.xml", SECTION.replace("END_OF_DOCUMENT", "EACH_PAGE"))

    with pytest.raises(ValueError, match="END_OF_DOCUMENT"):
        patch_first_native_endnote_page_break(source, target)
    assert not target.exists()


def test_rendered_boundary_requires_a_fresh_page_after_problem_pages(tmp_path: Path) -> None:
    hwpx = tmp_path / "integrated.hwpx"
    problem_pdf = tmp_path / "problem.pdf"
    good_pdf = tmp_path / "good.pdf"
    bad_pdf = tmp_path / "bad.pdf"
    _write_hwpx(hwpx)
    _write_pdf(problem_pdf, [("problem text", 72)])
    _write_pdf(good_pdf, [("problem text", 72), ("NOTE_ONE\nanswer text", 72)])
    _write_pdf(bad_pdf, [("problem text\nNOTE_ONE\nanswer text", 650)])

    good_review = _review(tmp_path / "good-review.json", problem_pdf, good_pdf, hwpx, 1, 2)
    bad_review = _review(tmp_path / "bad-review.json", problem_pdf, bad_pdf, hwpx, 1, 1)
    assert audit_endnote_page_boundary(problem_pdf, good_pdf, hwpx, good_review)["status"] == "PASS"
    failed = audit_endnote_page_boundary(problem_pdf, bad_pdf, hwpx, bad_review)
    assert failed["status"] == "FAIL"
    assert any(finding["code"] == "ENDNOTE_PAGE_BOUNDARY_NOT_FRESH_PAGE" for finding in failed["findings"])


def test_missing_review_does_not_invent_last_question_page(tmp_path):
    hwpx, problem, pdf = [tmp_path / x for x in ("x.hwpx", "p.pdf", "i.pdf")]
    _write_hwpx(hwpx)
    _write_pdf(problem, [("problem", 72)])
    _write_pdf(pdf, [("problem", 72), ("NOTE_ONE", 72)])
    result = audit_endnote_page_boundary(problem, pdf, hwpx)
    assert result["status"] == "REVIEW_REQUIRED"
    assert result["last_main_story_page"] is None


@pytest.mark.parametrize("last,first", [(1, 1), (1, 3)])
def test_top_of_page_or_blank_gap_cannot_replace_independent_boundary(tmp_path, last, first):
    hwpx, problem, pdf = [tmp_path / x for x in ("x.hwpx", "p.pdf", "i.pdf")]
    _write_hwpx(hwpx)
    _write_pdf(problem, [("problem", 72)])
    _write_pdf(pdf, [("problem\nNOTE_ONE", 72), ("", 72), ("NOTE_ONE", 72)])
    review = _review(tmp_path / "review.json", problem, pdf, hwpx, last, first)
    assert audit_endnote_page_boundary(problem, pdf, hwpx, review)["status"] == "FAIL"


def test_boundary_rejects_stale_hash_and_different_heading(tmp_path):
    hwpx, problem, pdf = [tmp_path / x for x in ("x.hwpx", "p.pdf", "i.pdf")]
    _write_hwpx(hwpx)
    _write_pdf(problem, [("problem", 72)])
    _write_pdf(pdf, [("problem", 72), ("XNOTE_ONE", 72)])
    review = _review(tmp_path / "review.json", problem, pdf, hwpx, 1, 2)
    assert audit_endnote_page_boundary(problem, pdf, hwpx, review)["status"] == "FAIL"
    value = json.loads(review.read_text())
    value["bindings"]["integrated_pdf_sha256"] = "0" * 64
    review.write_text(json.dumps(value))
    assert audit_endnote_page_boundary(problem, pdf, hwpx, review)["status"] == "REVIEW_REQUIRED"


def test_pipeline_rechecks_real_boundary_inputs_before_release(tmp_path):
    from app.hwp_release_gate import new_status, GATE_FIELDS
    from app.pdf_hwp_pipeline_gate import require_final_release
    hwpx, problem, pdf = [tmp_path / x for x in ("x.hwpx", "p.pdf", "i.pdf")]
    _write_hwpx(hwpx)
    _write_pdf(problem, [("problem", 72)])
    _write_pdf(pdf, [("problem", 72), ("NOTE_ONE", 72)])
    review = _review(tmp_path / "review.json", problem, pdf, hwpx, 1, 2)
    report = audit_endnote_page_boundary(problem, pdf, hwpx, review)
    report_path = tmp_path / "boundary.json"
    report_path.write_text(json.dumps(report))
    status = new_status(document="synthetic", source_document="synthetic", generated=True,
                        hwp_sha256="a" * 64, hwpx_sha256=hashlib.sha256(hwpx.read_bytes()).hexdigest(),
                        endnote_reference_count=2, endnote_body_count=2)
    status.update({field: True for field in GATE_FIELDS})
    status.update(evidence_root=str(tmp_path), evidence_files=[{"path": report_path.name,
                  "sha256": hashlib.sha256(report_path.read_bytes()).hexdigest()}])
    with pytest.raises(RuntimeError, match="ENDNOTE_BOUNDARY_RELEASE_EVIDENCE_MISSING"):
        require_final_release(status)
    status["endnote_boundary_report"] = report_path.name
    assert require_final_release(status)["final"] is True
    review.write_text("{}")
    with pytest.raises(RuntimeError, match="ENDNOTE_BOUNDARY_RELEASE_EVIDENCE_INVALID"):
        require_final_release(status)


def test_numbered_heading_does_not_match_suffix_of_another_number(tmp_path):
    hwpx, problem, pdf = [tmp_path / x for x in ("x.hwpx", "p.pdf", "i.pdf")]
    with ZipFile(hwpx, "w") as archive:
        archive.writestr("Contents/section0.xml", SECTION.replace("NOTE_ONE", "1 answer"))
    _write_pdf(problem, [("problem", 72)])
    _write_pdf(pdf, [("problem", 72), ("11 answer", 72)])
    result = audit_endnote_page_boundary(problem, pdf, hwpx)
    assert result["matching_pages"] == []
    assert result["status"] != "PASS"


def test_image_only_last_question_page_is_not_inferred_blank(tmp_path):
    hwpx, problem, pdf = [tmp_path / x for x in ("x.hwpx", "p.pdf", "i.pdf")]
    _write_hwpx(hwpx)
    _write_pdf(problem, [("problem", 72)])
    with fitz.open() as document:
        page = document.new_page()
        page.draw_rect(fitz.Rect(80, 80, 150, 150), fill=(0, 0, 0))
        document.new_page().insert_text((72, 72), "NOTE_ONE")
        document.save(pdf)
    review = _review(tmp_path / "review.json", problem, pdf, hwpx, 1, 2)
    result = audit_endnote_page_boundary(problem, pdf, hwpx, review)
    assert result["previous_main_story_page_text_char_count"] == 0
    assert result["status"] == "PASS"


def test_render_from_wrong_page_cannot_be_relabelled_with_a_new_hash(tmp_path):
    hwpx, problem, pdf = [tmp_path / x for x in ("x.hwpx", "p.pdf", "i.pdf")]
    _write_hwpx(hwpx)
    _write_pdf(problem, [("problem", 72)])
    _write_pdf(pdf, [("problem", 72), ("NOTE_ONE", 72)])
    review = _review(tmp_path / "review.json", problem, pdf, hwpx, 1, 2)
    data = json.loads(review.read_text())
    data["pages"][1]["path"] = data["pages"][0]["path"]
    data["pages"][1]["sha256"] = data["pages"][0]["sha256"]
    review.write_text(json.dumps(data))
    result = audit_endnote_page_boundary(problem, pdf, hwpx, review)
    assert result["status"] == "REVIEW_REQUIRED"


def test_patch_does_not_add_a_second_break_or_move_visible_content(tmp_path):
    source, one, two = [tmp_path / x for x in ("source.hwpx", "one.hwpx", "two.hwpx")]
    _write_hwpx(source)
    patch_first_native_endnote_page_break(source, one)
    report = patch_first_native_endnote_page_break(one, two)
    assert report["changed"] is False
    with ZipFile(source, "w") as archive:
        archive.writestr("Contents/section0.xml", SECTION.replace("<hp:run/>", "<hp:run><hp:t>last choice</hp:t></hp:run>"))
    with pytest.raises(ValueError, match="not empty"):
        patch_first_native_endnote_page_break(source, tmp_path / "forbidden.hwpx")
