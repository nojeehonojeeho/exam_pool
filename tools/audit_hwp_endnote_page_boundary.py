"""Rendered-PDF proof for the physical boundary before native endnotes.

This is intentionally separate from HWPX structure auditing.  A document can
declare ``END_OF_DOCUMENT`` and still put the first endnote at the bottom of
the page that contains the final problem.  The release contract requires the
first native-endnote heading to occur on a fresh physical page: at the top of
a page immediately after a non-blank main-story page.  The standalone problem
PDF page count is retained as a reference only, because adding native markers
can legitimately change pagination without changing the question content.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import zipfile
from datetime import datetime
from pathlib import Path
import xml.etree.ElementTree as ET

import fitz


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].split(":", 1)[-1]


def _normalise(value: str) -> str:
    return re.sub(r"\s+", "", value).casefold()


def _section_members(archive: zipfile.ZipFile) -> list[str]:
    names = [
        name
        for name in archive.namelist()
        if re.search(r"(?:^|/)section\d+\.xml$", name, flags=re.IGNORECASE)
    ]
    return sorted(
        names,
        key=lambda name: (
            int(re.search(r"section(\d+)\.xml$", name, flags=re.IGNORECASE).group(1))
            if re.search(r"section(\d+)\.xml$", name, flags=re.IGNORECASE)
            else 2**31 - 1,
            name.lower(),
        ),
    )


def first_native_endnote_heading(hwpx_path: Path) -> str:
    """Return the first non-empty paragraph visible inside the first endnote."""

    with zipfile.ZipFile(hwpx_path) as archive:
        for member in _section_members(archive):
            root = ET.fromstring(archive.read(member))
            for note in root.iter():
                if _local_name(note.tag) != "endNote":
                    continue
                for paragraph in note.iter():
                    if _local_name(paragraph.tag) != "p":
                        continue
                    text = "".join(
                        child.text or ""
                        for child in paragraph.iter()
                        if _local_name(child.tag) == "t"
                    ).strip()
                    if text:
                        return text
    raise ValueError("no visible native endnote heading found in HWPX")


def _pdf_page_texts(path: Path) -> list[str]:
    with fitz.open(path) as document:
        return [page.get_text("text") for page in document]


def _marker_vertical_ratios(path: Path, marker: str) -> dict[int, float]:
    """Return the first marker block's y-position ratio for every rendered page."""

    result: dict[int, float] = {}
    with fitz.open(path) as document:
        for index, page in enumerate(document, start=1):
            height = max(float(page.rect.height), 1.0)
            for block in page.get_text("dict")["blocks"]:
                for line in block.get("lines", []):
                    text = "".join(span.get("text", "") for span in line.get("spans", []))
                    # '1 answer' must not match '11 answer' or inline prose.
                    if marker == _normalise(text):
                        result.setdefault(index, float(line["bbox"][1]) / height)
    return result


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _review_boundary(review_path: Path | None, inputs: dict[str, Path], page_count: int,
                     heading: str) -> tuple[dict, list[dict]]:
    """Validate independent, actually viewed boundary records, never invent them.

    A heading y-coordinate cannot prove which page contains the final question.
    The reviewer locates the *tail* (including final choices/figures/equations)
    and the first note independently, in full-page renders. These records prove
    only the viewed boundary, not whole-book source fidelity or editor transfer.
    """
    if review_path is None:
        return {}, [{"code": "ENDNOTE_BOUNDARY_INDEPENDENT_REVIEW_REQUIRED"}]
    try:
        review_path = review_path.resolve()
        review = json.loads(review_path.read_text(encoding="utf-8-sig"))
        if not isinstance(review, dict):
            raise ValueError("review must be an object")
        if review.get("schema") != "hwp-endnote-boundary-review-v1":
            raise ValueError("unsupported boundary review schema")
        for key, path in inputs.items():
            if review.get("bindings", {}).get(key + "_sha256") != _sha256(path):
                raise ValueError(f"stale/missing input binding: {key}")
        for key in ("reviewer", "reviewed_at", "last_question_id", "first_endnote_item_id"):
            if not isinstance(review.get(key), str) or not review[key].strip():
                raise ValueError(f"missing review identity: {key}")
        if datetime.fromisoformat(review["reviewed_at"].replace("Z", "+00:00")).tzinfo is None:
            raise ValueError("review time must include timezone")
        checks = ("actual_viewed", "last_question_tail_seen", "first_endnote_seen",
                  "all_questions_before_notes", "no_solutions_in_main",
                  "notes_only_after_boundary", "no_blank_gap")
        if any(review.get(key) is not True for key in checks):
            raise ValueError("independent boundary checks not completed")
        if _normalise(review.get("first_native_endnote_heading", "")) != _normalise(heading):
            raise ValueError("first native note identity does not match HWPX")
        last = review.get("last_main_story_page")
        first = review.get("first_endnote_page")
        if any(type(x) is not int or not 1 <= x <= page_count for x in (last, first)):
            raise ValueError("invalid physical page numbers")
        if first != last + 1:
            return review, [{"code": "ENDNOTE_PAGE_BOUNDARY_NOT_FRESH_PAGE",
                             "last_main_story_page": last, "first_endnote_page": first}]
        renders = review.get("pages")
        if not isinstance(renders, list) or len(renders) != 2:
            raise ValueError("two independently viewed full-page renders required")
        if {x.get("page") for x in renders} != {last, first}:
            raise ValueError("render pages do not match the independent boundary")
        for record in renders:
            if (record.get("actual_viewed") is not True or type(record.get("page")) is not int
                    or type(record.get("dpi")) is not int or not 300 <= record["dpi"] <= 900):
                raise ValueError("page review/dpi missing")
            if record.get("renderer") != "pymupdf" or record.get("renderer_version") != fitz.VersionBind:
                raise ValueError("boundary render engine/version not recorded or changed")
            image_path = (review_path.parent / record["path"]).resolve()
            image_path.relative_to(review_path.parent)
            if _sha256(image_path) != record.get("sha256"):
                raise ValueError("changed boundary render")
            pix = fitz.Pixmap(str(image_path))
            with fitz.open(inputs["integrated_pdf"]) as pdf:
                page = pdf[record["page"] - 1]
                rect = page.rect
                expected = (rect.width * record["dpi"] / 72, rect.height * record["dpi"] / 72)
                expected_pix = page.get_pixmap(dpi=record["dpi"], colorspace=fitz.csRGB, alpha=False)
            if abs(pix.width - expected[0]) > 2 or abs(pix.height - expected[1]) > 2:
                raise ValueError("review requires full physical page render, not a crop")
            if pix.n != expected_pix.n or hashlib.sha256(pix.samples).digest() != hashlib.sha256(expected_pix.samples).digest():
                raise ValueError("review PNG is not a render of the bound PDF/page")
        review["review_path"] = str(review_path)
        review["review_sha256"] = _sha256(review_path)
        return review, []
    except (OSError, ValueError, KeyError, TypeError, AttributeError, RuntimeError) as exc:
        return {}, [{"code": "ENDNOTE_BOUNDARY_REVIEW_INVALID", "message": str(exc)}]


