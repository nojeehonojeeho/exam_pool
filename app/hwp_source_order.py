"""Preserve an explicit source inventory's item order without changing content.

An inventory is not assumed verified; this module only establishes coverage and
sequence relative to the supplied inventory. Source review remains independent.
"""
from __future__ import annotations

from collections import Counter


def order_reviewed_items(items, source_items, *, allow_partial=False):
    def identifiers(rows, label):
        ids = [row.get("item_id") for row in rows]
        if not ids or any(not isinstance(value, str) or not value.strip() for value in ids):
            raise ValueError(f"{label}: missing item IDs")
        duplicates = [key for key, count in Counter(ids).items() if count > 1]
        if duplicates:
            raise ValueError(f"{label}: duplicate item IDs: {duplicates}")
        return ids

    source_ids = identifiers(source_items, "source")
    actual_ids = identifiers(items, "reviewed")
    rank = {item_id: index for index, item_id in enumerate(source_ids)}
    actual_set = set(actual_ids)
    extra = [item_id for item_id in actual_ids if item_id not in rank]
    missing = [item_id for item_id in source_ids if item_id not in actual_set]
    if extra:
        raise ValueError(f"unknown reviewed item IDs: {extra}")
    if missing and not allow_partial:
        raise ValueError(f"incomplete source coverage: {len(missing)} missing")
    ordered = sorted(items, key=lambda item: rank[item["item_id"]])
    return ordered, {
        "check_scope": "coverage_and_order_against_supplied_inventory_only",
        "source_fidelity_proven": False,
        "status": "INCOMPLETE" if missing else "COMPLETE_INVENTORY_COVERAGE",
        "expected_count": len(source_ids), "actual_count": len(actual_ids),
        "missing_ids": missing, "extra_ids": extra,
        "reordered": actual_ids != [item["item_id"] for item in ordered],
        "ordered_ids": [item["item_id"] for item in ordered],
    }
