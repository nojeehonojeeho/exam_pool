"""Reconcile candidate source scope with explicitly closed evidence.

The module keeps four counts separate:

* candidate IDs from a source inventory;
* inventory-declared item count (which may count variants or sub-items);
* legacy reviewed IDs;
* evidence-closed IDs with explicit closure evidence.

``review_status=VERIFIED`` alone is intentionally not closure evidence.  This
prevents a historical manifest label from being promoted to a source-fidelity
PASS when page, crop, content, formula, solution mapping, and output evidence
are missing.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping


SCHEMA_VERSION = "pdf-hwp-scope-reconciliation-v1"


def _item_id(item: Mapping[str, Any]) -> str | None:
    for key in ("item_id", "id", "problem_id", "question_id", "source_item_id"):
        value = item.get(key)
        if value is not None and str(value).strip():
            return str(value)
    return None


def _items(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, Mapping):
        for key in ("items", "entries", "records", "manifest"):
            if isinstance(value.get(key), list):
                return [item for item in value[key] if isinstance(item, dict)]
    return []


def _status(item: Mapping[str, Any]) -> str:
    return str(item.get("review_status") or item.get("status") or "").upper()


def _explicitly_closed(item: Mapping[str, Any]) -> bool:
    """Return true only for explicit evidence closure, never legacy VERIFIED."""
    if str(item.get("evidence_status") or item.get("v2_status") or "").upper() != "CLOSED":
        return False
    evidence = item.get("source_evidence") or item.get("evidence")
    if not isinstance(evidence, Mapping):
        return False
    required = (
        "source_pdf_sha256",
        "source_page",
        "bbox_pt",
        "source_crop_sha256",
        "review_id",
    )
    return all(str(evidence.get(key) or "").strip() for key in required)


def expand_step_b_variants(
    pages: Iterable[Mapping[str, Any]],
    *,
    id_prefix: str = "HIGH-MATH-DOWN",
) -> list[dict[str, Any]]:
    """Expand Step B base/variant pairs without losing source-page metadata."""
    result: list[dict[str, Any]] = []
    for page in pages:
        chapter = str(page.get("chapter") or "").strip()
        section = str(page.get("section") or "").strip()
        if not chapter or not section:
            continue
        for raw_number in page.get("printed_nums") or []:
            number = str(raw_number).zfill(2)
            variants = ("", "-1") if section.upper() == "B" else ("",)
            for suffix in variants:
                result.append(
                    {
                        "item_id": f"{id_prefix}-{chapter}-{section}-{number}{suffix}",
                        "source_page_physical": page.get("source_page_physical"),
                        "source_page_printed": page.get("source_page_printed"),
                        "chapter": chapter,
                        "section": section,
                        "printed_num": f"{number}{suffix}",
                        "candidate_status": page.get("classification_status"),
                        "solution_mapping_status": page.get("solution_page_status"),
                    }
                )
    return result


def materialize_candidate_items(
    candidate_manifest: Mapping[str, Any],
    *,
    id_prefix: str | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Materialize candidate items from either item- or page-shaped manifests.

    The high-end upper manifest stores 550 item records directly, while the
    lower manifest stores 60 problem pages.  A lower Step B page has three
    printed labels but six source items (base plus ``-1`` variant), so using
    ``len(printed_nums)`` would under-count the source by 66 items.  Keep this
    normalization here so every caller reconciles the same candidate scope.

    The returned detail payload is diagnostic only; it does not certify source
    fidelity or authorize a release.
    """

    direct_items = _items(candidate_manifest)
    if direct_items:
        declared = candidate_manifest.get("item_count")
        if declared is None:
            counts = candidate_manifest.get("counts")
            if isinstance(counts, Mapping):
                declared = counts.get("items")
        return direct_items, {
            "mode": "items",
            "page_count": None,
            "declared_item_count": int(declared) if declared is not None else None,
            "page_declared_item_count": None,
            "page_expansion_count": None,
            "page_count_mismatches": [],
            "declared_count_matches_items": (
                declared is None or int(declared) == len(direct_items)
            ),
            "valid": declared is None or int(declared) == len(direct_items),
        }

    pages = candidate_manifest.get("pages")
    if not isinstance(pages, list):
        return [], {
            "mode": "empty",
            "page_count": None,
            "declared_item_count": None,
            "page_declared_item_count": None,
            "page_expansion_count": None,
            "page_count_mismatches": [],
            "declared_count_matches_items": False,
            "valid": False,
        }

    prefix = str(
        id_prefix
        or candidate_manifest.get("item_id_prefix")
        or "HIGH-MATH-DOWN"
    ).strip()
    expanded = expand_step_b_variants(pages, id_prefix=prefix)
    page_declared = 0
    mismatches: list[dict[str, Any]] = []
    cursor = 0
    for page in pages:
        declared = page.get("item_count") if isinstance(page, Mapping) else None
        page_rows = expand_step_b_variants([page], id_prefix=prefix) if isinstance(page, Mapping) else []
        if isinstance(declared, int):
            page_declared += declared
            if declared != len(page_rows):
                mismatches.append(
                    {
                        "source_page_physical": page.get("source_page_physical"),
                        "source_page_printed": page.get("source_page_printed"),
                        "declared_item_count": declared,
                        "expanded_item_count": len(page_rows),
                    }
                )
        cursor += len(page_rows)

    declared_total = candidate_manifest.get("item_count")
    declared_count_matches_expansion = (
        declared_total is None or int(declared_total) == len(expanded)
    )
    page_declared_matches_expansion = page_declared == len(expanded)
    return expanded, {
        "mode": "pages_step_b_variant_expansion",
        "id_prefix": prefix,
        "page_count": len(pages),
        "declared_item_count": int(declared_total) if declared_total is not None else None,
        "page_declared_item_count": page_declared,
        "page_expansion_count": cursor,
        "page_count_mismatches": mismatches,
        "declared_count_matches_items": declared_count_matches_expansion,
        "page_declared_matches_expansion": page_declared_matches_expansion,
        "valid": declared_count_matches_expansion and page_declared_matches_expansion and not mismatches,
    }


