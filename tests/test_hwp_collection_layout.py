from app.hwp_collection_layout import isolated_final_korean_span_indices
from app.hwp_collection_layout import compensate_paragraph_border_offset
import pytest


def span(text="오.", box=(43, 90, 54, 102), font="KoPubWorldDotumPM"):
    return {"text": text, "bbox": box, "font": font}


def test_actual_separate_final_syllable_is_a_candidate():
    assert isolated_final_korean_span_indices([span(), span("preceding", (43, 60, 300, 72))]) == [0]


def test_equation_on_the_left_is_not_an_orphan_extraction_line():
    assert isolated_final_korean_span_indices([span(box=(70, 90, 80, 102)),
        span("synthetic equation", (43, 85, 65, 108), "HancomEQN")]) == []


def test_equation_on_the_right_is_not_an_orphan_extraction_line():
    assert isolated_final_korean_span_indices([span(),
        span("synthetic equation", (60, 85, 100, 108), "HancomEQN")]) == []


def test_unpunctuated_variable_label_or_centered_caption_is_not_a_candidate():
    assert isolated_final_korean_span_indices([span("가"), span(box=(210, 90, 224, 102))]) == []


def test_frame_offset_compensation_preserves_other_border_properties():
    source = {"offsetRight": "425", "offsetLeft": "425", "ignoreMargin": "1", "borderFillIDRef": "7"}
    output = compensate_paragraph_border_offset(source, 2835)
    assert output == {**source, "offsetRight": "3260"}
    assert source["offsetRight"] == "425"


def test_frame_compensation_requires_an_explicit_existing_offset():
    with pytest.raises(ValueError):
        compensate_paragraph_border_offset({"ignoreMargin": "1"}, 2835)
