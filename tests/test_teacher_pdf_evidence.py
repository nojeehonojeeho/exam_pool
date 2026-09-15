from app.teacher_pdf_evidence import ordered_markers, workspace_rows
from lxml import etree as E
from app.teacher_workflow import H, P
from tools.teacher_release_evidence import (
    compact_two_one_two, exclude_heading_leaves_before_markers,
    first_physical_endnote_page, paragraph_rows,
)


def word(x0, y0, x1, y1, text, width=728):
    return {"x0": x0, "y0": y0, "x1": x1, "y1": y1, "text": text, "page_width": width}


def test_marker_flow_uses_column_order_before_y_order():
    # Question 1 is in the left column lower than question 2's right-column
    # start.  Reading flow is left column then right column, not raw y order.
    rows = ordered_markers([[word(42, 140, 55, 156, "1."), word(375, 99, 388, 115, "2.")]], [1, 2])
    assert [(row["printed_number"], row["column"]) for row in rows] == [(1, 0), (2, 1)]


def test_marker_flow_accepts_source_owned_number_resets():
    rows = ordered_markers([[
        word(42, 140, 55, 156, "1."), word(42, 240, 55, 256, "2."),
        word(375, 140, 388, 156, "1."),
    ]], [1, 2, 1])
    assert [row["printed_number"] for row in rows] == [1, 2, 1]


def test_workspace_uses_column_bottom_for_left_to_right_transition():
    markers = ordered_markers([[word(42, 140, 55, 156, "1."), word(375, 99, 388, 115, "2.")]], [1, 2])
    leaves = [
        {"page": 1, "column": 0, "x0": 62, "y0": 140, "x1": 120, "y1": 207, "kind": "word"},
        {"page": 1, "column": 1, "x0": 392, "y0": 103, "x1": 500, "y1": 191, "kind": "word"},
    ]
    rows = workspace_rows(["q1", "q2"], markers, leaves, body_bottom_pt=937)
    assert rows[0]["boundary_kind"] == "physical_column_bottom"
    assert rows[0]["gap_mm"] > 60
    assert rows[0]["semantic_endpoint_resolved"] is True


def test_workspace_refuses_an_item_without_a_leaf_endpoint():
    markers = ordered_markers([[word(42, 140, 55, 156, "1.")]], [1])
    rows = workspace_rows(["q1"], markers, [], body_bottom_pt=937)
    assert rows[0]["status"] == "REVIEW_REQUIRED"


def test_only_a_compact_two_one_two_can_be_a_wide_choice_exception():
    assert compact_two_one_two([
        [42, 142, "①"], [240, 142, "②"], [240, 175, "③"],
        [42, 240, "④"], [240, 240, "⑤"],
    ])
    assert not compact_two_one_two([
        [42, 142, "①"], [240, 142, "②"], [42, 142, "③"],
        [42, 240, "④"], [240, 240, "⑤"],
    ])
    assert not compact_two_one_two([
        [42, 142, "①"], [240, 142, "②"], [240, 175, "③"],
        [42, 340, "④"], [240, 340, "⑤"],
    ])


def test_physical_endnote_boundary_requires_paired_native_labels():
    class Page:
        def __init__(self, text):
            self.text = text
        def get_text(self, _kind):
            return self.text
    assert first_physical_endnote_page([Page("문제의 정답: 을 고르자"), Page("정답: 3\n해설: 내용")]) == 2


def test_only_actual_native_endnote_controls_are_question_anchors():
    class SyntheticPackage:
        def __init__(self):
            char = E.Element(H("charPr"), id="0")
            E.SubElement(char, H("fontRef"), hangul="0")
            para = E.Element(H("paraPr"), id="0")
            font = E.Element(H("font"), id="0", face="KoPubWorld돋움체 Medium")
            self.catalogs = {"charPr": {"0": char}, "paraPr": {"0": para}}
            self.fonts = {"hangul": {"0": font}}
            sec = E.Element(P("sec"))
            p = E.SubElement(sec, P("p"), paraPrIDRef="0")
            run = E.SubElement(p, P("run"), charPrIDRef="0")
            E.SubElement(run, P("t")).text = "ordinary body"
            anchor = E.SubElement(sec, P("p"), paraPrIDRef="0")
            arun = E.SubElement(anchor, P("run"), charPrIDRef="0")
            E.SubElement(arun, P("t")).text = "1. question"
            E.SubElement(E.SubElement(arun, P("ctrl")), P("endNote"), number="1")
            self.sections = {"section0": sec}
        def style_hash(self, kind, ident):
            return f"{kind}-{ident}"
        def resolved(self, node):
            return {"id": node.get("id")}

    rows = paragraph_rows(SyntheticPackage())
    anchors = [row for row in rows if row["has_question_anchor"]]
    ordinary = [row for row in rows if row["text"].strip() == "ordinary body"]
    assert [row["native_reference_number"] for row in anchors] == ["1"]
    assert ordinary and all(not row["has_question_anchor"] for row in ordinary)


def test_workspace_excludes_only_a_native_proven_heading_before_its_anchor():
    leaves = [
        {"page": 2, "column": 0, "x0": 42, "y0": 99, "x1": 170, "y1": 111, "kind": "word", "text": "unit heading"},
        {"page": 2, "column": 0, "x0": 42, "y0": 117, "x1": 55, "y1": 130, "kind": "word", "text": "25."},
        {"page": 2, "column": 1, "x0": 375, "y0": 99, "x1": 430, "y1": 111, "kind": "word", "text": "real continuation"},
    ]
    markers = [
        {"printed_number": 25, "page": 2, "column": 0, "y0": 117},
        {"printed_number": 26, "page": 2, "column": 1, "y0": 117},
    ]
    retained, excluded = exclude_heading_leaves_before_markers(leaves, markers, {25})
    assert [row["text_sha256"] for row in excluded]
    assert [row["text"] for row in retained] == ["25.", "real continuation"]
