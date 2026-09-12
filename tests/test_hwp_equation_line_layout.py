import hashlib
import pytest
from app.hwp_equation_line_layout import (
    wrap_equality_chain,
    wrap_safe_math_boundaries,
    wrap_parenthesized_division_as_fraction,
    wrap_adjacent_braced_factors,
    wrap_outer_braced_sum,
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


def test_compact_native_equality_chain_is_layoutable_without_changing_tokens():
    s='(x+1/y)(y+1/z)(z+1/x)=xyz+(x+y+z)+(1/x+1/y+1/z)+1/(xyz)'
    p=run(s,[1])
    assert p['rows']==['(x+1/y)(y+1/z)(z+1/x)','=xyz+(x+y+z)+(1/x+1/y+1/z)+1/(xyz)']
    assert p['layout_script']=='eqalign {(x+1/y)(y+1/z)(z+1/x) # =xyz+(x+y+z)+(1/x+1/y+1/z)+1/(xyz)}'
    assert canonical_script(p['layout_script'],p)==s


def test_explicit_safe_math_breaks_preserve_compact_tokens_and_groups():
    s='0=a^{2}+b^{2}+c^{2}+(d times e)'
    p=wrap_safe_math_boundaries(s, expected_sha256=hashlib.sha256(s.encode()).hexdigest(), safe_break_indices=[2])
    assert p['safe_candidates'] == ['=', '+', '+', '+']
    assert p['rows'] == ['0=a^{2}+', 'b^{2}+c^{2}+(d times e)']
    assert canonical_script(p['layout_script'], p) == s


def test_safe_math_breaks_reject_prose_and_group_interior_guessing():
    with pytest.raises(ValueError, match='SOURCE_PROSE_REQUIRES_EXPLICIT_TEXT_BLOCK'):
        wrap_safe_math_boundaries('x=1, 따라서 y=2', expected_sha256=hashlib.sha256('x=1, 따라서 y=2'.encode()).hexdigest(), safe_break_indices=[1])
    with pytest.raises(ValueError, match='INVALID_SAFE_MATH_BREAKS'):
        wrap_safe_math_boundaries('x=(a+b)', expected_sha256=hashlib.sha256('x=(a+b)'.encode()).hexdigest(), safe_break_indices=[2])


def test_safe_math_breaks_keep_mixed_prose_only_with_explicit_opt_in():
    source = '조건 (가): f(1)-2=0, f(-2)-2=0; 조건 (나): f(-2)-2=0, f(4)-2=0'
    plan = wrap_safe_math_boundaries(
        source,
        expected_sha256=hashlib.sha256(source.encode()).hexdigest(),
        safe_break_indices=[2],
        allow_mixed_prose=True,
    )
    assert plan['mixed_prose_retained'] is True
    assert plan['allow_mixed_prose'] is True
    assert canonical_script(plan['layout_script'], plan) == source


def test_safe_math_breaks_can_explicitly_group_legacy_single_digit_extents():
    source = '0=k^3+a'
    p = wrap_safe_math_boundaries(
        source,
        expected_sha256=hashlib.sha256(source.encode()).hexdigest(),
        safe_break_indices=[2],
        normalize_single_digit_extents=True,
    )
    assert p['layout_script'] == 'eqalign {0=k^{3}+ # a}'
    assert p['normalize_single_digit_extents'] is True
    assert canonical_script(p['layout_script'], p) == source


def test_parenthesized_division_uses_a_hash_bound_fraction_layout():
    source = 'k=(a+b)/(c+d)'
    p = wrap_parenthesized_division_as_fraction(source, expected_sha256=hashlib.sha256(source.encode()).hexdigest())
    assert p['layout_script'] == 'eqalign {k= # {{a+b} over {c+d}}}'
    assert p['numerator'] == 'a+b'
    assert p['denominator'] == 'c+d'
    assert canonical_script(p['layout_script'], p) == source


def test_standalone_parenthesized_division_is_a_valid_fraction_candidate():
    source = '(a+b)/(c+d)'
    p = wrap_parenthesized_division_as_fraction(
        source,
        expected_sha256=hashlib.sha256(source.encode()).hexdigest(),
    )
    assert p['rows'] == ['{{a+b} over {c+d}}']
    assert p['layout_script'] == 'eqalign {{{a+b} over {c+d}}}'
    assert canonical_script(p['layout_script'], p) == source


def test_parenthesized_division_rejects_multiple_or_prose_forms():
    with pytest.raises(ValueError, match='MULTIPLE_TOP_LEVEL_DIVISIONS'):
        wrap_parenthesized_division_as_fraction('x=(a)/(b)/(c)', expected_sha256=hashlib.sha256('x=(a)/(b)/(c)'.encode()).hexdigest())
    prose = '따라서 k=(a)/(b)'
    with pytest.raises(ValueError, match='SOURCE_PROSE_REQUIRES_EXPLICIT_TEXT_BLOCK'):
        wrap_parenthesized_division_as_fraction(prose, expected_sha256=hashlib.sha256(prose.encode()).hexdigest())


def test_adjacent_braced_factors_keep_all_source_tokens_in_reviewed_rows():
    source = '={(x+2)^2+(x+2)(x-2)+(x-2)^2}{(x+2)^2-(x+2)(x-2)+(x-2)^2}=(3x^2+4)(x^2+12)'
    plan = wrap_adjacent_braced_factors(
        source,
        expected_sha256=hashlib.sha256(source.encode()).hexdigest(),
        factor_break_indices=[1],
        normalize_single_digit_extents=True,
    )
    assert plan['rows'] == [
        '={(x+2)^{2}+(x+2)(x-2)+(x-2)^{2}}',
        '{(x+2)^{2}-(x+2)(x-2)+(x-2)^{2}}=(3x^{2}+4)(x^{2}+12)',
    ]
    assert canonical_script(plan['layout_script'], plan) == source


def test_outer_braced_sum_uses_only_reviewed_outer_body_boundaries():
    source = '=-{(1+2i-3-4i)+(5+6i-7-8i)+⋯+(13+14i-15-16i)+17}'
    plan = wrap_outer_braced_sum(
        source,
        expected_sha256=hashlib.sha256(source.encode()).hexdigest(),
        safe_break_indices=[3],
    )
    assert plan['rows'] == ['(1+2i-3-4i)+(5+6i-7-8i)+⋯+', '(13+14i-15-16i)+17']
    assert canonical_script(plan['layout_script'], plan) == source
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
