"""Copyright-free regression tests for the v2 builder boundary."""

from __future__ import annotations

import fitz
import pytest

from app.pdf_hwp_source_fidelity_v2 import (
    PageSetup,
    SOURCE_REGION_LAYOUT,
    SourceFidelityError,
    normalize_content_blocks,
    page_setups_from_pdf,
    source_region_layout_from_manifest,
    validate_source_region_layout,
)


def _layout() -> dict:
    return {
        "mode": SOURCE_REGION_LAYOUT,
        "pages": [
            {
                "pdf_page": 1,
                "media_box": [10, 20, 250, 380],
                "rotation": 0,
                "regions": [
                    {"region_id": "r-left", "bbox": [10, 20, 125, 180], "column_id": "L", "reading_order": 1, "item_id": "q-1"},
                    {"region_id": "r-right", "bbox": [130, 20, 250, 180], "column_id": "R", "reading_order": 2, "item_id": "q-2"},
                ],
            },
            {
                "pdf_page": 2,
                "media_box": [0, 0, 300, 200],
                "rotation": 90,
                "regions": [
                    {"region_id": "r-landscape", "bbox": [0, 0, 300, 200], "column_id": "L", "reading_order": 1, "item_id": "q-3"},
                ],
            },
        ],
    }


def test_page_setup_uses_media_box_and_rotation_instead_of_b4() -> None:
    portrait = PageSetup.from_media_box(1, [10, 20, 250, 380])
    rotated = PageSetup.from_media_box(2, [0, 0, 300, 200], 90)

    assert (portrait.width_pt, portrait.height_pt) == (240.0, 360.0)
    assert (rotated.width_pt, rotated.height_pt) == (200.0, 300.0)
    assert portrait.width_mm != 257.0
    assert portrait.as_dict()["geometry_source"] == "pdf_media_box"


def test_pdf_media_box_is_read_from_synthetic_pdf(tmp_path) -> None:
    source = tmp_path / "synthetic.pdf"
    document = fitz.open()
    page = document.new_page(width=240, height=360)
    page.set_rotation(90)
    document.save(source)
    document.close()

    setups = page_setups_from_pdf(source)
    assert len(setups) == 1
    assert setups[0].rotation == 90
    assert (setups[0].width_pt, setups[0].height_pt) == (360.0, 240.0)


def test_source_region_layout_preserves_per_page_geometry_and_regions() -> None:
    layout = source_region_layout_from_manifest(_layout())

    assert [page.page_number for page in layout.pages] == [1, 2]
    assert [(page.width_pt, page.height_pt) for page in layout.pages] == [(240.0, 360.0), (200.0, 300.0)]
    assert [region.region_id for region in layout.regions] == ["r-left", "r-right", "r-landscape"]
    assert validate_source_region_layout(_layout())["status"] == "PASS"


@pytest.mark.parametrize(
    ("mutate", "code"),
    [
        (lambda value: value["pages"][0].pop("media_box"), "MEDIABOX_REQUIRED"),
        (lambda value: value["pages"][0]["regions"][1].update({"reading_order": 1}), "READING_ORDER_DUPLICATE"),
        (lambda value: value["pages"][0]["regions"][0].update({"bbox": [9, 20, 125, 180]}), "REGION_OUT_OF_PAGE"),
        (lambda value: value["pages"][0]["regions"][0].pop("column_id"), "COLUMN_ID_REQUIRED"),
    ],
)
def test_source_region_layout_fails_closed_without_geometry_or_region_contract(mutate, code) -> None:
    value = _layout()
    mutate(value)
    report = validate_source_region_layout(value)
    assert report["status"] == "FAIL"
    assert report["findings"][0]["code"] == code


def test_legacy_text_wrapper_expands_all_nested_fields_once() -> None:
    blocks, ledger, findings = normalize_content_blocks([
        {
            "type": "text",
            "id": "intro",
            "text": "조건을 읽는다.",
            "condition_box": {"rows": [["x > 0"]]},
            "question": {"text": "값을 구하시오."},
            "table": {"rows": [["a", "b"]]},
            "choices": ["① 1", "② 2"],
        },
    ])

    assert findings == ()
    assert [block.block_type for block in blocks] == ["text", "condition_box", "question", "table", "choices", "choice", "choice"]
    assert {"/blocks/0", "/blocks/0/condition_box", "/blocks/0/question", "/blocks/0/table", "/blocks/0/choices"} <= {
        entry.pointer for entry in ledger.entries
    }
    assert len(ledger.entries) == len(blocks)


def test_unknown_nested_text_field_is_a_hard_failure() -> None:
    _, _, findings = normalize_content_blocks([
        {"type": "text", "text": "문장", "question": {"text": "질문", "quesiton": "오타"}},
    ])

    assert any(row["code"] == "AUTHORING_UNKNOWN_FIELD" and row["path"].endswith("/quesiton") for row in findings)


def test_formula_provenance_metadata_is_consumed_as_traceability_not_content() -> None:
    _, _, findings = normalize_content_blocks([
        {
            "type": "display_equation",
            "script": "x",
            "script_language": "latex",
            "formula_occurrence_id": "SYN:F:001",
            "source_order": 1,
            "source_text_sha256": "a" * 64,
            "source_pdf_sha256": "b" * 64,
            "source_pdf_verified": True,
            "source_evidence": {"pdf_page": 1, "bbox_pt": [1, 1, 2, 2], "source_crop_sha256": "c" * 64, "dpi": 900},
            "mathir": {"source_sha256": "a" * 64, "kind": "atom", "value": "x"},
            "dialect_script": "x",
            "dialect_status": "VERIFIED_SOURCE_BOUND",
            "evidence_status": "VERIFIED",
        },
    ])
    assert findings == ()


def test_consumption_ledger_requires_writer_and_readback() -> None:
    _, ledger, findings = normalize_content_blocks([{"type": "text", "text": "문장"}])
    assert findings == ()
    assert ledger.complete is False
    pointer = ledger.entries[0].pointer
    ledger.mark_written(pointer, "paragraph-1")
    ledger.mark_readback(pointer, "paragraph-1")
    assert ledger.complete is True


def test_media_box_errors_are_typed() -> None:
    with pytest.raises(SourceFidelityError) as exc_info:
        PageSetup.from_media_box(1, [0, 0, 0, 10])
    assert exc_info.value.code == "MEDIABOX_INVALID"
