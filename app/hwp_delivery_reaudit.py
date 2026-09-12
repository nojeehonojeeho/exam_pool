"""Read-only structural re-audit for a delivered HWP/HWPX folder.

This module deliberately does not open HWP through COM and does not claim
source-PDF fidelity.  It verifies the saved HWPX package, its native equation
metadata, and the HWP/HWPX pairing so a later source-and-COM gate can use a
stable, machine-readable starting point.
"""

from __future__ import annotations

import collections
import hashlib
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any
from zipfile import ZipFile


_SECTION_RE = re.compile(r"Contents/section\d+\.xml$")
_RAW_BACKSLASH_RE = re.compile(r"(?<!\\)\\[A-Za-z]+")


def _local(node: ET.Element) -> str:
    return node.tag.rsplit("}", 1)[-1]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def audit_hwpx(path: Path) -> dict[str, Any]:
    """Audit one HWPX package without modifying or opening it in Hanword."""

    path = Path(path)
    result: dict[str, Any] = {
        "path": str(path),
        "sha256": _sha256(path),
        "bytes": path.stat().st_size,
        "zip_test": None,
        "com_reopen_checked": False,
        "source_fidelity_checked": False,
    }
    with ZipFile(path) as package:
        result["zip_test"] = package.testzip()
        section_names = sorted(name for name in package.namelist() if _SECTION_RE.fullmatch(name))
        sections = [ET.fromstring(package.read(name)) for name in section_names]
        nodes = [node for section in sections for node in section.iter()]
        equations = [node for node in nodes if _local(node) == "equation"]
        paragraphs = [node for node in nodes if _local(node) == "p"]
        endnotes = [node for node in nodes if _local(node) == "endNote"]
        scripts = [node.findtext(".//{*}script", "") for node in equations]
        # Read only runs owned by each paragraph.  Walking ``paragraph.iter()``
        # would pull text from nested table cells or endnote sub-lists into
        # the ancestor and report the same visible formula more than once.
        paragraph_texts = [
            "".join(
                child.text or ""
                for run in paragraph
                if _local(run) == "run"
                for child in run
                if _local(child) == "t"
            )
            for paragraph in paragraphs
        ]
        text = "\n".join(paragraph_texts)
        raw_backslash_text = [
            {"paragraph_index": index + 1, "text": value}
            for index, value in enumerate(paragraph_texts)
            if _RAW_BACKSLASH_RE.search(value)
        ]
        result.update(
            {
                "sections": len(sections),
                "paragraphs": len(paragraphs),
                "equations": len(equations),
                "equation_fonts": dict(collections.Counter(node.get("font") for node in equations)),
                "equation_base_units": dict(collections.Counter(node.get("baseUnit") for node in equations)),
                "tables": sum(_local(node) == "tbl" for node in nodes),
                "pictures": sum(_local(node) == "pic" for node in nodes),
                "endnotes": len(endnotes),
                "raw_backslash_scripts": [
                    {"index": index + 1, "script": script}
                    for index, script in enumerate(scripts)
                    if _RAW_BACKSLASH_RE.search(script)
                ],
                # A formula command in hp:t is a lossy plain-text fallback,
                # even when another native equation follows in the same run.
                # Keep the paragraph index and complete visible text so the
                # repair queue can identify the exact source occurrence.
                "raw_backslash_text": raw_backslash_text,
                "sentence_fragment_signals": [
                    token for token in ("만들 수 있", "는 모든", "할 수") if token in text
                ],
            }
        )
    findings: list[dict[str, Any]] = []
    if result["zip_test"] is not None:
        findings.append({"code": "HWPX_ZIP_CORRUPT", "member": result["zip_test"]})
    if result["sections"] == 0:
        findings.append({"code": "HWPX_SECTION_MISSING"})
    if result["raw_backslash_scripts"]:
        findings.append({"code": "FORMULA_RAW_BACKSLASH", "count": len(result["raw_backslash_scripts"])})
    if result["raw_backslash_text"]:
        findings.append({"code": "FORMULA_RAW_BACKSLASH_TEXT", "count": len(result["raw_backslash_text"])})
    if result["equations"] and set(result["equation_fonts"]) != {"HYhwpEQ"}:
        findings.append({"code": "EQUATION_FONT_PROFILE_MISMATCH", "fonts": result["equation_fonts"]})
    if result["equations"] and set(result["equation_base_units"]) != {"1100"}:
        findings.append({"code": "EQUATION_BASEUNIT_PROFILE_MISMATCH", "base_units": result["equation_base_units"]})
    result["findings"] = findings
    result["structural_status"] = "PASS" if not findings else "FAIL"
    return result


def audit_delivery(root: Path) -> dict[str, Any]:
    """Audit all subject subfolders and require HWP/HWPX stem pairs."""

    root = Path(root)
    subjects: dict[str, Any] = {}
    for folder in sorted(path for path in root.iterdir() if path.is_dir()):
        hwpx_files = sorted(folder.glob("*.hwpx"))
        files = []
        pair_findings: list[dict[str, Any]] = []
        for hwpx in hwpx_files:
            files.append({
                "hwpx": audit_hwpx(hwpx),
                "hwp": {
                    "path": str(hwpx.with_suffix(".hwp")),
                    "exists": hwpx.with_suffix(".hwp").is_file(),
                    "sha256": _sha256(hwpx.with_suffix(".hwp")) if hwpx.with_suffix(".hwp").is_file() else None,
                },
            })
            if not hwpx.with_suffix(".hwp").is_file():
                pair_findings.append({"code": "HWP_HWPX_PAIR_MISSING", "hwpx": hwpx.name})
        extra_hwp = sorted(folder.glob("*.hwp"))
        if len(extra_hwp) != len(hwpx_files):
            pair_findings.append({"code": "HWP_HWPX_COUNT_MISMATCH", "hwp": len(extra_hwp), "hwpx": len(hwpx_files)})
        structural_failures = [entry for entry in files if entry["hwpx"]["structural_status"] != "PASS"]
        subjects[folder.name] = {
            "file_count": len(files),
            "expected_file_count": 3,
            "files": files,
            "findings": pair_findings,
            "structural_status": "PASS" if not structural_failures else "FAIL",
        }
    return {
        "schema": "hwp-delivery-reaudit-v1",
        "audit_only": True,
        "com_reopen_checked": False,
        "source_fidelity_checked": False,
        "release_status": "NOT_VERIFIED",
        "subjects": subjects,
    }