def audit_endnote_page_boundary(
    problem_pdf: Path,
    integrated_pdf: Path,
    integrated_hwpx: Path,
    boundary_review: Path | None = None,
) -> dict[str, object]:
    """Return a fail-closed physical-page boundary report."""

    problem_pdf = problem_pdf.resolve()
    integrated_pdf = integrated_pdf.resolve()
    integrated_hwpx = integrated_hwpx.resolve()
    result: dict[str, object] = {
        "schema": "hwp-native-endnote-render-boundary-audit-v2",
        "problem_pdf": str(problem_pdf),
        "integrated_pdf": str(integrated_pdf),
        "integrated_hwpx": str(integrated_hwpx),
        "status": "FAIL",
        "findings": [],
    }
    try:
        problem_pages = _pdf_page_texts(problem_pdf)
        integrated_pages = _pdf_page_texts(integrated_pdf)
        heading = first_native_endnote_heading(integrated_hwpx)
    except (OSError, ValueError, fitz.FileDataError, zipfile.BadZipFile, ET.ParseError) as exc:
        result["findings"] = [{"code": "ENDNOTE_PAGE_BOUNDARY_INPUT_INVALID", "message": str(exc)}]
        return result
    marker = _normalise(heading)
    marker_ratios = _marker_vertical_ratios(integrated_pdf, marker) if marker else {}
    matching_pages = sorted(marker_ratios)
    source_problem_page_count = len(problem_pages)
    inputs = {"problem_pdf": problem_pdf, "integrated_pdf": integrated_pdf, "integrated_hwpx": integrated_hwpx}
    review, review_findings = _review_boundary(boundary_review, inputs, len(integrated_pages), heading)
    first_endnote_page = review.get("first_endnote_page")
    last_main_story_page = review.get("last_main_story_page")
    first_endnote_top_ratio = marker_ratios.get(first_endnote_page) if first_endnote_page else None
    previous_page_text = (
        integrated_pages[last_main_story_page - 1]
        if last_main_story_page and 1 <= last_main_story_page <= len(integrated_pages)
        else ""
    )
    result.update(
        {
            "reference_problem_page_count": source_problem_page_count,
            "integrated_page_count": len(integrated_pages),
            "first_native_endnote_heading": heading,
            "first_native_endnote_heading_normalized": marker,
            "matching_pages": matching_pages,
            "candidate_first_endnote_page": matching_pages[0] if matching_pages else None,
            "input_sha256": {key: _sha256(path) for key, path in inputs.items()},
            "independent_review": review,
            "scope": "physical_boundary_only_not_source_fidelity",
            "last_main_story_page": last_main_story_page,
            "first_endnote_page": first_endnote_page,
            "first_endnote_heading_top_ratio": first_endnote_top_ratio,
            "previous_main_story_page_text_char_count": len(previous_page_text.strip()),
            "previous_main_story_page_contains_first_endnote_heading": bool(
                marker
                and last_main_story_page
                and last_main_story_page in marker_ratios
            ),
        }
    )
    findings: list[dict[str, object]] = list(review_findings)
    if first_endnote_page and any(page < first_endnote_page for page in matching_pages):
        findings.append({"code": "ENDNOTE_BOUNDARY_EARLIER_HEADING_REQUIRES_REVIEW",
                         "matching_pages": matching_pages})
    if not marker:
        findings.append({"code": "ENDNOTE_PAGE_BOUNDARY_HEADING_EMPTY"})
    if first_endnote_page is not None and first_endnote_page <= 1:
        findings.append(
            {
                "code": "ENDNOTE_PAGE_BOUNDARY_NO_MAIN_STORY_PAGE",
                "actual": first_endnote_page,
            }
        )
    if first_endnote_page is not None and first_endnote_page not in matching_pages:
        findings.append(
            {"code": "ENDNOTE_PAGE_BOUNDARY_HEADING_NOT_RENDERED", "heading": heading}
        )
    elif first_endnote_page is not None and (first_endnote_top_ratio is None or first_endnote_top_ratio > 0.30):
        findings.append(
            {
                "code": "ENDNOTE_PAGE_BOUNDARY_NOT_FRESH_PAGE",
                "maximum_heading_top_ratio": 0.30,
                "actual_heading_top_ratio": first_endnote_top_ratio,
                "page": first_endnote_page,
            }
        )
    # Text-less pages may contain the final graph/equation. Do not declare them
    # blank based on PDF text extraction; the independent full-page review applies.
    if result["previous_main_story_page_contains_first_endnote_heading"]:
        findings.append(
            {
                "code": "ENDNOTE_PAGE_BOUNDARY_LEAKS_ON_FINAL_PROBLEM_PAGE",
                "page": last_main_story_page,
            }
        )
    result["findings"] = findings
    result["status"] = "PASS" if not findings else ("REVIEW_REQUIRED" if review_findings and not review else "FAIL")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify that the first native endnote begins on the page after all problem pages."
    )
    parser.add_argument("--problem-pdf", required=True, type=Path)
    parser.add_argument("--integrated-pdf", required=True, type=Path)
    parser.add_argument("--integrated-hwpx", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--boundary-review", type=Path,
                        help="Hash-bound, independently viewed final-question/first-note pages; missing = REVIEW_REQUIRED")
    args = parser.parse_args()
    report = audit_endnote_page_boundary(args.problem_pdf, args.integrated_pdf, args.integrated_hwpx, args.boundary_review)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
