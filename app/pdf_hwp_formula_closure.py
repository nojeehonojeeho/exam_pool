"""Build a conservative source-to-authoring formula closure ledger.

This module joins two *already reviewed* inputs without inventing source
evidence:

``reviewed source manifest -> exact occurrence key -> authoring MathIR/dialect``

The source manifest remains authoritative.  A formula is closed only when an
explicit occurrence id matches, or when a unique composite key
``item_id + source_order + source_text_sha256`` matches exactly.  Text
similarity, page proximity, list position alone, or an existing VERIFIED
label never closes a formula.  Missing or ambiguous links stay
``REVIEW_REQUIRED``/``candidate_only`` and are emitted as findings.

The output is intentionally compatible with
``app.pdf_hwp_formula_provenance_gate.audit_formula_provenance``: a closed
ledger can be passed to that gate, while an open ledger is useful as a work
queue and cannot be promoted by this module.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from collections.abc import Mapping, Sequence
from typing import Any, Iterable

from .math_source_manifest import SCHEMA_VERSION, validate_source_manifest
from .pdf_hwp_formula_provenance_gate import audit_formula_provenance


_SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")
_FORMULA_KINDS = frozenset({"equation", "inline_equation", "display_equation", "piecewise_function"})
_BLOCK_KEYS = ("formulas", "formula_occurrences", "formula_ledger", "problem_formulas", "solution_formulas")
_ROLE_KEYS = ("problem_blocks", "solution_blocks")


def _sha256_text(value: Any) -> str:
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()


def _is_sha256(value: Any) -> bool:
    return bool(_SHA256.fullmatch(str(value or "")))


def _first(record: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        value = record.get(key)
        if value is not None and value != "":
            return value
    return None


def _walk(value: Any, path: str = "") -> Iterable[tuple[str, Mapping[str, Any]]]:
    if isinstance(value, Mapping):
        yield path, value
        for key, child in value.items():
            yield from _walk(child, f"{path}/{key}")
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for index, child in enumerate(value):
            yield from _walk(child, f"{path}/{index}")


def _is_formula(record: Mapping[str, Any], path: str) -> bool:
    kind = str(record.get("type", "")).strip().lower()
    if kind in _FORMULA_KINDS:
        return True
    if any(key in record for key in ("formula_occurrence_id", "source_occurrence_id", "source_formula_id")):
        return True
    if isinstance(record.get("mathir"), Mapping):
        return True
    return "formula" in path.lower() and any(key in record for key in ("source", "script", "source_script"))


def _formula_source(record: Mapping[str, Any]) -> str:
    value = _first(record, "source", "reviewed_source", "formula_source", "source_script", "script")
    return str(value).strip() if value is not None else ""


def _source_hash(record: Mapping[str, Any], source: str) -> str:
    value = str(_first(record, "source_text_sha256", "formula_source_sha256") or "").lower()
    return value if _is_sha256(value) else (_sha256_text(source) if source else "")


def _item_id(record: Mapping[str, Any], item: Mapping[str, Any] | None) -> str | None:
    value = _first(record, "item_id", "source_item_id")
    if value is None and item is not None:
        value = _first(item, "item_id", "source_item_id")
    return str(value).strip() if value is not None and str(value).strip() else None


def _order(record: Mapping[str, Any]) -> int | None:
    value = _first(record, "source_order", "ordinal", "occurrence_order", "order")
    return value if isinstance(value, int) and value >= 1 else None


def _evidence(record: Mapping[str, Any], item: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Return formula evidence without fabricating formula geometry.

    Item-level evidence may contribute only page/PDF-level context.  Formula
    bbox and crop are never inherited from an item or page because that would
    make a whole-item crop look like proof for an individual equation.
    """

    nested = None
    for key in ("source_evidence", "formula_source_evidence", "evidence"):
        if isinstance(record.get(key), Mapping):
            nested = dict(record[key])
            break
    nested = nested or {}
    item_nested: Mapping[str, Any] = {}
    if isinstance(item, Mapping):
        for key in ("source_evidence", "evidence"):
            if isinstance(item.get(key), Mapping):
                item_nested = item[key]
                break
    result: dict[str, Any] = {}
    for key in ("pdf_page", "page", "source_page", "source_pdf_sha256", "source_pdf_hash"):
        value = _first(nested, key)
        if value is None:
            value = _first(record, key)
        if value is None:
            value = _first(item_nested, key)
        if value is not None:
            result[key] = value
    # These must be formula-specific.  Do not fall back to item evidence.
    for key in ("bbox_pt", "bbox", "source_bbox", "source_crop_sha256", "crop_sha256", "source_crop_hash", "dpi", "render_dpi", "review_dpi", "review_status", "evidence_status", "status"):
        value = _first(nested, key)
        if value is None:
            value = _first(record, key)
        if value is not None:
            result[key] = value
    return result


