from __future__ import annotations

from app.pdf_hwp_semantic_boundaries import is_explicit_structural_marker, merge_physical_rows


def test_ordinary_korean_syllables_are_not_markers() -> None:
    assert not is_explicit_structural_marker("나열하여 만들 수 있")
    assert not is_explicit_structural_marker("다음 조건을 만족")
    assert not is_explicit_structural_marker("가진다.")


def test_explicit_markers_are_preserved() -> None:
    for value in ("(가) 조건", "(나) 조건", "가) 조건", "① 선택", "[보기]"):
        assert is_explicit_structural_marker(value)


def test_inline_formula_row_stays_in_a_single_prose_block() -> None:
    rows = [
        {"text": "숫자를 선택하여"},
        {"text": "f(x)=x^2 를 구하시오."},
    ]
    blocks = merge_physical_rows(rows)
    assert len(blocks) == 1
    assert "f(x)=x^2" in blocks[0][0]


def test_no_target_count_half_split_is_possible() -> None:
    rows = [{"text": "첫 문장이다."}, {"text": "둘째 문장이다."}]
    assert len(merge_physical_rows(rows)) == 2
