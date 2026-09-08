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
    )


def reconcile_manifests(
    candidate_manifest: Mapping[str, Any],
    reviewed_manifest: Mapping[str, Any],
    *,
    candidate_items: Iterable[Mapping[str, Any]] | None = None,
    declared_item_count: int | None = None,
) -> dict[str, Any]:
    candidates = list(candidate_items) if candidate_items is not None else _items(candidate_manifest)
    reviewed = _items(reviewed_manifest)
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
