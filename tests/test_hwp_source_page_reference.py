import pytest
from app.hwp_source_page_reference import reference_page


def test_solution_uses_answer_pdf_page_not_question_pdf_page_number():
    item={'source_page':13,'source_solution_pages':[5,6]}
    assert reference_page(item,'solution',78)==5
    assert reference_page(item,'problem',76)==13
    assert reference_page(item,'endnote',76)==13


def test_no_fallback_from_missing_solution_page_to_question_page():
    with pytest.raises(ValueError,match='SOLUTION_SOURCE_PAGE_MISSING'):
        reference_page({'source_page':13},'solution',78)


def test_explicit_legacy_answer_page_is_supported_but_conflicts_fail():
    assert reference_page({'source_page':11,'source_solution_page':2},'solution',78)==2
    with pytest.raises(ValueError,match='CONFLICT'):
        reference_page({'source_solution_page':2,'source_solution_pages':[5]},'solution',78)


@pytest.mark.parametrize('page',[0,79,'5',True,None])
def test_invalid_source_page_is_not_coerced(page):
    with pytest.raises(ValueError):reference_page({'source_solution_pages':[page]},'solution',78)
