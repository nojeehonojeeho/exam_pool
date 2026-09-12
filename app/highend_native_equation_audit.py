"""Read-only evidence audit for HIGH-END native-equation count reconciliation.

The HIGH-END reviewed scope records ``equation``/``display_equation`` blocks
as typed formula units, but a ``piecewise_function`` is one reviewed block
whose cases are emitted as one native equation control per case by the
current authoring output.  Comparing the HWPX control count directly with
the typed-unit count therefore produces a misleading shortfall/excess.

This module makes that distinction explicit.  It reads JSON manifests and a
HWPX ZIP package only; it never opens Hanword/COM and never writes any input
document.  The result is an evidence report, not a source-fidelity release
gate: ``status`` is deliberately ``REVIEW_REQUIRED`` even when the expanded
counts reconcile.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
import re
from typing import Any, Iterable
import xml.etree.ElementTree as ET
import zipfile


_EXPLICIT_FORMULA_TYPES = frozenset({"equation", "display_equation"})
_PIECEWISE_TYPE = "piecewise_function"
_ITEM_ID_RE = re.compile(r"^(?P<prefix>.+)-(?P<number>\d+)$")


def _local_name(tag: Any) -> str:
    """Return an XML local name without assuming a particular HWPX URI."""

    return str(tag).rsplit("}", 1)[-1]


def _walk_records(value: Any) -> Iterable[Mapping[str, Any]]:
    """Yield every mapping record in a JSON-like block tree."""

    if isinstance(value, Mapping):
        yield value
        for child in value.values():
            yield from _walk_records(child)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for child in value:
            yield from _walk_records(child)


def _block_counts(value: Any) -> dict[str, int]:
    """Count explicit formula records and piecewise cases in one side."""

    explicit = 0
    piecewise_blocks = 0
    piecewise_cases = 0
    for record in _walk_records(value):
        kind = str(record.get("type", "")).strip().lower()
        if kind in _EXPLICIT_FORMULA_TYPES:
            explicit += 1
        elif kind == _PIECEWISE_TYPE:
            piecewise_blocks += 1
            cases = record.get("cases", [])
            if isinstance(cases, Sequence) and not isinstance(cases, (str, bytes, bytearray)):
                piecewise_cases += len(cases)
    return {
        "explicit_formula_units": explicit,
        "piecewise_blocks": piecewise_blocks,
        "piecewise_cases": piecewise_cases,
        "expanded_native_units": explicit + piecewise_cases,
    }


def _rows_by_id(
    payload: Mapping[str, Any], *, field: str
) -> tuple[list[str], dict[str, Mapping[str, Any]], list[dict[str, Any]]]:
    """Index item rows while preserving order and reporting malformed IDs."""

    rows = payload.get(field, [])
    if not isinstance(rows, Sequence) or isinstance(rows, (str, bytes, bytearray)):
        return [], {}, [{"code": "ITEM_LIST_INVALID", "field": field}]
    ordered: list[str] = []
    indexed: dict[str, Mapping[str, Any]] = {}
    findings: list[dict[str, Any]] = []
    for index, row in enumerate(rows, 1):
        if not isinstance(row, Mapping):
            findings.append({"code": "ITEM_RECORD_INVALID", "field": field, "position": index})
            continue
        item_id = str(row.get("item_id", "")).strip()
        if not item_id:
            findings.append({"code": "ITEM_ID_MISSING", "field": field, "position": index})
            continue
        ordered.append(item_id)
        if item_id in indexed:
            findings.append({"code": "ITEM_ID_DUPLICATE", "field": field, "item_id": item_id})
        else:
            indexed[item_id] = row
    return ordered, indexed, findings


def _item_number(item_id: str) -> int | None:
    match = _ITEM_ID_RE.fullmatch(item_id)
    if not match:
        return None
    try:
        return int(match.group("number"))
    except ValueError:
        return None


def _source_side_row(item: Mapping[str, Any], *, side: str) -> dict[str, Any]:
    counts = _block_counts(item.get(f"{side}_blocks", []))
    return {"side": side, **counts}


def _source_counts(
    reviewed_manifest: Mapping[str, Any],
    reviewed_scope_manifest: Mapping[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    """Compute typed and piecewise-expanded source counts per reviewed item."""

    _, detailed, detailed_findings = _rows_by_id(reviewed_manifest, field="items")
    _, scoped, scoped_findings = _rows_by_id(reviewed_scope_manifest, field="items")
    findings = list(detailed_findings) + list(scoped_findings)
    item_rows: list[dict[str, Any]] = []
    for item_id, item in detailed.items():
        problem = _source_side_row(item, side="problem")
        solution = _source_side_row(item, side="solution")
        scope = scoped.get(item_id, {})
        row = {
            "item_id": item_id,
            "problem": problem,
            "solution": solution,
            "review_status": item.get("review_status"),
            "source_page": item.get("source_page"),
            "column": item.get("column"),
            "printed_num": item.get("printed_num"),
            "scope_declared_problem": scope.get("problem_typed_equation_count"),
            "scope_declared_solution": scope.get("solution_typed_equation_count"),
        }
        item_rows.append(row)
        for side, count_key in (
            ("problem", "problem_typed_equation_count"),
            ("solution", "solution_typed_equation_count"),
        ):
            declared = scope.get(count_key)
            computed = (
                problem["explicit_formula_units"]
                if side == "problem"
                else solution["explicit_formula_units"]
            )
            if declared is not None and declared != computed:
                findings.append({
                    "code": "SCOPE_DECLARED_FORMULA_COUNT_MISMATCH",
                    "item_id": item_id,
                    "side": side,
                    "declared": declared,
                    "computed": computed,
                })

    totals = {
        "item_count": len(item_rows),
        "explicit_problem": sum(row["problem"]["explicit_formula_units"] for row in item_rows),
        "explicit_solution": sum(row["solution"]["explicit_formula_units"] for row in item_rows),
        "piecewise_problem_blocks": sum(row["problem"]["piecewise_blocks"] for row in item_rows),
        "piecewise_solution_blocks": sum(row["solution"]["piecewise_blocks"] for row in item_rows),
        "piecewise_problem_cases": sum(row["problem"]["piecewise_cases"] for row in item_rows),
        "piecewise_solution_cases": sum(row["solution"]["piecewise_cases"] for row in item_rows),
    }
    totals["explicit_total"] = totals["explicit_problem"] + totals["explicit_solution"]
    totals["piecewise_case_total"] = totals["piecewise_problem_cases"] + totals["piecewise_solution_cases"]
    totals["expanded_problem"] = totals["explicit_problem"] + totals["piecewise_problem_cases"]
    totals["expanded_solution"] = totals["explicit_solution"] + totals["piecewise_solution_cases"]
    totals["expanded_total"] = totals["expanded_problem"] + totals["expanded_solution"]

    scope_totals = {
        "declared_problem": sum(
            int(row.get("scope_declared_problem"))
            for row in item_rows
            if isinstance(row.get("scope_declared_problem"), int)
        ),
        "declared_solution": sum(
            int(row.get("scope_declared_solution"))
            for row in item_rows
            if isinstance(row.get("scope_declared_solution"), int)
        ),
    }
    scope_totals["declared_total"] = scope_totals["declared_problem"] + scope_totals["declared_solution"]
    return {"totals": totals, "scope_totals": scope_totals}, item_rows, findings


def _section_sort_key(name: str) -> tuple[int, str]:
    match = re.search(r"section(\d+)\.xml$", name, re.IGNORECASE)
    return (int(match.group(1)) if match else 10**9, name)


def _read_hwpx_sections(path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Read equation and endnote counts from HWPX section XML files."""

    sections: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    try:
        package = zipfile.ZipFile(path)
    except (OSError, zipfile.BadZipFile) as exc:
        return [], [{"code": "HWPX_READ_ERROR", "detail": str(exc), "path": str(path)}]

    with package:
        names = sorted(
            (
                name
                for name in package.namelist()
                if re.search(r"(?:^|/)section\d+\.xml$", name, re.IGNORECASE)
            ),
            key=_section_sort_key,
        )
        if not names:
            return [], [{"code": "HWPX_SECTION_MISSING", "path": str(path)}]
        for name in names:
            try:
                root = ET.fromstring(package.read(name))
            except (KeyError, ET.ParseError, OSError, UnicodeError) as exc:
                findings.append({"code": "HWPX_SECTION_INVALID", "section": name, "detail": str(exc)})
                continue
            equations = [element for element in root.iter() if _local_name(element.tag) == "equation"]
            notes = [element for element in root.iter() if _local_name(element.tag) == "endNote"]
            note_descendant_ids = {id(child) for note in notes for child in note.iter()}
            note_equations = [
                sum(1 for child in note.iter() if _local_name(child.tag) == "equation")
                for note in notes
            ]
            current_note = 0
            main_by_note = [0] * len(notes)
            main_before_first_note = 0
            for element in root.iter():
                local = _local_name(element.tag)
                if local == "endNote":
                    current_note += 1
                elif local == "equation" and id(element) not in note_descendant_ids:
                    if current_note == 0:
                        main_before_first_note += 1
                    elif current_note <= len(main_by_note):
                        main_by_note[current_note - 1] += 1
            numbers = [note.attrib.get("number") for note in notes]
            sections.append({
                "section": name,
                "equation_count": len(equations),
                "main_equation_count": len(equations) - sum(note_equations),
                "endnote_equation_count": sum(note_equations),
                "endnote_count": len(notes),
                "endnote_numbers": numbers,
                "endnote_equations": note_equations,
                "main_equations_by_endnote": main_by_note,
                "main_equations_before_first_endnote": main_before_first_note,
            })
    return sections, findings


