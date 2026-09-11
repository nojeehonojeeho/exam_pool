import hashlib
import pytest
from app.hwp_equation_line_layout import (
    wrap_equality_chain,
    canonical_script,
    prepare_reviewed_display_layout,
)
def run(s,breaks):return wrap_equality_chain(s,expected_sha256=hashlib.sha256(s.encode()).hexdigest(),before_equals=breaks)
def test_preserves_every_equality_term_and_one_object_script():
    s='f ( n ) = a = b = {{c} over {2}}'
    p=run(s,[3])
    assert p['rows']==['f ( n ) = a = b','= {{c} over {2}}']
    assert canonical_script(p['layout_script'],p)==s
    assert p['final'] is False
def test_nested_and_quoted_equals_are_not_break_candidates():
    p=run('x = {a = b} = rm {"a=b"}',[2])
    assert p['rows']==['x = {a = b}','= rm {"a=b"}']
@pytest.mark.parametrize('breaks',[[],[0],[4],[True],[2,1],[1,1]])
def test_bad_breaks_fail(breaks):
    with pytest.raises(ValueError):run('a = b = c',breaks)
def test_hash_and_readback_changes_fail():
    with pytest.raises(ValueError):wrap_equality_chain('x = y',expected_sha256='0'*64,before_equals=[1])
    p=run('x = y',[1])
    with pytest.raises(ValueError):canonical_script(p['layout_script'].replace('y','z'),p)
def test_existing_matrix_or_aligned_rejected():
    with pytest.raises(ValueError):run('eqalign {a = b # c = d}',[1])
def test_explicit_existing_comma_retained_on_last_row():
    s='a = b = c';p=wrap_equality_chain(s,expected_sha256=hashlib.sha256(s.encode()).hexdigest(),before_equals=[2],trailing_punctuation=',')
    assert p['layout_script'].endswith('= c , }')
    assert canonical_script(p['layout_script'],p)==s
    assert p['trailing_punctuation']==','
    with pytest.raises(ValueError):canonical_script(p['layout_script'].replace(' , ',''),p)
    with pytest.raises(ValueError):wrap_equality_chain(s,expected_sha256=hashlib.sha256(s.encode()).hexdigest(),before_equals=[2],trailing_punctuation='new text')


def test_long_display_layout_keeps_source_hash_and_separates_prose():
    source = 'P(0<=Z<=1)=0.3413; 따라서 n의 최솟값은 25'
    writer = 'pile { P(0<=Z<=1)=0.3413 }'
    plan = prepare_reviewed_display_layout(
        source,
        expected_sha256=hashlib.sha256(source.encode()).hexdigest(),
        writer_script=writer,
        prose_moved_to_text=True,
    )
    assert plan['source_script'] == source
    assert plan['writer_script'] == writer
    assert plan['prose_moved_to_text'] is True
    assert plan['final'] is False


def test_long_display_layout_rejects_mixed_or_undeclared_prose():
    source = 'x = y'
    digest = hashlib.sha256(source.encode()).hexdigest()
    with pytest.raises(ValueError, match='DISPLAY_EQUATION_PROSE_MIXED'):
        prepare_reviewed_display_layout(source, expected_sha256=digest, writer_script='pile { 따라서 x=y }')
    source_with_prose = 'x = y; 따라서'
    with pytest.raises(ValueError, match='SOURCE_PROSE_REQUIRES_EXPLICIT_TEXT_BLOCK'):
        prepare_reviewed_display_layout(
            source_with_prose,
            expected_sha256=hashlib.sha256(source_with_prose.encode()).hexdigest(),
            writer_script='pile { x = y }',
        )