def _source_rows(manifest: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[int] = set()

    def add(record: Mapping[str, Any], item: Mapping[str, Any] | None, page: Mapping[str, Any] | None, path: str) -> None:
        if id(record) in seen:
            return
        seen.add(id(record))
        if not _is_formula(record, path):
            return
        ev = _evidence(record, item)
        if page:
            # Page context is safe for page/PDF identity, not formula bounds.
            ev.setdefault("pdf_page", _first(page, "pdf_page", "page"))
            ev.setdefault("source_pdf_sha256", _first(page, "source_pdf_sha256", "source_pdf_hash"))
        rows.append({"record": record, "item": item or {}, "page": page or {}, "path": path, "evidence": ev})

    pages = manifest.get("pages")
    if isinstance(pages, Sequence) and not isinstance(pages, (str, bytes)):
        for page_index, page in enumerate(pages):
            if not isinstance(page, Mapping):
                continue
            items = page.get("items")
            if not isinstance(items, Sequence) or isinstance(items, (str, bytes)):
                continue
            for item_index, item in enumerate(items):
                if not isinstance(item, Mapping):
                    continue
                for key in _BLOCK_KEYS:
                    values = item.get(key)
                    if isinstance(values, Sequence) and not isinstance(values, (str, bytes)):
                        for index, record in enumerate(values):
                            if isinstance(record, Mapping):
                                add(record, item, page, f"/pages/{page_index}/items/{item_index}/{key}/{index}")

    items = manifest.get("items")
    if isinstance(items, Sequence) and not isinstance(items, (str, bytes)):
        for item_index, item in enumerate(items):
            if not isinstance(item, Mapping):
                continue
            for key in _BLOCK_KEYS + _ROLE_KEYS:
                values = item.get(key)
                if isinstance(values, Sequence) and not isinstance(values, (str, bytes)):
                    for path, record in _walk(values, f"/items/{item_index}/{key}"):
                        if _is_formula(record, path):
                            add(record, item, None, path)

    for key in _BLOCK_KEYS:
        values = manifest.get(key)
        if isinstance(values, Sequence) and not isinstance(values, (str, bytes)):
            for index, record in enumerate(values):
                if isinstance(record, Mapping):
                    add(record, None, None, f"/{key}/{index}")
    return rows


def _authoring_rows(manifest: Mapping[str, Any]) -> list[dict[str, Any]]:
    # Authoring input is intentionally parsed separately from the source
    # parser so a source record cannot accidentally serve as its own match.
    rows: list[dict[str, Any]] = []
    seen: set[int] = set()
    items = manifest.get("items")
    if isinstance(items, Sequence) and not isinstance(items, (str, bytes)):
        for item_index, item in enumerate(items):
            if not isinstance(item, Mapping):
                continue
            item_id = _item_id(item, None)
            for key in _BLOCK_KEYS + _ROLE_KEYS:
                values = item.get(key)
                if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
                    continue
                for path, record in _walk(values, f"/items/{item_index}/{key}"):
                    if id(record) in seen or not _is_formula(record, path):
                        continue
                    seen.add(id(record))
                    rows.append({"record": record, "item": item, "path": path, "item_id": item_id})
    for key in _BLOCK_KEYS:
        values = manifest.get(key)
        if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
            continue
        for index, record in enumerate(values):
            if isinstance(record, Mapping) and id(record) not in seen and _is_formula(record, f"/{key}/{index}"):
                seen.add(id(record))
                rows.append({"record": record, "item": {}, "path": f"/{key}/{index}", "item_id": _item_id(record, None)})
    return rows


def _source_verified(source_manifest: Mapping[str, Any], row: Mapping[str, Any], source_hash: str) -> bool:
    if str(source_manifest.get("status", "")).upper() != "VERIFIED":
        return False
    if source_manifest.get("uncertainties") not in (None, []):
        return False
    if not _is_sha256(str(source_manifest.get("source_pdf_sha256", "")).lower()):
        return False
    record = row["record"]
    item = row["item"]
    page = row["page"]
    ev = row["evidence"]
    statuses = (record, item, page, ev)
    if any(str(value.get("status", value.get("review_status", ""))).upper() in {"DRAFT", "UNREVIEWED", "BLOCKED", "REVIEW_REQUIRED"} for value in statuses if isinstance(value, Mapping)):
        return False
    if str(page.get("status", "VERIFIED")).upper() != "VERIFIED":
        return False
    if str(record.get("review_status", record.get("status", ""))).upper() != "VERIFIED":
        return False
    if not source_hash or not _is_sha256(source_hash):
        return False
    if not _is_sha256(str(ev.get("source_crop_sha256", ev.get("crop_sha256", ""))).lower()):
        return False
    bbox = ev.get("bbox_pt", ev.get("bbox", ev.get("source_bbox")))
    if not isinstance(bbox, Sequence) or isinstance(bbox, (str, bytes)) or len(bbox) != 4:
        return False
    try:
        nums = [float(value) for value in bbox]
    except (TypeError, ValueError):
        return False
    if not (nums[2] > nums[0] and nums[3] > nums[1] and min(nums) >= 0):
        return False
    if ev.get("dpi", ev.get("render_dpi", ev.get("review_dpi"))) not in (600, 900):
        return False
    return True


def _normalize_source(row: Mapping[str, Any], root_pdf_hash: str) -> dict[str, Any]:
    record = row["record"]
    item = row["item"]
    ev = dict(row["evidence"])
    source = _formula_source(record)
    digest = _source_hash(record, source)
    item_id = _item_id(record, item)
    order = _order(record)
    explicit_id = str(_first(record, "formula_occurrence_id", "source_occurrence_id", "source_formula_id") or "").strip() or None
    derived_id = explicit_id or (f"{item_id}:F{order:03d}" if item_id and order is not None else None)
    pdf_hash = str(_first(record, "source_pdf_sha256", "source_pdf_hash") or _first(ev, "source_pdf_sha256", "source_pdf_hash") or root_pdf_hash or "").lower()
    return {
        "type": str(record.get("type", "equation")),
        "formula_occurrence_id": derived_id,
        "source_occurrence_id": explicit_id,
        "item_id": item_id,
        "source_order": order,
        "source": source,
        "source_text_sha256": digest,
        "source_pdf_sha256": pdf_hash,
        "source_evidence": ev,
        "source_pdf_verified": False,
        "source_review_status": str(record.get("review_status", record.get("status", ""))).upper() or None,
        "source_path": row["path"],
    }


def _normalize_authoring(row: Mapping[str, Any]) -> dict[str, Any]:
    record = row["record"]
    source = _formula_source(record)
    digest = str(_first(record, "source_text_sha256", "formula_source_sha256") or (_sha256_text(source) if source else "")).lower()
    mathir = record.get("mathir")
    return {
        "formula_occurrence_id": str(_first(record, "formula_occurrence_id", "source_occurrence_id", "source_formula_id") or "").strip() or None,
        "item_id": _item_id(record, row.get("item")),
        "source_order": _order(record),
        "source": source,
        "source_text_sha256": digest,
        "mathir": dict(mathir) if isinstance(mathir, Mapping) else None,
        "script": _first(record, "dialect_script", "hwp_script", "script", "source_script"),
        "script_language": _first(record, "script_language", "dialect", "hwp_dialect"),
        "record": record,
        "path": row["path"],
    }


def _link_key(row: Mapping[str, Any]) -> tuple[str | None, int | None, str | None]:
    return row.get("item_id"), row.get("source_order"), row.get("source_text_sha256")


def _finding(code: str, source: Mapping[str, Any], **extra: Any) -> dict[str, Any]:
    result = {
        "code": code,
        "stage": "formula-closure",
        "item_id": source.get("item_id"),
        "formula_occurrence_id": source.get("formula_occurrence_id"),
        "source_path": source.get("source_path"),
    }
    result.update({key: value for key, value in extra.items() if value is not None})
    return result


def build_formula_closure(reviewed_manifest: Mapping[str, Any], authoring_manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Join reviewed source formulas with authoring MathIR/dialect records.

    This function never mutates either input.  It returns ``PASS`` only when
    every source formula has a unique exact link and the generated ledger also
    passes the strict provenance gate.  All other results are explicit
    ``REVIEW_REQUIRED`` and ``candidate_only``.
    """

    if not isinstance(reviewed_manifest, Mapping) or not isinstance(authoring_manifest, Mapping):
        return {
            "schema_version": "formula-closure-v1",
            "status": "REVIEW_REQUIRED",
            "release_status": "REVIEW_REQUIRED",
            "candidate_only": True,
            "counts": {"source_formula_occurrences": 0, "authoring_formula_occurrences": 0, "raw_finding_count": 1},
            "findings": [{"code": "MANIFEST_NOT_OBJECT", "stage": "formula-closure"}],
            "formula_occurrences": [],
        }

    source_rows = _source_rows(reviewed_manifest)
    authoring_rows = _authoring_rows(authoring_manifest)
    sources = [_normalize_source(row, str(reviewed_manifest.get("source_pdf_sha256", "")).lower()) for row in source_rows]
    authors = [_normalize_authoring(row) for row in authoring_rows]
    findings: list[dict[str, Any]] = []

    by_id: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    by_key: defaultdict[tuple[str | None, int | None, str | None], list[dict[str, Any]]] = defaultdict(list)
    for author in authors:
        if author.get("formula_occurrence_id"):
            by_id[str(author["formula_occurrence_id"])].append(author)
        by_key[_link_key(author)].append(author)

    ledger: list[dict[str, Any]] = []
    matched_author_paths: set[str] = set()
    for source in sources:
        source_id = source.get("formula_occurrence_id")
        source_key = _link_key(source)
        candidates: list[dict[str, Any]] = []
        match_method = None
        if source.get("source_occurrence_id"):
            candidates = by_id.get(str(source_id), [])
            match_method = "explicit_occurrence_id"
            if not candidates:
                # Once the source side carries an explicit occurrence ID,
                # authoring must carry the same ID.  A composite fallback
                # would conceal a source/authoring identity mismatch.
                composite_candidates = by_key.get(source_key, [])
                if composite_candidates:
                    findings.append(_finding("FORMULA_AUTHORING_OCCURRENCE_ID_MISMATCH", source, expected=source_id, actual=[candidate.get("formula_occurrence_id") for candidate in composite_candidates]))
        elif all(value is not None for value in source_key):
            candidates = by_key.get(source_key, [])
            match_method = "exact_composite_key"
        if not candidates:
            findings.append(_finding("FORMULA_AUTHORING_LINK_MISSING", source, expected_key=source_key))
        elif len(candidates) > 1:
            findings.append(_finding("FORMULA_AUTHORING_LINK_AMBIGUOUS", source, match_method=match_method, candidate_count=len(candidates)))
            candidates = []
        author = candidates[0] if candidates else None
        if author:
            matched_author_paths.add(str(author.get("path")))
        closed = True
        if author is None:
            closed = False
        else:
            if author.get("item_id") != source.get("item_id") or author.get("source_order") != source.get("source_order"):
                findings.append(_finding("FORMULA_AUTHORING_ANCHOR_MISMATCH", source, author_path=author.get("path")))
                closed = False
            if author.get("source_text_sha256") != source.get("source_text_sha256"):
                findings.append(_finding("FORMULA_AUTHORING_SOURCE_HASH_MISMATCH", source, expected=source.get("source_text_sha256"), actual=author.get("source_text_sha256")))
                closed = False
            mathir = author.get("mathir")
            if not isinstance(mathir, Mapping) or not mathir:
                findings.append(_finding("FORMULA_AUTHORING_MATHIR_MISSING", source, author_path=author.get("path")))
                closed = False
            elif str(mathir.get("source_sha256", "")).lower() != str(source.get("source_text_sha256", "")).lower():
                findings.append(_finding("FORMULA_AUTHORING_MATHIR_HASH_MISMATCH", source, expected=source.get("source_text_sha256"), actual=mathir.get("source_sha256")))
                closed = False
            if not isinstance(author.get("script"), str) or not author.get("script").strip() or not isinstance(author.get("script_language"), str) or not author.get("script_language").strip():
                findings.append(_finding("FORMULA_AUTHORING_DIALECT_MISSING", source, author_path=author.get("path")))
                closed = False
        if not _source_verified(reviewed_manifest, source_rows[len(ledger)], str(source.get("source_text_sha256", ""))):
            findings.append(_finding("FORMULA_SOURCE_REVIEW_OPEN", source))
            closed = False

        merged = dict(source)
        merged["source_pdf_verified"] = bool(closed)
        merged["closure_status"] = "CLOSED" if closed else "OPEN"
        merged["candidate_only"] = not closed
        merged["match_method"] = match_method
        if author:
            merged["script"] = author.get("script")
            merged["script_language"] = author.get("script_language")
            merged["mathir"] = author.get("mathir")
            merged["authoring_path"] = author.get("path")
        ledger.append(merged)

    for author in authors:
        if str(author.get("path")) not in matched_author_paths:
            findings.append({"code": "FORMULA_AUTHORING_ORPHAN", "stage": "formula-closure", "authoring_path": author.get("path"), "item_id": author.get("item_id")})

    # Validate the generated canonical ledger.  It is intentionally called
    # even when closure findings exist so downstream reports expose the exact
    # provenance failures, not only the join failure.
    strict_input = {
        "source_pdf_sha256": reviewed_manifest.get("source_pdf_sha256"),
        "formula_occurrences": ledger,
    }
    provenance = audit_formula_provenance(strict_input, require_source_evidence=True)
    if provenance.get("status") != "PASS":
        findings.append({"code": "FORMULA_PROVENANCE_GATE_FAIL", "stage": "formula-closure", "finding_count": len(provenance.get("findings", []))})

    source_manifest_validation = (
        validate_source_manifest(reviewed_manifest)
        if reviewed_manifest.get("schema_version") == SCHEMA_VERSION
        else {"status": "REVIEW_REQUIRED", "passed": False, "findings": [{"code": "SOURCE_MANIFEST_SCHEMA_UNVERIFIED"}]}
    )
    source_item_ids = {str(row.get("item_id")) for row in sources if row.get("item_id")}
    item_closed: set[str] = set()
    for item_id in source_item_ids:
        item_rows = [row for row in ledger if str(row.get("item_id")) == item_id]
        if item_rows and all(row.get("closure_status") == "CLOSED" for row in item_rows):
            item_closed.add(item_id)
    passed = bool(ledger) and not findings and provenance.get("status") == "PASS" and source_manifest_validation.get("status") == "PASS" and source_manifest_validation.get("passed") is not False
    report = {
        "schema_version": "formula-closure-v1",
        "status": "PASS" if passed else "REVIEW_REQUIRED",
        "release_status": "PASS" if passed else "REVIEW_REQUIRED",
        "candidate_only": not passed,
        "source_manifest_schema": reviewed_manifest.get("schema_version"),
        "source_manifest_validation": source_manifest_validation,
        "provenance_gate": provenance,
        "counts": {
            "source_formula_occurrences": len(sources),
            "authoring_formula_occurrences": len(authors),
            "linked_formula_occurrences": sum(1 for row in ledger if row.get("closure_status") == "CLOSED" and row.get("authoring_path")),
            "mathir_occurrence_count": sum(1 for row in ledger if isinstance(row.get("mathir"), Mapping) and row.get("mathir")),
            "evidence_closed_item_count": len(item_closed),
            "evidence_open_item_count": len(source_item_ids - item_closed),
            "raw_finding_count": len(findings),
        },
        "findings": findings,
        "formula_occurrences": ledger,
    }
    return report


__all__ = ["build_formula_closure"]