def audit_hwpx_equations(path: str | Path) -> dict[str, Any]:
    """Return read-only native-equation counts for one HWPX package."""

    source_path = Path(path)
    if not source_path.is_file():
        return {
            "status": "FAIL",
            "path": str(source_path),
            "sections": [],
            "counts": {"equations": 0, "main_equations": 0, "endnote_equations": 0, "endnotes": 0},
            "findings": [{"code": "HWPX_NOT_FOUND", "path": str(source_path)}],
        }
    sections, findings = _read_hwpx_sections(source_path)
    counts = {
        "equations": sum(section["equation_count"] for section in sections),
        "main_equations": sum(section["main_equation_count"] for section in sections),
        "endnote_equations": sum(section["endnote_equation_count"] for section in sections),
        "endnotes": sum(section["endnote_count"] for section in sections),
    }
    return {
        "status": "PASS" if sections and not findings else "FAIL",
        "path": str(source_path),
        "sha256": hashlib.sha256(source_path.read_bytes()).hexdigest(),
        "sections": sections,
        "counts": counts,
        "findings": findings,
    }


def _alignment_audit(
    problem_page_manifest: Mapping[str, Any],
    reviewed_manifest: Mapping[str, Any],
    reviewed_scope_manifest: Mapping[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    page_order, page_rows, page_findings = _rows_by_id(problem_page_manifest, field="items")
    reviewed_order, reviewed_rows, reviewed_findings = _rows_by_id(reviewed_manifest, field="items")
    scope_order, scope_rows, scope_findings = _rows_by_id(reviewed_scope_manifest, field="items")
    findings = page_findings + reviewed_findings + scope_findings
    # The page manifest covers all 103 source questions while the reviewed
    # manifests intentionally cover only the 001--060 subset.  Compare the
    # page order after restricting it to the reviewed IDs; otherwise a valid
    # subset would be misreported as an order mismatch merely because the
    # page inventory contains 43 additional unreviewed items.
    page_scoped_order = [
        item_id
        for item_id in page_order
        if item_id in reviewed_rows and item_id in scope_rows
    ]
    orders = {
        "problem_page_manifest": page_order,
        "problem_page_reviewed_subset": page_scoped_order,
        "reviewed_manifest": reviewed_order,
        "reviewed_scope_manifest": scope_order,
    }
    sequence_exact = page_scoped_order == reviewed_order == scope_order
    if set(page_scoped_order) != set(reviewed_order) or set(reviewed_order) != set(scope_order):
        findings.append({
            "code": "ITEM_SET_MISMATCH",
            "problem_page_reviewed_subset_only": sorted(set(page_scoped_order) - set(reviewed_order)),
            "reviewed_only": sorted(set(reviewed_order) - set(page_scoped_order)),
            "scope_only": sorted(set(scope_order) - set(reviewed_order)),
        })
    if not sequence_exact:
        findings.append({"code": "ITEM_SEQUENCE_MISMATCH", "orders": orders})

    common_ids = [item_id for item_id in reviewed_order if item_id in page_rows and item_id in scope_rows]
    page_mismatches: list[dict[str, Any]] = []
    column_mismatches: list[dict[str, Any]] = []
    for item_id in common_ids:
        page = page_rows[item_id]
        reviewed = reviewed_rows[item_id]
        scope = scope_rows[item_id]
        page_number = page.get("source_pdf_page")
        reviewed_page = reviewed.get("source_page")
        scope_page = scope.get("source_page")
        if page_number != reviewed_page or page_number != scope_page:
            page_mismatches.append({
                "item_id": item_id,
                "problem_page_source_pdf_page": page_number,
                "reviewed_source_page": reviewed_page,
                "scope_source_page": scope_page,
            })
        page_num = page.get("printed_item_number")
        reviewed_num = reviewed.get("printed_num")
        scope_num = scope.get("printed_num")
        if page_num != reviewed_num or page_num != scope_num:
            page_mismatches.append({
                "item_id": item_id,
                "problem_page_printed_item_number": page_num,
                "reviewed_printed_num": reviewed_num,
                "scope_printed_num": scope_num,
            })
        page_column = page.get("source_column")
        reviewed_column = reviewed.get("column")
        scope_column = scope.get("column")
        if page_column != reviewed_column or page_column != scope_column:
            column_mismatches.append({
                "item_id": item_id,
                "problem_page_source_column": page_column,
                "reviewed_column": reviewed_column,
                "scope_column": scope_column,
                "source_pdf_page": page_number,
                "printed_item_number": page_num,
            })

    if page_mismatches:
        findings.extend({"code": "ITEM_PAGE_OR_NUMBER_MISMATCH", **mismatch} for mismatch in page_mismatches)
    if column_mismatches:
        findings.extend({"code": "ITEM_COLUMN_MISMATCH", **mismatch} for mismatch in column_mismatches)

    return {
        "sequence_exact": sequence_exact,
        "orders": orders,
        "page_or_number_mismatches": page_mismatches,
        "column_mismatches": column_mismatches,
        "common_item_count": len(common_ids),
        "m2_p_027": next(
            (
                mismatch
                for mismatch in column_mismatches
                if mismatch["item_id"] == "M2-P-027"
            ),
            None,
        ),
    }, findings


def audit_highend_math2(
    problem_page_manifest: Mapping[str, Any],
    reviewed_manifest: Mapping[str, Any],
    reviewed_scope_manifest: Mapping[str, Any],
    hwpx_path: str | Path,
) -> dict[str, Any]:
    """Reconcile source typed units, piecewise expansion, and HWPX controls.

    ``status`` is never ``PASS``: this report intentionally cannot certify
    source fidelity.  A successful structural comparison is exposed through
    individual gates and a ``REVIEW_REQUIRED`` report remains the only
    release-safe result.
    """

    manifests = (problem_page_manifest, reviewed_manifest, reviewed_scope_manifest)
    if not all(isinstance(payload, Mapping) for payload in manifests):
        return {
            "status": "FAIL",
            "release_status": "REVIEW_REQUIRED",
            "source_fidelity_release_pass": False,
            "findings": [{"code": "MANIFEST_NOT_OBJECT"}],
        }

    source, item_rows, source_findings = _source_counts(reviewed_manifest, reviewed_scope_manifest)
    alignment, alignment_findings = _alignment_audit(
        problem_page_manifest, reviewed_manifest, reviewed_scope_manifest
    )
    output = audit_hwpx_equations(hwpx_path)
    output_counts = output.get("counts", {})
    findings = list(source_findings) + list(alignment_findings) + list(output.get("findings", []))

    expected_problem = [
        row["problem"]["expanded_native_units"] for row in item_rows
    ]
    expected_solution = [
        row["solution"]["expanded_native_units"] for row in item_rows
    ]
    output_sections = output.get("sections", [])
    actual_problem: list[int] = []
    actual_solution: list[int] = []
    for section in output_sections:
        actual_problem.extend(section.get("main_equations_by_endnote", []))
        actual_solution.extend(section.get("endnote_equations", []))
    per_item_lengths_match = (
        len(actual_problem)
        == len(expected_problem)
        == len(actual_solution)
        == len(expected_solution)
    )
    per_item_problem_exact = per_item_lengths_match and actual_problem == expected_problem
    per_item_solution_exact = per_item_lengths_match and actual_solution == expected_solution

    explicit_total_exact = output_counts.get("equations") == source["totals"]["explicit_total"]
    expanded_total_exact = output_counts.get("equations") == source["totals"]["expanded_total"]
    if not explicit_total_exact:
        findings.append({
            "code": "OUTPUT_VS_EXPLICIT_SOURCE_COUNT_DIFFERENCE",
            "source_explicit_total": source["totals"]["explicit_total"],
            "output_native_total": output_counts.get("equations"),
            "delta": (output_counts.get("equations") or 0) - source["totals"]["explicit_total"],
            "piecewise_case_total": source["totals"]["piecewise_case_total"],
        })
    if expanded_total_exact:
        findings.append({
            "code": "COUNT_DELTA_EXPLAINED_BY_PIECEWISE_CASES",
            "delta_vs_explicit_source": (output_counts.get("equations") or 0)
            - source["totals"]["explicit_total"],
            "piecewise_case_total": source["totals"]["piecewise_case_total"],
        })
    if not per_item_problem_exact or not per_item_solution_exact:
        findings.append({
            "code": "OUTPUT_PER_ITEM_NATIVE_COUNT_MISMATCH",
            "problem_expected": expected_problem,
            "problem_actual": actual_problem,
            "solution_expected": expected_solution,
            "solution_actual": actual_solution,
        })

    scope = reviewed_scope_manifest
    scope_validations = scope.get("validations", {})
    scope_source_order = (
        scope_validations.get("source_order", {})
        if isinstance(scope_validations, Mapping)
        else {}
    )
    source_release_ready = bool(
        str(problem_page_manifest.get("status", "")).upper() == "VERIFIED"
        and str(reviewed_manifest.get("review_status", "")).upper() == "VERIFIED"
        and bool(scope.get("strict_pass"))
        and bool(scope.get("full_book_pass_claimed"))
        and not scope_source_order.get("mismatches")
    )
    if not source_release_ready:
        findings.append({
            "code": "SOURCE_MANIFEST_NOT_RELEASE_READY",
            "problem_page_status": problem_page_manifest.get("status"),
            "reviewed_status": reviewed_manifest.get("review_status"),
            "scope_strict_pass": scope.get("strict_pass"),
            "scope_full_book_pass_claimed": scope.get("full_book_pass_claimed"),
        })

    report = {
        "schema": "highend-native-equation-audit-v1",
        "status": "REVIEW_REQUIRED",
        "release_status": "REVIEW_REQUIRED",
        "source_fidelity_release_pass": False,
        "read_only": True,
        "com_used": False,
        "source": {
            **source,
            "items": item_rows,
        },
        "alignment": alignment,
        "output": output,
        "counts": {
            "source_explicit_total": source["totals"]["explicit_total"],
            "source_piecewise_case_total": source["totals"]["piecewise_case_total"],
            "source_expanded_expected_total": source["totals"]["expanded_total"],
            "output_native_equation_total": output_counts.get("equations", 0),
            "output_main_equations": output_counts.get("main_equations", 0),
            "output_endnote_equations": output_counts.get("endnote_equations", 0),
            "output_endnotes": output_counts.get("endnotes", 0),
            "delta_vs_explicit_source": (output_counts.get("equations") or 0)
            - source["totals"]["explicit_total"],
            "delta_vs_expanded_expected": (output_counts.get("equations") or 0)
            - source["totals"]["expanded_total"],
        },
        "gates": {
            "source_explicit_count_matches_output": explicit_total_exact,
            "source_piecewise_expanded_count_matches_output": expanded_total_exact,
            "problem_per_item_expanded_count_exact": per_item_problem_exact,
            "solution_per_item_expanded_count_exact": per_item_solution_exact,
            "item_sequence_exact": alignment["sequence_exact"],
            "item_page_and_number_exact": not alignment["page_or_number_mismatches"],
            "item_column_exact": not alignment["column_mismatches"],
            "source_manifest_release_ready": source_release_ready,
            "source_fidelity_release_pass": False,
        },
        "findings": findings,
    }
    return report


def load_and_audit(
    problem_page_manifest: str | Path,
    reviewed_manifest: str | Path,
    reviewed_scope_manifest: str | Path,
    hwpx_path: str | Path,
) -> dict[str, Any]:
    """Load four read-only inputs and return :func:`audit_highend_math2`."""

    paths = [Path(problem_page_manifest), Path(reviewed_manifest), Path(reviewed_scope_manifest)]
    try:
        payloads = [json.loads(path.read_text(encoding="utf-8")) for path in paths]
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return {
            "status": "FAIL",
            "release_status": "REVIEW_REQUIRED",
            "source_fidelity_release_pass": False,
            "findings": [{"code": "MANIFEST_READ_ERROR", "detail": str(exc)}],
        }
    return audit_highend_math2(*payloads, hwpx_path)


__all__ = ["audit_highend_math2", "audit_hwpx_equations", "load_and_audit"]
