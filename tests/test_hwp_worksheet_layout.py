from app.hwp_worksheet_layout import (
    WorksheetItem,
    hwpunit_to_mm,
    plan_pages,
    validate_workspace_margins,
)


def test_plan_keeps_order_and_defaults_to_three_items_per_page() -> None:
    pages = plan_pages([WorksheetItem(str(index), 120) for index in range(1, 8)])
    assert [page.item_ids for page in pages] == [("1", "2", "3"), ("4", "5", "6"), ("7",)]


def test_complex_item_is_not_forced_into_a_three_item_page() -> None:
    pages = plan_pages(
        [
            WorksheetItem("1", 120),
            WorksheetItem("2", 120),
            WorksheetItem("3", 120, tables=2),
            WorksheetItem("4", 120),
            WorksheetItem("5", 120),
        ]
    )
    assert [page.item_ids for page in pages] == [("1", "2"), ("3", "4"), ("5",)]


def test_workspace_margin_uses_physical_units() -> None:
    assert hwpunit_to_mm(17008) == 60.0
    assert validate_workspace_margins({"29": 17008}, minimum_mm=60.0) == []
    assert validate_workspace_margins({"29": 10000}, minimum_mm=60.0)[0]["item_id"] == "29"
