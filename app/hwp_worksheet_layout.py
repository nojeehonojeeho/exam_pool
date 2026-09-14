"""Deterministic planning and QA for teacher-style worksheet writing space.

This module deliberately separates *logical* problem contents from the space
reserved for a student's handwriting.  In a HWPX file the latter must be a
single paragraph with an explicit after-paragraph margin (or an equivalent
table/object property), never a run of manually repeated empty paragraphs.

It is intentionally independent of a particular publisher or source PDF so
that template-append jobs can share the same placement rules.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


HWPUNIT_PER_MM = 283.4645669


@dataclass(frozen=True)
class WorksheetItem:
    """One main-story question and its source-derived layout risk."""

    item_id: str
    text_chars: int
    equations: int = 0
    tables: int = 0
    pictures: int = 0

    @property
    def is_complex(self) -> bool:
        """Whether this item should not be forced into a three-item page."""
        return bool(
            self.tables >= 2
            or self.pictures >= 2
            or self.text_chars >= 740
            or self.equations >= 28
        )


@dataclass(frozen=True)
class WorksheetPage:
    item_ids: tuple[str, ...]


def plan_pages(items: Iterable[WorksheetItem], preferred_items_per_page: int = 3) -> list[WorksheetPage]:
    """Keep source order while using roughly three questions per B4 page.

    A dense table, figure, long condition, or equation-heavy item reduces the
    current page cap to two.  This is a *ceiling*, not an instruction to pad
    a page with invented content.  The final renderer remains responsible for
    moving an item if it cannot retain its measured writing space.
    """
    if preferred_items_per_page < 2:
        raise ValueError("preferred_items_per_page must be at least 2")
    pages: list[WorksheetPage] = []
    current: list[str] = []
    cap = preferred_items_per_page
    for item in items:
        item_cap = 2 if item.is_complex else preferred_items_per_page
        if current and (len(current) >= cap or item.is_complex):
            pages.append(WorksheetPage(tuple(current)))
            current = []
            cap = item_cap
        current.append(item.item_id)
        cap = min(cap, item_cap)
        if len(current) >= cap:
            pages.append(WorksheetPage(tuple(current)))
            current = []
            cap = preferred_items_per_page
    if current:
        pages.append(WorksheetPage(tuple(current)))
    return pages


def hwpunit_to_mm(value: int | float) -> float:
    return round(float(value) / HWPUNIT_PER_MM, 3)


def validate_workspace_margins(
    margins_by_item: dict[str, int], *, minimum_mm: float
) -> list[dict[str, float | str]]:
    """Return per-item failures; an empty list is a layout-space pass."""
    failures: list[dict[str, float | str]] = []
    for item_id, raw in margins_by_item.items():
        actual = hwpunit_to_mm(raw)
        if actual + 1e-9 < minimum_mm:
            failures.append(
                {
                    "item_id": item_id,
                    "actual_mm": actual,
                    "minimum_mm": minimum_mm,
                }
            )
    return failures
