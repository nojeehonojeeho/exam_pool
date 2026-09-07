"""Source-faithful builder contracts for the v2 PDF→HWP path.

This module deliberately contains no HWP/COM calls.  It is the small,
side-effect-free boundary that a writer can use before handing content to
HwpPalette (or another writer):

* page geometry is derived from the source PDF ``MediaBox`` instead of a
  process-wide B4 default;
* ``source_region_layout`` must carry a geometry record for every source page
  and every region is checked against that page; and
* legacy text wrappers are expanded into ordered typed blocks.  Unknown keys
  fail closed, so a writer cannot silently drop a nested question/table/choice.

The source PDF and real transcriptions stay outside the repository.  The
functions accept either a PDF path or a copyright-free manifest containing
the measured MediaBox values, which keeps the synthetic regression layer
independent from COM and from proprietary inputs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


SCHEMA_VERSION = "pdf-hwp-source-fidelity-v2-builder-v1"
SOURCE_REGION_LAYOUT = "source_region_layout"
ITEM_REFLOW = "item_reflow"
POINTS_PER_INCH = 72.0
MM_PER_INCH = 25.4
HWPUNITS_PER_INCH = 7200.0


class SourceFidelityError(ValueError):
    """A fail-closed source-fidelity input error."""

    def __init__(self, code: str, message: str, *, path: str = "") -> None:
        self.code = code
        self.path = path
        super().__init__(f"{code}{f' at {path}' if path else ''}: {message}")


@dataclass(frozen=True, slots=True)
class PageSetup:
    """One output page setup measured from a source PDF MediaBox."""

    page_number: int
    media_box_pt: tuple[float, float, float, float]
    rotation: int = 0
    width_pt: float = 0.0
    height_pt: float = 0.0
    width_mm: float = 0.0
    height_mm: float = 0.0
    width_hwpunits: int = 0
    height_hwpunits: int = 0

    @classmethod
    def from_media_box(
        cls,
        page_number: int,
        media_box: Sequence[float],
        rotation: int = 0,
    ) -> "PageSetup":
        if isinstance(media_box, (str, bytes)):
            raise SourceFidelityError("MEDIABOX_INVALID", "MediaBox must contain four numbers", path=f"pages/{page_number}/media_box")
        try:
            media_box_length = len(media_box)
        except TypeError as exc:
            raise SourceFidelityError("MEDIABOX_INVALID", "MediaBox must contain four numbers", path=f"pages/{page_number}/media_box") from exc
        if media_box_length != 4:
            raise SourceFidelityError("MEDIABOX_INVALID", "MediaBox must contain four numbers", path=f"pages/{page_number}/media_box")
        try:
            values = tuple(float(value) for value in media_box)
        except (TypeError, ValueError) as exc:
            raise SourceFidelityError("MEDIABOX_INVALID", "MediaBox values must be numeric", path=f"pages/{page_number}/media_box") from exc
        x0, y0, x1, y1 = values
        if x1 <= x0 or y1 <= y0:
            raise SourceFidelityError("MEDIABOX_INVALID", "MediaBox must have positive width and height", path=f"pages/{page_number}/media_box")
        try:
            normalized_rotation = int(rotation) % 360
        except (TypeError, ValueError) as exc:
            raise SourceFidelityError("ROTATION_INVALID", "page rotation must be numeric", path=f"pages/{page_number}/rotation") from exc
        if normalized_rotation not in {0, 90, 180, 270}:
            raise SourceFidelityError("ROTATION_INVALID", "page rotation must be 0, 90, 180, or 270", path=f"pages/{page_number}/rotation")
        raw_width, raw_height = x1 - x0, y1 - y0
        width_pt, height_pt = ((raw_height, raw_width) if normalized_rotation in {90, 270} else (raw_width, raw_height))
        return cls(
            page_number=int(page_number),
            media_box_pt=values,
            rotation=normalized_rotation,
            width_pt=round(width_pt, 6),
            height_pt=round(height_pt, 6),
            width_mm=round(width_pt / POINTS_PER_INCH * MM_PER_INCH, 6),
            height_mm=round(height_pt / POINTS_PER_INCH * MM_PER_INCH, 6),
            width_hwpunits=round(width_pt / POINTS_PER_INCH * HWPUNITS_PER_INCH),
            height_hwpunits=round(height_pt / POINTS_PER_INCH * HWPUNITS_PER_INCH),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "page_number": self.page_number,
            "media_box_pt": list(self.media_box_pt),
            "rotation": self.rotation,
            "width_pt": self.width_pt,
            "height_pt": self.height_pt,
            "width_mm": self.width_mm,
            "height_mm": self.height_mm,
            "width_hwpunits": self.width_hwpunits,
            "height_hwpunits": self.height_hwpunits,
            "geometry_source": "pdf_media_box",
        }


@dataclass(frozen=True, slots=True)
class SourceRegion:
    region_id: str
    page_number: int
    bbox_pt: tuple[float, float, float, float]
    reading_order: int
    column_id: str
    item_id: str | None = None
    role: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "region_id": self.region_id,
            "page_number": self.page_number,
            "bbox_pt": list(self.bbox_pt),
            "reading_order": self.reading_order,
            "column_id": self.column_id,
            "item_id": self.item_id,
            "role": self.role,
        }


@dataclass(frozen=True, slots=True)
class SourceRegionLayout:
    pages: tuple[PageSetup, ...]
    regions: tuple[SourceRegion, ...]
    mode: str = SOURCE_REGION_LAYOUT

    @property
    def page_by_number(self) -> dict[int, PageSetup]:
        return {page.page_number: page for page in self.pages}

    @property
    def region_by_id(self) -> dict[str, SourceRegion]:
        return {region.region_id: region for region in self.regions}

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "mode": self.mode,
            "pages": [page.as_dict() for page in self.pages],
            "regions": [region.as_dict() for region in self.regions],
        }


@dataclass(frozen=True, slots=True)
class ConsumedField:
    pointer: str
    block_id: str
    block_type: str
    writer_status: str = "pending"
    output_id: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "pointer": self.pointer,
            "block_id": self.block_id,
            "block_type": self.block_type,
            "writer_status": self.writer_status,
            "output_id": self.output_id,
        }


@dataclass(slots=True)
class FieldConsumptionLedger:
    """Tracks each source pointer exactly once through the writer boundary."""

    entries: list[ConsumedField] = field(default_factory=list)

    def add(self, pointer: str, block_id: str, block_type: str) -> None:
        if any(entry.pointer == pointer for entry in self.entries):
            raise SourceFidelityError("FIELD_DUPLICATE_CONSUMPTION", "source field was consumed more than once", path=pointer)
        self.entries.append(ConsumedField(pointer, block_id, block_type))

    def mark_written(self, pointer: str, output_id: str) -> None:
        for index, entry in enumerate(self.entries):
            if entry.pointer == pointer:
                self.entries[index] = ConsumedField(entry.pointer, entry.block_id, entry.block_type, "written", output_id)
                return
        raise SourceFidelityError("FIELD_NOT_DECLARED", "writer output refers to an unknown source field", path=pointer)

    def mark_readback(self, pointer: str, output_id: str | None = None) -> None:
        for index, entry in enumerate(self.entries):
            if entry.pointer == pointer:
                self.entries[index] = ConsumedField(entry.pointer, entry.block_id, entry.block_type, "readback", output_id or entry.output_id)
                return
        raise SourceFidelityError("FIELD_NOT_DECLARED", "readback refers to an unknown source field", path=pointer)

    @property
    def complete(self) -> bool:
        return bool(self.entries) and all(entry.writer_status == "readback" for entry in self.entries)

    def as_dict(self) -> dict[str, Any]:
        consumed = len(self.entries)
        return {
            "entries": [entry.as_dict() for entry in self.entries],
            "declared_count": consumed,
            "written_count": sum(entry.writer_status in {"written", "readback"} for entry in self.entries),
            "readback_count": sum(entry.writer_status == "readback" for entry in self.entries),
            "unknown_count": 0,
            "duplicate_count": 0,
            "consumption_rate": 1.0 if consumed else 0.0,
        }


@dataclass(frozen=True, slots=True)
class NormalizedBlock:
    block_id: str
    block_type: str
    value: dict[str, Any]
    source_pointer: str


_COMMON_FIELDS = frozenset({
    "type", "id", "text", "role", "metadata", "meta", "style", "source", "source_ref",
    "review_status", "uncertainties", "children", "runs", "segments", "components",
    "layout", "layout_ref", "bbox", "source_bbox", "x", "y", "width", "height",
    "description", "allowed", "reason", "path", "sha256", "native", "object_type",
    "font", "font_family", "font_size_pt", "line_spacing_percent", "space_before_pt",
    "space_after_pt", "alignment", "justify_stretch", "base_unit", "label", "value",
    "index", "ord", "is_answer", "evidence", "custom_evidence", "kind",
})
_NESTED_TEXT_FIELDS = frozenset({"condition_box", "question", "table", "choices"})
_BLOCK_FIELDS: dict[str, frozenset[str]] = {
    "text": _COMMON_FIELDS | _NESTED_TEXT_FIELDS,
    "question": _COMMON_FIELDS | frozenset({"prompt", "ask", "content"}),
    "condition_box": _COMMON_FIELDS | frozenset({"rows", "cells", "content", "table", "kind"}),
    "table": _COMMON_FIELDS | frozenset({"rows", "cells", "columns", "colspan", "rowspan", "kind"}),
    "choices": _COMMON_FIELDS | frozenset({"items", "values", "layout", "expected_count", "kind"}),
    "choice": _COMMON_FIELDS | frozenset({"label", "value", "index", "ord", "content"}),
    "figure": _COMMON_FIELDS | frozenset({"kind", "content_role", "contains_text"}),
    "equation": _COMMON_FIELDS | frozenset({"script", "source", "script_language", "operator_policies", "cases", "name", "kind"}),
    "inline_equation": _COMMON_FIELDS | frozenset({"script", "source", "script_language", "operator_policies", "kind"}),
    "display_equation": _COMMON_FIELDS | frozenset({"script", "source", "script_language", "operator_policies", "kind"}),
    "blank": _COMMON_FIELDS | frozenset({"width", "height", "kind"}),
}
_BLOCK_FIELDS["piecewise_function"] = _COMMON_FIELDS | frozenset({"script", "source", "script_language", "operator_policies", "cases", "name"})
_BLOCK_FIELDS["figure_reference"] = _COMMON_FIELDS | frozenset({"kind"})


def _pointer(path: str, key: str | int) -> str:
    escaped = str(key).replace("~", "~0").replace("/", "~1")
    return f"{path}/{escaped}" if path else f"/{escaped}"


def _block_id(raw: Mapping[str, Any], pointer: str, block_type: str) -> str:
    declared = str(raw.get("id", "")).strip()
    if declared:
        return declared
    digest = hashlib.sha1(f"{pointer}:{block_type}".encode("utf-8")).hexdigest()[:12]
    return f"src-{block_type}-{digest}"


def _unknown_fields(raw: Mapping[str, Any], block_type: str, pointer: str) -> list[dict[str, Any]]:
    allowed = _BLOCK_FIELDS.get(block_type, _COMMON_FIELDS)
    return [
        {"code": "AUTHORING_UNKNOWN_FIELD", "path": _pointer(pointer, key), "field": key, "block_type": block_type}
        for key in raw
        if key not in allowed
    ]


def normalize_content_blocks(
    blocks: Sequence[Any], *, path: str = "/blocks",
) -> tuple[tuple[NormalizedBlock, ...], FieldConsumptionLedger, tuple[dict[str, Any], ...]]:
    """Expand legacy nested text fields without dropping their content.

    The four legacy keys on a ``text`` block are emitted after the wrapper in
    their explicit contract order.  A caller that needs a different order
    must provide ``children``; having both an ordered child list and legacy
    fields is rejected as ambiguous.  Unknown keys are returned as findings,
    not ignored.
    """

    normalized: list[NormalizedBlock] = []
    findings: list[dict[str, Any]] = []
    ledger = FieldConsumptionLedger()

    def emit(raw: Any, pointer: str, forced_type: str | None = None) -> None:
        if not isinstance(raw, Mapping):
            findings.append({"code": "CONTENT_BLOCK_INVALID", "path": pointer, "detail": "block must be an object"})
            return
        block_type = forced_type or str(raw.get("type", "")).strip()
        if not block_type:
            findings.append({"code": "CONTENT_BLOCK_TYPE_MISSING", "path": pointer})
            return
        findings.extend(_unknown_fields(raw, block_type, pointer))
        block_id = _block_id(raw, pointer, block_type)
        value = dict(raw)
        value["type"] = block_type
        normalized.append(NormalizedBlock(block_id, block_type, value, pointer))
        try:
            ledger.add(pointer, block_id, block_type)
        except SourceFidelityError as exc:
            findings.append({"code": exc.code, "path": pointer, "detail": str(exc)})

        child_values = raw.get("children")
        nested_present = block_type == "text" and any(key in raw for key in _NESTED_TEXT_FIELDS)
        if child_values is not None and nested_present:
            findings.append({"code": "AUTHORING_AMBIGUOUS_CONTENT", "path": pointer, "detail": "children and legacy nested fields cannot both define reading order"})
        if child_values is not None:
            if not isinstance(child_values, Sequence) or isinstance(child_values, (str, bytes)):
                findings.append({"code": "CONTENT_CHILDREN_INVALID", "path": _pointer(pointer, "children")})
            else:
                for index, child in enumerate(child_values):
                    emit(child, _pointer(_pointer(pointer, "children"), index))
        if block_type == "text":
            for key in ("condition_box", "question", "table", "choices"):
                if key not in raw:
                    continue
                child = raw[key]
                child_path = _pointer(pointer, key)
                if key == "choices" and isinstance(child, Sequence) and not isinstance(child, (str, bytes, Mapping)):
                    emit({"type": "choices", "items": list(child)}, child_path)
                elif not isinstance(child, Mapping):
                    emit({"type": key, "text": str(child)}, child_path, key)
                else:
                    emit(child, child_path, key)
        if block_type == "choices":
            items = raw.get("items", raw.get("values"))
            if items is not None:
                if not isinstance(items, Sequence) or isinstance(items, (str, bytes, Mapping)):
                    findings.append({"code": "CONTENT_CHOICES_INVALID", "path": _pointer(pointer, "items")})
                else:
                    for index, item in enumerate(items):
                        if isinstance(item, Mapping):
                            emit(item, _pointer(_pointer(pointer, "items"), index), "choice")
                        else:
                            child_path = _pointer(_pointer(pointer, "items"), index)
                            emit({"type": "choice", "text": str(item)}, child_path, "choice")

    if not isinstance(blocks, Sequence) or isinstance(blocks, (str, bytes)):
        findings.append({"code": "CONTENT_BLOCKS_INVALID", "path": path, "detail": "blocks must be an array"})
    else:
        for index, block in enumerate(blocks):
            emit(block, _pointer(path, index))
    return tuple(normalized), ledger, tuple(findings)


def page_setups_from_pdf(source_pdf: str | Path) -> tuple[PageSetup, ...]:
    """Read exact per-page MediaBoxes and rotations from a source PDF."""

    try:
        import fitz
        document = fitz.open(Path(source_pdf).resolve())
    except (ImportError, OSError, RuntimeError, ValueError) as exc:
        raise SourceFidelityError("SOURCE_PDF_READ_ERROR", str(exc)) from exc
    try:
        return tuple(
            PageSetup.from_media_box(page.number + 1, tuple(float(value) for value in page.mediabox), page.rotation)
            for page in document
        )
    finally:
        document.close()


def _page_record_setup(record: Mapping[str, Any], index: int) -> PageSetup:
    page_number = record.get("pdf_page", record.get("page_number", index))
    media_box = record.get("media_box", record.get("MediaBox", record.get("media_box_pt")))
    if media_box is None:
        raise SourceFidelityError("MEDIABOX_REQUIRED", "source-region pages require the original MediaBox", path=f"pages/{index - 1}/media_box")
    return PageSetup.from_media_box(int(page_number), media_box, record.get("rotation", 0))


def source_region_layout_from_manifest(manifest: Mapping[str, Any]) -> SourceRegionLayout:
    """Build and validate a source-region layout from measured page records."""

    if not isinstance(manifest, Mapping):
        raise SourceFidelityError("LAYOUT_MANIFEST_INVALID", "layout manifest must be an object")
    mode = str(manifest.get("mode", manifest.get("output_layout_mode", SOURCE_REGION_LAYOUT)))
    if mode != SOURCE_REGION_LAYOUT:
        raise SourceFidelityError("LAYOUT_MODE_INVALID", f"expected {SOURCE_REGION_LAYOUT}, got {mode}")
    raw_pages = manifest.get("pages")
    if not isinstance(raw_pages, Sequence) or isinstance(raw_pages, (str, bytes)) or not raw_pages:
        raise SourceFidelityError("LAYOUT_PAGES_REQUIRED", "source-region layout requires page records")
    pages = tuple(_page_record_setup(record, index) for index, record in enumerate(raw_pages, 1) if isinstance(record, Mapping))
    if len(pages) != len(raw_pages) or len({page.page_number for page in pages}) != len(pages):
        raise SourceFidelityError("LAYOUT_PAGE_DUPLICATE", "each source page needs one geometry record")
    by_page = {page.page_number: page for page in pages}
    regions: list[SourceRegion] = []
    seen_ids: set[str] = set()
    seen_orders: set[tuple[int, int]] = set()
    raw_regions: list[tuple[Mapping[str, Any], int, int]] = []
    for page_index, record in enumerate(raw_pages, 1):
        if not isinstance(record, Mapping):
            continue
        page_number = pages[page_index - 1].page_number
        page_regions = record.get("regions", [])
        if not isinstance(page_regions, Sequence) or isinstance(page_regions, (str, bytes)):
            raise SourceFidelityError("REGIONS_INVALID", "page regions must be an array", path=f"pages/{page_index - 1}/regions")
        raw_regions.extend((region, page_number, page_index) for region in page_regions if isinstance(region, Mapping))
    # Accept a normalized manifest form with regions at the document root as
    # well as the page-local authoring form.  Either form still requires an
    # explicit source page; there is no first-page/B4 fallback.
    if not raw_regions and isinstance(manifest.get("regions"), Sequence) and not isinstance(manifest.get("regions"), (str, bytes)):
        for region in manifest["regions"]:
            if not isinstance(region, Mapping):
                continue
            page_number = region.get("pdf_page", region.get("page_number", region.get("page")))
            if page_number is None:
                raise SourceFidelityError("REGION_PAGE_REQUIRED", "root regions require pdf_page/page_number", path="regions")
            page_number = int(page_number)
            if page_number not in by_page:
                raise SourceFidelityError("REGION_PAGE_INVALID", "region refers to an unknown source page", path=str(region.get("region_id", "")))
            raw_regions.append((region, page_number, page_number))
    for region_index, (record, page_number, page_index) in enumerate(raw_regions, 1):
        region_id = str(record.get("region_id", record.get("id", ""))).strip()
        if not region_id or region_id in seen_ids:
            raise SourceFidelityError("REGION_ID_INVALID", "region_id must be nonempty and unique", path=f"pages/{page_index - 1}/regions/{region_index - 1}")
        bbox = record.get("bbox", record.get("bbox_pt"))
        if not isinstance(bbox, Sequence) or isinstance(bbox, (str, bytes)) or len(bbox) != 4:
            raise SourceFidelityError("REGION_BBOX_INVALID", "region bbox must contain four numbers", path=f"pages/{page_index - 1}/regions/{region_index - 1}/bbox")
        try:
            rect = tuple(float(value) for value in bbox)
        except (TypeError, ValueError) as exc:
            raise SourceFidelityError("REGION_BBOX_INVALID", "region bbox values must be numeric") from exc
        x0, y0, x1, y1 = rect
        page = by_page[page_number]
        px0, py0, px1, py1 = page.media_box_pt
        if x1 <= x0 or y1 <= y0 or x0 < px0 or y0 < py0 or x1 > px1 or y1 > py1:
            raise SourceFidelityError("REGION_OUT_OF_PAGE", "region bbox must be inside its source MediaBox", path=region_id)
        reading_order = record.get("reading_order")
        if not isinstance(reading_order, int) or reading_order < 1:
            raise SourceFidelityError("READING_ORDER_INVALID", "reading_order must be a positive integer", path=region_id)
        order_key = (page_number, reading_order)
        if order_key in seen_orders:
            raise SourceFidelityError("READING_ORDER_DUPLICATE", "reading_order must be unique per source page", path=region_id)
        column_id = str(record.get("column_id", record.get("column", ""))).strip()
        if not column_id:
            raise SourceFidelityError("COLUMN_ID_REQUIRED", "source regions require an explicit column id", path=region_id)
        seen_ids.add(region_id)
        seen_orders.add(order_key)
        regions.append(SourceRegion(
            region_id=region_id,
            page_number=page_number,
            bbox_pt=rect,
            reading_order=reading_order,
            column_id=column_id,
            item_id=str(record.get("item_id")).strip() if record.get("item_id") is not None else None,
            role=str(record.get("role", "")).strip(),
        ))
    return SourceRegionLayout(pages=pages, regions=tuple(regions))


def validate_source_region_layout(manifest: Mapping[str, Any]) -> dict[str, Any]:
    try:
        layout = source_region_layout_from_manifest(manifest)
    except SourceFidelityError as exc:
        return {
            "schema_version": SCHEMA_VERSION,
            "status": "FAIL",
            "passed": False,
            "gates": {"media_box_geometry": False, "regions_in_page": False, "reading_order": False},
            "findings": [{"code": exc.code, "path": exc.path, "message": str(exc)}],
        }
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "PASS",
        "passed": True,
        "gates": {"media_box_geometry": True, "regions_in_page": True, "reading_order": True},
        "counts": {"pages": len(layout.pages), "regions": len(layout.regions)},
        "page_setups": [page.as_dict() for page in layout.pages],
        "regions": [region.as_dict() for region in layout.regions],
    }


def canonical_sha256(value: Mapping[str, Any]) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


__all__ = [
    "ConsumedField",
    "FieldConsumptionLedger",
    "ITEM_REFLOW",
    "NormalizedBlock",
    "PageSetup",
    "SCHEMA_VERSION",
    "SOURCE_REGION_LAYOUT",
    "SourceFidelityError",
    "SourceRegion",
    "SourceRegionLayout",
    "canonical_sha256",
    "normalize_content_blocks",
    "page_setups_from_pdf",
    "source_region_layout_from_manifest",
    "validate_source_region_layout",
]
