"""Audit the user-facing layout contract of an integrated HWP/HWPX package.

The native HWPX representation keeps each ``hp:endNote`` control at its
problem anchor.  The saved ``hp:endNotePr/hp:placement`` value controls where
Hanword renders the body.  This read-only auditor makes that distinction
explicit and checks the contract used by all four HIGH-END subjects:

* the main-body text is not carrying solution headings;
* native endnote bodies and ENDNOTE auto-number controls are present; and
* every native endnote control is attached to a main-story paragraph anchor;
* declared ``endNotePr`` sections use ``END_OF_DOCUMENT`` for endnotes; and
  at least one such declaration exists when native endnotes are present.

This is a structural candidate gate.  It does not claim source-PDF fidelity,
Hanword COM re-open, visual rendering, or copy/move proof; those remain
independent release gates.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import zipfile
from pathlib import Path
import xml.etree.ElementTree as ET


REQUIRED_PLACEMENT = "END_OF_DOCUMENT"
REQUIRED_SUBJECTS = ("고등수학상", "고등수학하", "수학II", "확률과_통계")
AUDIT_SCHEMA = "integrated-endnote-layout-audit-v2"
_SOLUTION_MARKER_RE = re.compile(
    r"(?:^|\s)(?:정답\s*(?:및\s*)?풀이|해설(?:\s*제목)?)(?=\s|[:：|]|$)"
)


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].split(":", 1)[-1]


def _text(element: ET.Element) -> str:
    return "".join(element.itertext())


def _native_reference_anchors(
    root: ET.Element,
    parent: dict[ET.Element, ET.Element],
) -> tuple[list[ET.Element], list[ET.Element]]:
    """Return endnotes whose controls have an outside-body paragraph anchor.

    HWPX stores a native endnote as ``hp:ctrl/hp:endNote``.  The control must
    be a descendant of the main-story paragraph that owns the reference; the
    ``subList`` paragraphs inside the endnote body are not references.  Older
    structural checks counted only ``hp:endNote`` and could therefore accept a
    detached body-only package.  Walking the parent chain keeps the check
    namespace-agnostic and works for anchors nested in table cells as well.
    """

    notes = [element for element in root.iter() if _local_name(element.tag) == "endNote"]
    anchored: list[ET.Element] = []
    for note in notes:
        current = parent.get(note)
        anchor_paragraph: ET.Element | None = None
        while current is not None:
            local = _local_name(current.tag)
            if local == "endNote":
                # A nested endnote body is not a main-story anchor.
                anchor_paragraph = None
                break
            if local == "p":
                anchor_paragraph = current
                break
            current = parent.get(current)
        if anchor_paragraph is not None:
            anchored.append(anchor_paragraph)
    return notes, anchored


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _section_members(archive: zipfile.ZipFile) -> list[str]:
    members = [
        name
        for name in archive.namelist()
        if re.search(r"(?:^|/)section\d+\.xml$", name, flags=re.IGNORECASE)
    ]

    def sort_key(name: str) -> tuple[int, str]:
        match = re.search(r"section(\d+)\.xml$", name, flags=re.IGNORECASE)
        return (int(match.group(1)) if match else 2**31 - 1, name.lower())

    return sorted(members, key=sort_key)


def _endnote_placement_values(root: ET.Element) -> tuple[list[str], bool]:
    """Return native-endnote placement values and whether ``endNotePr`` exists.

    ``footNotePr`` is a separate setting and must not participate in this
    contract.  A declared property without a placement, or a placement with
    a blank ``place`` attribute, is represented by an empty value so callers
    can report ``ENDNOTE_PLACEMENT_UNDECLARED`` just like the canonical app
    gate.
    """

    properties = [element for element in root.iter() if _local_name(element.tag) == "endNotePr"]
    if not properties:
        return [], False
    values: list[str] = []
    for property_element in properties:
        placements = [
            element
            for element in property_element.iter()
            if _local_name(element.tag) == "placement"
        ]
        if not placements:
            values.append("")
            continue
        values.extend(
            next(
                (value for key, value in element.attrib.items() if _local_name(key) == "place"),
                "",
            )
            .strip()
            .upper()
            for element in placements
        )
    return values, True


def audit_hwpx(path: Path) -> dict[str, object]:
    try:
        raw_bytes = path.read_bytes()
    except OSError as exc:
        return {
            "path": str(path),
            "sha256": None,
            "status": "FAIL",
            "sections": [],
            "counts": {
                "sections": 0,
                "endnotes": 0,
                "endnote_autonum": 0,
                "main_text_chars": 0,
                "endnote_text_chars": 0,
                "main_solution_marker_count": 0,
                "empty_endnote_bodies": 0,
                "native_reference_anchor_count": 0,
            },
            "findings": [{"code": "INVALID_HWPX", "message": str(exc)}],
        }
    result: dict[str, object] = {
        "path": str(path),
        "sha256": hashlib.sha256(raw_bytes).hexdigest(),
        "status": "FAIL",
        "sections": [],
        "counts": {
            "sections": 0,
            "endnotes": 0,
            "endnote_autonum": 0,
            "main_text_chars": 0,
                "endnote_text_chars": 0,
                "main_solution_marker_count": 0,
                "empty_endnote_bodies": 0,
                "native_reference_anchor_count": 0,
            },
        "findings": [],
    }
    try:
        archive = zipfile.ZipFile(path)
    except (OSError, zipfile.BadZipFile) as exc:
        result["findings"] = [{"code": "INVALID_HWPX", "message": str(exc)}]
        return result

    with archive:
        section_names = _section_members(archive)
        result["counts"]["sections"] = len(section_names)  # type: ignore[index]
        if not section_names:
            result["findings"].append({"code": "NO_SECTION_XML", "message": "no section XML"})  # type: ignore[union-attr]
            return result
        total_notes = 0
        total_autonum = 0
        main_chars = 0
        note_chars = 0
        marker_count = 0
        empty_note_count = 0
        section_reports: list[dict[str, object]] = []
        section_endnote_placements: dict[str, list[str]] = {}
        section_endnote_pr_declared: dict[str, bool] = {}
        for member in section_names:
            raw = archive.read(member)
            try:
                root = ET.fromstring(raw)
            except ET.ParseError as exc:
                result["findings"].append(  # type: ignore[union-attr]
                    {"code": "INVALID_SECTION_XML", "section": member, "message": str(exc)}
                )
                continue
            parent = {child: parent for parent in root.iter() for child in parent}

            def under(element: ET.Element, ancestor_name: str) -> bool:
                current = parent.get(element)
                while current is not None:
                    if _local_name(current.tag) == ancestor_name:
                        return True
                    current = parent.get(current)
                return False

            notes, anchored_notes = _native_reference_anchors(root, parent)
            empty_notes = [note for note in notes if not _text(note).strip()]
            empty_note_count += len(empty_notes)
            auto = [
                element
                for element in root.iter()
                if _local_name(element.tag) == "autoNum"
                and next((value for key, value in element.attrib.items() if _local_name(key) == "numType"), "").upper()
                == "ENDNOTE"
            ]
            placements, declared = _endnote_placement_values(root)
            section_endnote_placements[member] = placements
            section_endnote_pr_declared[member] = declared
            main_text_parts: list[str] = []
            note_text_parts: list[str] = []
            for element in root.iter():
                if _local_name(element.tag) != "t":
                    continue
                value = _text(element)
                if under(element, "endNote"):
                    note_text_parts.append(value)
                else:
                    main_text_parts.append(value)
            main_text = " ".join(main_text_parts)
            note_text = " ".join(note_text_parts)
            markers = _SOLUTION_MARKER_RE.findall(main_text)
            total_notes += len(notes)
            total_autonum += len(auto)
            main_chars += len(main_text)
            note_chars += len(note_text)
            marker_count += len(markers)
            section_reports.append(
                {
                    "section": member,
                    "endnotes": len(notes),
                    "endnote_autonum": len(auto),
                    "endnote_placements": placements,
                    "main_text_chars": len(main_text),
                    "endnote_text_chars": len(note_text),
                    "empty_endnote_bodies": len(empty_notes),
                    "native_reference_anchor_count": len(anchored_notes),
                    "main_text_sha256": _sha256_text(main_text),
                    "endnote_text_sha256": _sha256_text(note_text),
                    "main_solution_marker_count": len(markers),
                }
            )
            if empty_notes:
                result["findings"].append(  # type: ignore[union-attr]
                    {
                        "code": "ENDNOTE_BODY_EMPTY",
                        "section": member,
                        "count": len(empty_notes),
                        "message": "one or more native endnotes has an empty body",
                    }
                )
            if len(notes) != len(auto):
                result["findings"].append(  # type: ignore[union-attr]
                    {
                        "code": "ENDNOTE_AUTONUM_MISMATCH",
                        "section": member,
                        "expected": len(notes),
                        "actual": len(auto),
                    }
                )
            if len(anchored_notes) != len(notes):
                result["findings"].append(  # type: ignore[union-attr]
                    {
                        "code": "ENDNOTE_REFERENCE_ANCHOR_MISSING",
                        "section": member,
                        "expected": len(notes),
                        "actual": len(anchored_notes),
                        "message": "one or more native endnote bodies is detached from a main-story anchor paragraph",
                    }
                )
            if markers:
                result["findings"].append(  # type: ignore[union-attr]
                    {
                        "code": "MAIN_BODY_SOLUTION_MARKER",
                        "section": member,
                        "count": len(markers),
                    }
                )
        # Match the canonical app gate: placement is relevant only when the
        # document actually contains native endnotes.  Among those sections,
        # only sections declaring ``endNotePr`` are checked; a missing
        # declaration is reported globally only when no section declares it.
        # This keeps ``footNotePr`` (including EACH_COLUMN) out of the gate.
        if total_notes:
            declared_sections = [
                member
                for member, declared in section_endnote_pr_declared.items()
                if declared
            ]
            if not declared_sections:
                result["findings"].append(  # type: ignore[union-attr]
                    {
                        "code": "ENDNOTE_PLACEMENT_UNDECLARED",
                        "expected": REQUIRED_PLACEMENT,
                        "actual": {},
                    }
                )
            for member in declared_sections:
                placements = section_endnote_placements[member]
                if not placements or any(not value for value in placements):
                    result["findings"].append(  # type: ignore[union-attr]
                        {
                            "code": "ENDNOTE_PLACEMENT_UNDECLARED",
                            "section": member,
                            "expected": REQUIRED_PLACEMENT,
                            "actual": placements,
                        }
                    )
                elif any(value != REQUIRED_PLACEMENT for value in placements):
                    result["findings"].append(  # type: ignore[union-attr]
                        {
                            "code": "ENDNOTE_PLACEMENT_INVALID",
                            "section": member,
                            "expected": REQUIRED_PLACEMENT,
                            "actual": placements,
                        }
                    )
        result["sections"] = section_reports
        result["counts"].update(  # type: ignore[union-attr]
            {
                "endnotes": total_notes,
                "endnote_autonum": total_autonum,
                "main_text_chars": main_chars,
                "endnote_text_chars": note_chars,
                "main_solution_marker_count": marker_count,
                "empty_endnote_bodies": empty_note_count,
                "native_reference_anchor_count": sum(
                    int(section.get("native_reference_anchor_count", 0))
                    for section in section_reports
                ),
            }
        )
        if total_notes == 0:
            result["findings"].append(  # type: ignore[union-attr]
                {"code": "NO_NATIVE_ENDNOTES", "message": "integrated document has no native endnotes"}
            )
    result["status"] = "PASS" if not result["findings"] else "FAIL"
    return result


def audit_package(root: Path) -> dict[str, object]:
    base: dict[str, object] = {
        "schema": AUDIT_SCHEMA,
        "root": str(root),
        "required_subjects": list(REQUIRED_SUBJECTS),
        "subject_count": 0,
        "subjects": {},
        "findings": [],
        "status": "FAIL",
        "release_note": "Structural candidate gate only; COM, visual, and source-fidelity gates remain independent.",
    }
    if not root.is_dir():
        base["findings"] = [{"code": "INVALID_PACKAGE_ROOT", "message": f"not a directory: {root}"}]
        return base
    subjects: dict[str, dict[str, object]] = {}
    directories = sorted(path for path in root.iterdir() if path.is_dir())
    for directory in directories:
        candidates = sorted(directory.glob("*미주*.hwpx"))
        if not candidates:
            continue
        hwpx = candidates[0]
        report = audit_hwpx(hwpx)
        if len(candidates) != 1:
            report["findings"].append(  # type: ignore[union-attr]
                {
                    "code": "AMBIGUOUS_INTEGRATED_HWPX",
                    "message": "expected exactly one integrated HWPX candidate",
                    "count": len(candidates),
                }
            )
        hwp_candidates = sorted(directory.glob("*미주*.hwp"))
        report["paired_hwp"] = {
            "path": str(hwp_candidates[0]) if hwp_candidates else None,
            "exists": bool(hwp_candidates),
            "sha256": hashlib.sha256(hwp_candidates[0].read_bytes()).hexdigest() if hwp_candidates else None,
        }
        if not hwp_candidates:
            report["findings"].append(  # type: ignore[union-attr]
                {"code": "MISSING_PAIRED_HWP", "message": "integrated HWPX has no paired HWP"}
            )
        elif len(hwp_candidates) != 1:
            report["findings"].append(  # type: ignore[union-attr]
                {
                    "code": "AMBIGUOUS_PAIRED_HWP",
                    "message": "expected exactly one paired HWP candidate",
                    "count": len(hwp_candidates),
                }
            )
        subjects[directory.name] = report
    findings: list[dict[str, object]] = []
    for required in REQUIRED_SUBJECTS:
        if required not in subjects:
            findings.append(
                {
                    "code": "MISSING_REQUIRED_SUBJECT",
                    "subject": required,
                    "message": "required HIGH-END subject has no integrated HWPX candidate",
                }
            )
    for extra in sorted(set(subjects) - set(REQUIRED_SUBJECTS)):
        findings.append(
            {
                "code": "UNEXPECTED_SUBJECT",
                "subject": extra,
                "message": "package contains an integrated candidate outside the four-subject contract",
            }
        )
    findings.extend(
        finding
        for report in subjects.values()
        for finding in report.get("findings", [])  # type: ignore[union-attr]
    )
    statuses = [str(report["status"]) for report in subjects.values()]
    result = dict(base)
    result.update(
        {
            "subject_count": len(subjects),
            "subjects": subjects,
            "findings": findings,
            "status": "PASS"
            if len(subjects) == len(REQUIRED_SUBJECTS)
            and set(subjects) == set(REQUIRED_SUBJECTS)
            and statuses
            and all(value == "PASS" for value in statuses)
            and not findings
            else "FAIL",
        }
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, help="package root containing subject directories")
    parser.add_argument("--json", type=Path, required=True)
    args = parser.parse_args()
    report = audit_package(args.root)
    args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