@dataclass(frozen=True)
class ScopeReconciliation:
    candidate_ids: tuple[str, ...]
    declared_item_count: int | None
    legacy_reviewed_ids: tuple[str, ...]
    evidence_closed_ids: tuple[str, ...]
    open_ids: tuple[str, ...]
    duplicate_candidate_ids: tuple[str, ...]
    duplicate_reviewed_ids: tuple[str, ...]
    source_evidence_claim_ids: tuple[str, ...] = ()
    unexpected_reviewed_ids: tuple[str, ...] = ()
    reviewed_candidate_ids: tuple[str, ...] = ()
    unreviewed_candidate_ids: tuple[str, ...] = ()

    @property
    def candidate_id_count(self) -> int:
        return len(self.candidate_ids)

    @property
    def legacy_reviewed_scope_count(self) -> int:
        return len(self.legacy_reviewed_ids)

    @property
    def evidence_closed_item_count(self) -> int:
        return len(self.evidence_closed_ids)

    @property
    def evidence_open_item_count(self) -> int:
        return len(self.open_ids)

    @property
    def reviewed_candidate_scope_count(self) -> int:
        """Number of reviewed IDs that belong to the candidate source scope."""
        return len(self.reviewed_candidate_ids)

    @property
    def unreviewed_candidate_scope_count(self) -> int:
        """Number of candidate IDs absent from the reviewed subset."""
        return len(self.unreviewed_candidate_ids)

    @property
    def coverage_ratio(self) -> float:
        if not self.candidate_ids:
            return 0.0
        return self.reviewed_candidate_scope_count / len(self.candidate_ids)

    @property
    def scope_classification(self) -> str:
        """Classify coverage without treating it as a fidelity/release gate."""
        if not self.candidate_ids:
            return "EMPTY_CANDIDATE_SCOPE"
        if not self.reviewed_candidate_ids:
            return "NO_REVIEWED_SCOPE"
        if self.unexpected_reviewed_ids:
            return "REVIEWED_IDS_OUTSIDE_CANDIDATE"
        if self.duplicate_candidate_ids or self.duplicate_reviewed_ids:
            return "DUPLICATE_SCOPE_IDS"
        if not self.unreviewed_candidate_ids:
            return "FULL_BOOK_COVERAGE"
        return "PARTIAL_SCOPE"

    @property
    def final_eligible(self) -> bool:
        """Metadata reconciliation cannot certify source or artifact fidelity.

        Use the evidence-bound production release gate for actual promotion.
        In particular, an empty scope and fabricated CLOSED metadata must not
        turn this diagnostic into a successful release command.
        """
        return False

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA_VERSION,
            "candidate_id_count": self.candidate_id_count,
            "declared_item_count": self.declared_item_count,
            "legacy_reviewed_scope_count": self.legacy_reviewed_scope_count,
            "reviewed_candidate_scope_count": self.reviewed_candidate_scope_count,
            "unreviewed_candidate_scope_count": self.unreviewed_candidate_scope_count,
            "coverage_ratio": self.coverage_ratio,
            "scope_classification": self.scope_classification,
            "evidence_closed_item_count": self.evidence_closed_item_count,
            "evidence_open_item_count": self.evidence_open_item_count,
            "candidate_ids": list(self.candidate_ids),
            "legacy_reviewed_ids": list(self.legacy_reviewed_ids),
            "evidence_closed_ids": list(self.evidence_closed_ids),
            "open_ids": list(self.open_ids),
            "duplicate_candidate_ids": list(self.duplicate_candidate_ids),
            "duplicate_reviewed_ids": list(self.duplicate_reviewed_ids),
            "source_evidence_claim_ids": list(self.source_evidence_claim_ids),
            "unexpected_reviewed_ids": list(self.unexpected_reviewed_ids),
            "reviewed_candidate_ids": list(self.reviewed_candidate_ids),
            "unreviewed_candidate_ids": list(self.unreviewed_candidate_ids),
            "closure_assessment": "NOT_PERFORMED_BY_METADATA_RECONCILER",
            "declared_count_matches_candidates": self.declared_item_count == self.candidate_id_count if self.declared_item_count is not None else None,
            "final_eligible": self.final_eligible,
        }


