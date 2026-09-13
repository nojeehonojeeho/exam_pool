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
            for block in page.get_text("blocks"):
                text = str(block[4] or "")
                if marker in _normalise(text):
                    result[index] = float(block[1]) / height
                    break
    return result


def audit_endnote_page_boundary(
    problem_pdf: Path,
    integrated_pdf: Path,
    integrated_hwpx: Path,
) -> dict[str, object]:
    """Return a fail-closed physical-page boundary report."""

    problem_pdf = problem_pdf.resolve()
    integrated_pdf = integrated_pdf.resolve()
    integrated_hwpx = integrated_hwpx.resolve()
    result: dict[str, object] = {
        "schema": "hwp-native-endnote-render-boundary-audit-v1",
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
    matching_pages = [
        index + 1
        for index, value in enumerate(integrated_pages)
        if marker and marker in _normalise(value)
    ]
    marker_ratios = _marker_vertical_ratios(integrated_pdf, marker) if marker else {}
    source_problem_page_count = len(problem_pages)
    first_endnote_page = matching_pages[0] if matching_pages else None
    last_main_story_page = first_endnote_page - 1 if first_endnote_page else None
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
            "last_main_story_page": last_main_story_page,
            "first_endnote_page": first_endnote_page,
            "first_endnote_heading_top_ratio": first_endnote_top_ratio,
            "previous_main_story_page_text_char_count": len(previous_page_text.strip()),
            "previous_main_story_page_contains_first_endnote_heading": bool(
                marker
                and last_main_story_page
                and marker in _normalise(previous_page_text)
            ),
        }
    )
    findings: list[dict[str, object]] = []
    if not marker:
        findings.append({"code": "ENDNOTE_PAGE_BOUNDARY_HEADING_EMPTY"})
    if first_endnote_page is not None and first_endnote_page <= 1:
        findings.append(
            {
                "code": "ENDNOTE_PAGE_BOUNDARY_NO_MAIN_STORY_PAGE",
                "actual": first_endnote_page,
            }
        )
    if first_endnote_page is None:
        findings.append(
            {"code": "ENDNOTE_PAGE_BOUNDARY_HEADING_NOT_RENDERED", "heading": heading}
        )
    elif first_endnote_top_ratio is None or first_endnote_top_ratio > 0.30:
        findings.append(
            {
                "code": "ENDNOTE_PAGE_BOUNDARY_NOT_FRESH_PAGE",
                "maximum_heading_top_ratio": 0.30,
                "actual_heading_top_ratio": first_endnote_top_ratio,
                "page": first_endnote_page,
            }
        )
    if not previous_page_text.strip():
        findings.append(
            {
                "code": "ENDNOTE_PAGE_BOUNDARY_BLANK_GAP",
                "page": last_main_story_page,
            }
        )
    if result["previous_main_story_page_contains_first_endnote_heading"]:
        findings.append(
            {
                "code": "ENDNOTE_PAGE_BOUNDARY_LEAKS_ON_FINAL_PROBLEM_PAGE",
                "page": last_main_story_page,
            }
        )
    result["findings"] = findings
    result["status"] = "PASS" if not findings else "FAIL"
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify that the first native endnote begins on the page after all problem pages."
    )
    parser.add_argument("--problem-pdf", required=True, type=Path)
    parser.add_argument("--integrated-pdf", required=True, type=Path)
    parser.add_argument("--integrated-hwpx", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    report = audit_endnote_page_boundary(args.problem_pdf, args.integrated_pdf, args.integrated_hwpx)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
