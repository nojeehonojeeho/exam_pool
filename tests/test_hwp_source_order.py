from copy import deepcopy
import pytest
from app.hwp_source_order import order_reviewed_items


def test_explicit_inventory_order_wins_over_lexical_id_and_queue_order():
    source = [{"item_id": key} for key in ("B-2", "B-10", "B-1-1")]
    items = [{"item_id": key, "solution_blocks": [{"type": "text", "text": key}]} for key in ("B-1-1", "B-10", "B-2")]
    saved = deepcopy(items)
    ordered, report = order_reviewed_items(items, source)
    assert [item["item_id"] for item in ordered] == [item["item_id"] for item in source]
    assert items == saved
    assert ordered[0] is items[2]
    assert report["reordered"] is True
    assert report["source_fidelity_proven"] is False


def test_partial_delivery_requires_explicit_opt_in_and_keeps_missing_ids():
    source = [{"item_id": key} for key in ("S-1", "S-2")]
    with pytest.raises(ValueError, match="incomplete"):
        order_reviewed_items(source[:1], source)
    _, report = order_reviewed_items(source[:1], source, allow_partial=True)
    assert report["status"] == "INCOMPLETE"
    assert report["missing_ids"] == ["S-2"]


@pytest.mark.parametrize("actual,source", [(["A", "A"], ["A"]), (["A"], ["A", "A"]), (["B"], ["A"]), ([""], ["A"])])
def test_ambiguous_or_unknown_ids_fail(actual, source):
    with pytest.raises(ValueError):
        order_reviewed_items([{"item_id": x} for x in actual], [{"item_id": x} for x in source], allow_partial=True)