def reconcile_scope(
    candidate_items: Iterable[Mapping[str, Any]],
    reviewed_items: Iterable[Mapping[str, Any]],
    *,
    declared_item_count: int | None = None,
) -> ScopeReconciliation:
    candidate_list = list(candidate_items)
    reviewed_list = list(reviewed_items)
    candidates = [str(value) for item in candidate_list if (value := _item_id(item))]
    reviewed = [str(value) for item in reviewed_list if (value := _item_id(item))]
    candidate_set = set(candidates)
    reviewed_set = set(reviewed)
    claims = {_item_id(item) for item in reviewed_list if _item_id(item) and _explicitly_closed(item)} & candidate_set
    # Presence of metadata is not independent evidence validation. Preserve
    # claims for the evidence index; do not silently discard prior checkpoints
    # or certify their source/readback/visual correctness here.
    closed: set[str] = set()
    legacy = {_item_id(item) for item in reviewed_list if _status(item) == "VERIFIED"} & candidate_set
    open_ids = candidate_set - closed
    reviewed_candidate_ids = reviewed_set & candidate_set
    return ScopeReconciliation(
        candidate_ids=tuple(sorted(candidate_set)),
        declared_item_count=declared_item_count,
        legacy_reviewed_ids=tuple(sorted(legacy)),
        evidence_closed_ids=tuple(sorted(closed)),
        open_ids=tuple(sorted(open_ids)),
        duplicate_candidate_ids=tuple(sorted({x for x in candidates if candidates.count(x) > 1})),
        duplicate_reviewed_ids=tuple(sorted({x for x in reviewed if reviewed.count(x) > 1})),
        source_evidence_claim_ids=tuple(sorted(claims)),
        unexpected_reviewed_ids=tuple(sorted(reviewed_set - candidate_set)),
        reviewed_candidate_ids=tuple(sorted(reviewed_candidate_ids)),
        unreviewed_candidate_ids=tuple(sorted(candidate_set - reviewed_candidate_ids)),
    )


def reconcile_manifests(
    candidate_manifest: Mapping[str, Any],
    reviewed_manifest: Mapping[str, Any],
    *,
    candidate_items: Iterable[Mapping[str, Any]] | None = None,
    declared_item_count: int | None = None,
) -> dict[str, Any]:
    materialization = {
        "mode": "caller_supplied",
        "page_count": None,
        "declared_item_count": None,
        "page_declared_item_count": None,
        "page_expansion_count": None,
        "page_count_mismatches": [],
        "declared_count_matches_items": None,
        "valid": True,
    }
    if candidate_items is not None:
        candidates = list(candidate_items)
    else:
        candidates, materialization = materialize_candidate_items(candidate_manifest)
    reviewed = _items(reviewed_manifest)
    if declared_item_count is None:
        materialized_declared = materialization.get("declared_item_count")
        if materialized_declared is not None:
            declared_item_count = int(materialized_declared)
    if declared_item_count is None:
        counts = candidate_manifest.get("counts") if isinstance(candidate_manifest, Mapping) else None
        if isinstance(counts, Mapping):
            for key in ("items", "problem_items", "estimated_total_problem_items"):
                if counts.get(key) is not None:
                    declared_item_count = int(counts[key])
                    break
    result = reconcile_scope(candidates, reviewed, declared_item_count=declared_item_count)
    payload = result.as_dict()
    payload.update(
        {
            "candidate_manifest_status": candidate_manifest.get("status"),
            "reviewed_manifest_status": reviewed_manifest.get("status"),
            "candidate_scope_status": candidate_manifest.get("scope_status"),
            "reviewed_status_counts": {
                status: sum(_status(item) == status for item in reviewed)
                for status in sorted({_status(item) for item in reviewed if _status(item)})
            },
            "candidate_materialization": materialization,
            "scope_assessment": {
                "classification": result.scope_classification,
                "candidate_item_count": result.candidate_id_count,
                "reviewed_candidate_item_count": result.reviewed_candidate_scope_count,
                "unreviewed_candidate_item_count": result.unreviewed_candidate_scope_count,
                "coverage_ratio": result.coverage_ratio,
                "full_book_coverage": result.scope_classification == "FULL_BOOK_COVERAGE",
                "full_book_release_eligible": False,
                "release_note": "Coverage equality is not source-fidelity or artifact-release evidence.",
            },
            "warning": "Legacy VERIFIED labels are not evidence closure.",
        }
    )
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Reconcile candidate and evidence-closed source scope")
    parser.add_argument("candidate", type=Path)
    parser.add_argument("reviewed", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    candidate = json.loads(args.candidate.read_text(encoding="utf-8"))
    reviewed = json.loads(args.reviewed.read_text(encoding="utf-8"))
    output = reconcile_manifests(candidate, reviewed)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0 if output["final_eligible"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
