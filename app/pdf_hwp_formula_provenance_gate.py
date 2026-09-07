"""Fail-closed source provenance checks for native mathematical equations.

``audit_authoring_items`` deliberately checks the writer-facing syntax only.
This module checks the separate evidence chain that must exist before a
strict PDF -> HWP/HWPX build is allowed to start:

    source PDF occurrence -> item/reading order -> MathIR -> HWP dialect

The gate never treats a matching formula count, a VERIFIED item label, or a
successful HWP reopen as proof of source fidelity.  It returns raw findings
without collapsing them; root-cause grouping is a later diagnostic layer.
No copyrighted source material is copied into this module or its tests.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any, Iterator


FORMULA_KINDS = frozenset({"equation", "inline_equation", "display_equation", "piecewise_function"})
_SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")


def _sha256_text(value: Any) -> str:
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()


def _is_bbox(value: Any) -> bool:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)) or len(value) != 4:
        return False
    try:
        x0, y0, x1, y1 = (float(x) for x in value)
    except (TypeError, ValueError):
        return False
    return x1 > x0 and y1 > y0 and min(x0, y0) >= 0


def _first(record: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        value = record.get(key)
        if value is not None and value != "":
            return value
    return None


def _walk(value: Any, path: str = "") -> Iterator[tuple[str, Mapping[str, Any]]]:
    if isinstance(value, Mapping):
        yield path, value
        for key, child in value.items():
            yield from _walk(child, f"{path}/{key}")
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for index, child in enumerate(value):
            yield from _walk(child, f"{path}/{index}")


def _is_formula_record(record: Mapping[str, Any], path: str) -> bool:
    kind = str(record.get("type", "")).strip().lower()
    if kind in FORMULA_KINDS or record.get("formula_occurrence_id"):
        return True
    # Flat occurrence ledgers sometimes omit ``type`` but use a formula path.
    if "source_text_sha256" in record and ("script" in record or "source" in record):
        return "formula" in path.lower() or bool(record.get("role"))
    return False


def _formula_source(record: Mapping[str, Any]) -> str:
    value = _first(record, "source_script", "script", "source", "reviewed_source", "formula_source")
    return str(value).strip() if value is not None else ""


def _evidence(record: Mapping[str, Any]) -> Mapping[str, Any] | None:
    for key in ("source_evidence", "formula_source_evidence", "evidence"):
        value = record.get(key)
        if isinstance(value, Mapping):
            return value
    # A normalized occurrence ledger may keep evidence columns at the record
    # level.  Project them into the same contract without modifying input.
    keys = {"pdf_page", "page", "source_page", "bbox_pt", "bbox", "source_bbox", "source_crop_sha256", "crop_sha256", "dpi", "render_dpi"}
    if any(key in record for key in keys):
        return {key: record.get(key) for key in keys if key in record}
    return None


def _iter_formula_records(manifest: Mapping[str, Any]) -> Iterator[tuple[str, Mapping[str, Any], str | None]]:
    """Yield each formula once, carrying the nearest item owner."""

    seen: set[int] = set()
    items = manifest.get("items")
    if isinstance(items, Sequence) and not isinstance(items, (str, bytes)):
        for item_index, item in enumerate(items):
            if not isinstance(item, Mapping):
                continue
            item_id = str(item.get("item_id", "")).strip() or None
            for role in ("problem_blocks", "solution_blocks"):
                blocks = item.get(role)
                if not isinstance(blocks, Sequence) or isinstance(blocks, (str, bytes)):
                    continue
                for path, record in _walk(blocks, f"/items/{item_index}/{role}"):
                    if _is_formula_record(record, path) and id(record) not in seen:
                        seen.add(id(record))
                        yield path, record, item_id
    # Candidate manifests also carry a flat formula-occurrence ledger.  It may
    # be separate from typed blocks, so it must be audited as well.
    for key in ("formula_occurrences", "formulas", "formula_ledger"):
        values = manifest.get(key)
        if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
            continue
        for index, record in enumerate(values):
            if isinstance(record, Mapping) and _is_formula_record(record, f"/{key}/{index}") and id(record) not in seen:
                seen.add(id(record))
                item_id = str(record.get("item_id", "")).strip() or None
                yield f"/{key}/{index}", record, item_id


def _finding(code: str, path: str, item_id: str | None, occurrence_id: str | None, **extra: Any) -> dict[str, Any]:
    result: dict[str, Any] = {
        "code": code,
        "stage": "source-evidence",
        "evidence_key": occurrence_id or path,
        "path": path,
    }
    if item_id:
        result["item_id"] = item_id
    if occurrence_id:
        result["formula_occurrence_id"] = occurrence_id
    result.update(extra)
    return result


def audit_formula_provenance(manifest: Mapping[str, Any], *, require_source_evidence: bool = True) -> dict[str, Any]:
    """Audit source evidence for every native formula in a manifest.

    ``require_source_evidence=False`` is available for legacy diagnostics, but
    the production strict builder must call this with ``True``.  A complete
    record needs a stable occurrence id, an owning item and source order,
    verified 600/900dpi evidence (page, bbox, crop hash, PDF hash), a
    source-backed MathIR hash, and a writer-facing dialect/script.
    """

    if not isinstance(manifest, Mapping):
        return {"status": "FAIL", "passed": False, "counts": {"formula_occurrences": 0, "findings": 1}, "findings": [{"code": "MANIFEST_NOT_OBJECT"}]}
    if not require_source_evidence:
        return {"status": "DIAGNOSTIC_ONLY", "passed": False, "counts": {"formula_occurrences": 0, "findings": 0}, "findings": []}

    findings: list[dict[str, Any]] = []
    records = list(_iter_formula_records(manifest))
    seen_ids: Counter[str] = Counter()
    root_pdf_hash = str(_first(manifest, "source_pdf_sha256", "source_sha256") or "").lower()
    if root_pdf_hash and not _SHA256.fullmatch(root_pdf_hash):
        findings.append(_finding("SOURCE_PDF_HASH_INVALID", "/source_pdf_sha256", None, None, source_hash=root_pdf_hash))

    for path, record, owner_item_id in records:
        occurrence_id = str(_first(record, "formula_occurrence_id", "source_occurrence_id", "source_formula_id", "id") or "").strip() or None
        if occurrence_id:
            seen_ids[occurrence_id] += 1
        else:
            findings.append(_finding("FORMULA_OCCURRENCE_ID_MISSING", path, owner_item_id, None))
        item_id = owner_item_id or str(record.get("item_id", "")).strip() or None
        if not item_id:
            findings.append(_finding("FORMULA_ITEM_OWNER_MISSING", path, None, occurrence_id))
        order = _first(record, "source_order", "ordinal", "occurrence_order", "order")
        if not isinstance(order, int) or order < 1:
            findings.append(_finding("FORMULA_ORDER_MISSING", path, item_id, occurrence_id))

        source = _formula_source(record)
        source_digest = str(_first(record, "source_text_sha256", "formula_source_sha256") or _sha256_text(source)).lower()
        if not source:
            findings.append(_finding("FORMULA_SOURCE_EMPTY", path, item_id, occurrence_id))
        if not _SHA256.fullmatch(source_digest) or (source and source_digest != _sha256_text(source)):
            findings.append(_finding("FORMULA_SOURCE_HASH_MISMATCH", path, item_id, occurrence_id, expected=_sha256_text(source), actual=source_digest))

        if record.get("source_pdf_verified") is not True:
            findings.append(_finding("FORMULA_SOURCE_EVIDENCE_UNVERIFIED", path, item_id, occurrence_id))
        ev = _evidence(record)
        if ev is None:
            findings.append(_finding("FORMULA_SOURCE_EVIDENCE_MISSING", path, item_id, occurrence_id))
        else:
            page = _first(ev, "pdf_page", "page", "source_page")
            if not isinstance(page, int) or page < 1:
                findings.append(_finding("FORMULA_SOURCE_PAGE_MISSING", path, item_id, occurrence_id))
            bbox = _first(ev, "bbox_pt", "bbox", "source_bbox")
            if not _is_bbox(bbox):
                findings.append(_finding("FORMULA_SOURCE_BBOX_MISSING", path, item_id, occurrence_id))
            crop_hash = str(_first(ev, "source_crop_sha256", "crop_sha256", "source_crop_hash") or "").lower()
            if not _SHA256.fullmatch(crop_hash):
                findings.append(_finding("FORMULA_SOURCE_CROP_HASH_MISSING", path, item_id, occurrence_id))
            dpi = _first(ev, "dpi", "render_dpi", "review_dpi")
            if dpi not in (600, 900):
                findings.append(_finding("FORMULA_SOURCE_DPI_INVALID", path, item_id, occurrence_id, dpi=dpi))
            pdf_hash = str(_first(record, "source_pdf_sha256", "source_pdf_hash") or _first(ev, "source_pdf_sha256", "source_pdf_hash") or root_pdf_hash).lower()
            if not _SHA256.fullmatch(pdf_hash):
                findings.append(_finding("FORMULA_SOURCE_PDF_HASH_MISSING", path, item_id, occurrence_id))
            elif root_pdf_hash and pdf_hash != root_pdf_hash:
                findings.append(_finding("FORMULA_SOURCE_PDF_HASH_MISMATCH", path, item_id, occurrence_id, expected=root_pdf_hash, actual=pdf_hash))
            status = str(_first(ev, "review_status", "evidence_status", "status") or record.get("evidence_status", "")).upper()
            if status and status not in {"VERIFIED", "SOURCE_REVIEWED_600_AND_900"}:
                findings.append(_finding("FORMULA_SOURCE_EVIDENCE_UNVERIFIED", path, item_id, occurrence_id, status=status))

        mathir = record.get("mathir")
        if not isinstance(mathir, Mapping) or not mathir:
            findings.append(_finding("MATHIR_MISSING", path, item_id, occurrence_id))
        else:
            mathir_hash = str(mathir.get("source_sha256", "")).lower()
            if mathir_hash != source_digest:
                findings.append(_finding("MATHIR_SOURCE_HASH_MISMATCH", path, item_id, occurrence_id, expected=source_digest, actual=mathir_hash))

        script = _first(record, "dialect_script", "hwp_script", "script", "source_script")
        language = _first(record, "script_language", "dialect", "hwp_dialect")
        if not isinstance(script, str) or not script.strip() or not isinstance(language, str) or not language.strip():
            findings.append(_finding("DIALECT_REQUIRED", path, item_id, occurrence_id))
        elif str(record.get("dialect_status", "")).upper() in {"DIALECT_REQUIRED", "UNVERIFIED", "REVIEW_REQUIRED"}:
            findings.append(_finding("DIALECT_UNVERIFIED", path, item_id, occurrence_id, status=record.get("dialect_status")))

    for occurrence_id, count in seen_ids.items():
        if count > 1:
            findings.append(_finding("FORMULA_OCCURRENCE_ID_DUPLICATE", "", None, occurrence_id, count=count))

    counts = {
        "formula_occurrences": len(records),
        "findings": len(findings),
        "source_verified": sum(1 for _, record, _ in records if record.get("source_pdf_verified") is True),
        "mathir_present": sum(1 for _, record, _ in records if isinstance(record.get("mathir"), Mapping) and bool(record.get("mathir"))),
    }
    return {
        "status": "PASS" if not findings and records else "FAIL",
        "passed": bool(records) and not findings,
        "check_scope": "strict_formula_source_provenance_only",
        "counts": counts,
        "findings": findings,
        "formula_occurrences": [{"path": path, "item_id": item_id, "formula_occurrence_id": _first(record, "formula_occurrence_id", "source_occurrence_id", "source_formula_id", "id")} for path, record, item_id in records],
    }


__all__ = ["audit_formula_provenance"]
