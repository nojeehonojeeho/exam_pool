"""Explicit presentation-only wrapping of a reviewed equality chain.

No algebra, token deletion, size reduction or source verification inference.
The exact original script remains the canonical semantic/readback target.
"""
from __future__ import annotations
import hashlib
import re
from app.hwp_equation_compiler import validate_hancom_script


def prepare_reviewed_display_layout(
    source_script: str,
    *,
    expected_sha256: str,
    writer_script: str,
    prose_moved_to_text: bool = False,
) -> dict:
    """Record a presentation-only writer layout without changing source math.

    Long source blocks may need a reviewed native ``pile``/``eqalign`` writer
    script.  This helper makes the boundary explicit: the source script/hash
    remains authoritative, the writer script must be valid Hancom syntax and
    must not contain Korean prose, and any prose moved to an ordinary text
    block has to be declared by the caller.  It intentionally does not claim
    source fidelity or visual/com readback; those remain separate gates.
    """
    if hashlib.sha256(source_script.encode()).hexdigest() != expected_sha256:
        raise ValueError("LINE_LAYOUT_SOURCE_HASH_MISMATCH")
    if not isinstance(writer_script, str) or not writer_script.strip():
        raise ValueError("EMPTY_WRITER_LAYOUT")
    validate_hancom_script(writer_script)
    source_has_prose = bool(re.search(r"[가-힣]", source_script))
    if source_has_prose and not prose_moved_to_text:
        raise ValueError("SOURCE_PROSE_REQUIRES_EXPLICIT_TEXT_BLOCK")
    if re.search(r"[가-힣]", writer_script):
        raise ValueError("DISPLAY_EQUATION_PROSE_MIXED")
    return {
        "source_script": source_script,
        "source_script_sha256": expected_sha256,
        "writer_script": writer_script,
        "prose_moved_to_text": bool(prose_moved_to_text),
        "presentation_only": True,
        "requires_native_readback": True,
        "requires_visual_qa": True,
        "final": False,
    }

def wrap_equality_chain(script: str, *, expected_sha256: str, before_equals: list[int], trailing_punctuation: str = '') -> dict:
    if hashlib.sha256(script.encode()).hexdigest() != expected_sha256:
        raise ValueError('LINE_LAYOUT_SOURCE_HASH_MISMATCH')
    validate_hancom_script(script)
    if trailing_punctuation not in ('', ','):
        raise ValueError('UNSUPPORTED_BOUNDARY_PUNCTUATION')
    if any(c in script for c in ('#','&')):
        raise ValueError('ALREADY_STRUCTURED_EQUATION')
    points=[];depth=0;quoted=False
    for i,c in enumerate(script):
        if c=='"':quoted=not quoted
        if quoted:continue
        if c=='{':depth+=1
        elif c=='}':depth-=1
        elif c=='=' and depth==0:points.append(i)
    if not before_equals or any(type(i) is not int or not 1<=i<=len(points) for i in before_equals) or before_equals!=sorted(set(before_equals)):
        raise ValueError('INVALID_EQUALITY_BREAKS')
    offsets=[0]+[points[i-1] for i in before_equals]+[len(script)]
    # Preserve the exact source slices before normalizing their display
    # boundaries.  Compact native scripts such as ``x=y`` intentionally have
    # no spaces around ``=``; comparing only whitespace-collapsed display
    # rows used to reject such a safe presentation-only line break.
    raw_rows=[script[a:b] for a,b in zip(offsets,offsets[1:])]
    if ''.join(raw_rows)!=script:raise ValueError('EQUATION_TOKEN_CHANGE')
    rows=[row.strip() for row in raw_rows]
    if any(not row for row in rows):raise ValueError('EMPTY_EQUATION_ROW')
    layout='eqalign {'+' # '.join(rows)+(' , ' if trailing_punctuation else '')+'}'
    validate_hancom_script(layout)
    return {'original_script':script,'original_script_sha256':expected_sha256,'layout_script':layout,'before_equals':before_equals,'rows':rows,'trailing_punctuation':trailing_punctuation,'semantic_tokens_preserved':True,'final':False,'status':'PRESENTATION_CHANGED_REQUIRES_NATIVE_READBACK_AND_VISUAL_QA'}


def _top_level_safe_boundaries(script: str) -> list[tuple[int, int, str]]:
    """Return explicit display-only break candidates outside math groups.

    The caller chooses the candidate ordinals in a hash-bound review plan;
    this helper never selects a line break heuristically.  Parentheses,
    braces and quoted labels are treated as opaque so a break cannot cut a
    fraction, function argument or quoted text.
    """
    candidates: list[tuple[int, int, str]] = []
    brace_depth = paren_depth = 0
    quoted = False
    index = 0
    while index < len(script):
        char = script[index]
        if char == '"':
            quoted = not quoted
            index += 1
            continue
        if quoted:
            index += 1
            continue
        if char == '{':
            brace_depth += 1
            index += 1
            continue
        if char == '}':
            brace_depth -= 1
            index += 1
            continue
        if char == '(':
            paren_depth += 1
            index += 1
            continue
        if char == ')':
            paren_depth -= 1
            index += 1
            continue
        if brace_depth == 0 and paren_depth == 0:
            if script.startswith(' times ', index):
                candidates.append((index, index + len(' times '), 'times'))
                index += len(' times ')
                continue
            if char == '=' and (index == 0 or script[index - 1] not in '<>!') and (index + 1 == len(script) or script[index + 1] != '='):
                candidates.append((index, index + 1, '='))
            elif char == '+' and index > 0:
                candidates.append((index, index + 1, '+'))
            elif char in ',;':
                candidates.append((index, index + 1, char))
        index += 1
    if brace_depth != 0 or paren_depth != 0 or quoted:
        raise ValueError('UNBALANCED_MATH_GROUPS')
    return candidates


def _group_single_digit_script_extents(script: str) -> str:
    """Make a legacy ``x^2`` extent explicit without changing its token."""
    grouped = re.sub(r'([_^])(\d)', r'\1{\2}', script)
    if re.sub(r'([_^])\{(\d)\}', r'\1\2', grouped) != script:
        raise ValueError('SCRIPT_EXTENT_NORMALIZATION_MISMATCH')
    return grouped


def wrap_safe_math_boundaries(
    script: str,
    *,
    expected_sha256: str,
    safe_break_indices: list[int],
    normalize_single_digit_extents: bool = False,
    allow_mixed_prose: bool = False,
) -> dict:
    """Build an explicit multi-line native layout from reviewed safe breaks.

    This is restricted to equation-only scripts by default.  A reviewed plan
    may explicitly retain Korean prose in the same native equation object
    when the source object itself is mixed prose/math and a text split would
    be more invasive.  That opt-in still permits only hash-bound top-level
    display breaks and does not edit or infer source tokens.
    """
    if hashlib.sha256(script.encode()).hexdigest() != expected_sha256:
        raise ValueError('LINE_LAYOUT_SOURCE_HASH_MISMATCH')
    writer_source = _group_single_digit_script_extents(script) if normalize_single_digit_extents else script
    validate_hancom_script(writer_source)
    mixed_prose_retained = bool(re.search(r'[가-힣]', script))
    if mixed_prose_retained and not allow_mixed_prose:
        raise ValueError('SOURCE_PROSE_REQUIRES_EXPLICIT_TEXT_BLOCK')
    if any(char in script for char in ('#', '&')):
        raise ValueError('ALREADY_STRUCTURED_EQUATION')
    candidates = _top_level_safe_boundaries(writer_source)
    if (not safe_break_indices or safe_break_indices != sorted(set(safe_break_indices))
            or any(type(item) is not int or not 1 <= item <= len(candidates) for item in safe_break_indices)):
        raise ValueError('INVALID_SAFE_MATH_BREAKS')
    offsets = [0] + [candidates[item - 1][1] for item in safe_break_indices] + [len(writer_source)]
    raw_rows = [writer_source[start:end] for start, end in zip(offsets, offsets[1:])]
    if ''.join(raw_rows) != writer_source:
        raise ValueError('EQUATION_TOKEN_CHANGE')
    rows = [row.strip() for row in raw_rows]
    if any(not row for row in rows):
        raise ValueError('EMPTY_EQUATION_ROW')
    layout = 'eqalign {' + ' # '.join(rows) + '}'
    validate_hancom_script(layout)
    return {
        'original_script': script,
        'original_script_sha256': expected_sha256,
        'layout_script': layout,
        'layout_kind': 'safe_math_boundaries',
        'safe_break_indices': safe_break_indices,
        'normalize_single_digit_extents': bool(normalize_single_digit_extents),
        'allow_mixed_prose': bool(allow_mixed_prose),
        'mixed_prose_retained': mixed_prose_retained,
        'safe_candidates': [kind for _, _, kind in candidates],
        'rows': rows,
        'semantic_tokens_preserved': True,
        'final': False,
        'status': 'PRESENTATION_CHANGED_REQUIRES_NATIVE_READBACK_AND_VISUAL_QA',
    }


def _matching_parenthesis(script: str, start: int) -> int:
    if start < 0 or start >= len(script) or script[start] != '(':
        raise ValueError('PARENTHESIS_START_REQUIRED')
    depth = 0
    for index in range(start, len(script)):
        char = script[index]
        if char == '(':
            depth += 1
        elif char == ')':
            depth -= 1
            if depth == 0:
                return index
            if depth < 0:
                break
    raise ValueError('UNBALANCED_MATH_GROUPS')


def wrap_parenthesized_division_as_fraction(script: str, *, expected_sha256: str) -> dict:
    """Render one reviewed top-level ``(numerator)/(denominator)`` vertically.

    This is a syntax-only presentation conversion: the captured prefix,
    numerator, denominator and suffix reconstruct the exact source script.
    It is deliberately limited to one top-level parenthesized division and
    rejects prose, matrices and already-structured equations.
    """
    if hashlib.sha256(script.encode()).hexdigest() != expected_sha256:
        raise ValueError('LINE_LAYOUT_SOURCE_HASH_MISMATCH')
    validate_hancom_script(script)
    if re.search(r'[가-힣]', script):
        raise ValueError('SOURCE_PROSE_REQUIRES_EXPLICIT_TEXT_BLOCK')
    if any(char in script for char in ('#', '&')):
        raise ValueError('ALREADY_STRUCTURED_EQUATION')
    brace_depth = paren_depth = 0
    division_index: int | None = None
    for index, char in enumerate(script):
        if char == '{':
            brace_depth += 1
        elif char == '}':
            brace_depth -= 1
        elif char == '(':
            paren_depth += 1
        elif char == ')':
            paren_depth -= 1
        elif char == '/' and brace_depth == 0 and paren_depth == 0:
            if division_index is not None:
                raise ValueError('MULTIPLE_TOP_LEVEL_DIVISIONS')
            division_index = index
    if brace_depth != 0 or paren_depth != 0 or division_index is None:
        raise ValueError('TOP_LEVEL_PARENTHESIZED_DIVISION_REQUIRED')
    left_close = division_index - 1
    if left_close < 0 or script[left_close] != ')' or division_index + 1 >= len(script) or script[division_index + 1] != '(':
        raise ValueError('TOP_LEVEL_PARENTHESIZED_DIVISION_REQUIRED')
    # Locate the matching left opening parenthesis by scanning from the
    # beginning and retaining the one paired with the immediate left close.
    left_open: int | None = None
    depth = 0
    for index, char in enumerate(script[: left_close + 1]):
        if char == '(':
            depth += 1
            if depth == 1:
                candidate = index
        elif char == ')':
            depth -= 1
            if depth == 0 and index == left_close:
                left_open = candidate
                break
    if left_open is None:
        raise ValueError('TOP_LEVEL_PARENTHESIZED_DIVISION_REQUIRED')
    right_open = division_index + 1
    right_close = _matching_parenthesis(script, right_open)
    prefix, numerator = script[:left_open], script[left_open + 1:left_close]
    denominator, suffix = script[right_open + 1:right_close], script[right_close + 1:]
    # A standalone parenthesized division such as ``(a)/(b)`` is a valid
    # fraction candidate too; the prefix is optional.  Historically the
    # helper required a non-empty prefix, which silently rejected precisely
    # the common standalone form.
    if not numerator.strip() or not denominator.strip():
        raise ValueError('EMPTY_FRACTION_COMPONENT')
    if prefix + '(' + numerator + ')/(' + denominator + ')' + suffix != script:
        raise ValueError('EQUATION_TOKEN_CHANGE')
    rows = []
    if prefix.strip():
        rows.append(prefix.strip())
    rows.append('{{' + numerator.strip() + '} over {' + denominator.strip() + '}}')
    if suffix.strip():
        rows.append(suffix.strip())
    layout = 'eqalign {' + ' # '.join(rows) + '}'
    validate_hancom_script(layout)
    return {
        'original_script': script,
        'original_script_sha256': expected_sha256,
        'layout_script': layout,
        'layout_kind': 'parenthesized_division_fraction',
        'prefix': prefix,
        'numerator': numerator,
        'denominator': denominator,
        'suffix': suffix,
        'rows': rows,
        'semantic_tokens_preserved': True,
        'final': False,
        'status': 'PRESENTATION_CHANGED_REQUIRES_NATIVE_READBACK_AND_VISUAL_QA',
    }


def wrap_adjacent_braced_factors(
    script: str,
    *,
    expected_sha256: str,
    factor_break_indices: list[int],
    normalize_single_digit_extents: bool = False,
) -> dict:
    """Lay out reviewed adjacent complete braced factors on native rows.

    This deliberately supports only a break between two already-balanced
    top-level ``}{`` factors.  It is useful for a visually over-wide implicit
    product, while avoiding a cut inside a factor or a rewrite to an explicit
    multiplication token.  The reviewed plan supplies the selected boundary
    ordinal; source tokens and source hash remain canonical.
    """
    if hashlib.sha256(script.encode()).hexdigest() != expected_sha256:
        raise ValueError('LINE_LAYOUT_SOURCE_HASH_MISMATCH')
    if re.search(r'[가-힣]', script):
        raise ValueError('SOURCE_PROSE_REQUIRES_EXPLICIT_TEXT_BLOCK')
    if any(char in script for char in ('#', '&')):
        raise ValueError('ALREADY_STRUCTURED_EQUATION')
    writer_source = _group_single_digit_script_extents(script) if normalize_single_digit_extents else script
    validate_hancom_script(writer_source)
    candidates: list[int] = []
    depth = 0
    for index, char in enumerate(writer_source[:-1]):
        if char == '{':
            depth += 1
        elif char == '}':
            depth -= 1
            if depth < 0:
                raise ValueError('UNBALANCED_MATH_GROUPS')
            if depth == 0 and writer_source[index + 1] == '{':
                candidates.append(index + 1)
    if depth != 0:
        raise ValueError('UNBALANCED_MATH_GROUPS')
    if (not factor_break_indices or factor_break_indices != sorted(set(factor_break_indices))
            or any(type(item) is not int or not 1 <= item <= len(candidates) for item in factor_break_indices)):
        raise ValueError('INVALID_ADJACENT_FACTOR_BREAKS')
    offsets = [0] + [candidates[item - 1] for item in factor_break_indices] + [len(writer_source)]
    raw_rows = [writer_source[start:end] for start, end in zip(offsets, offsets[1:])]
    if ''.join(raw_rows) != writer_source or any(not row.strip() for row in raw_rows):
        raise ValueError('EQUATION_TOKEN_CHANGE')
    layout = 'eqalign {' + ' # '.join(row.strip() for row in raw_rows) + '}'
    validate_hancom_script(layout)
    return {
        'original_script': script,
        'original_script_sha256': expected_sha256,
        'layout_script': layout,
        'layout_kind': 'adjacent_braced_factors',
        'factor_break_indices': factor_break_indices,
        'normalize_single_digit_extents': bool(normalize_single_digit_extents),
        'rows': [row.strip() for row in raw_rows],
        'semantic_tokens_preserved': True,
        'final': False,
        'status': 'PRESENTATION_CHANGED_REQUIRES_NATIVE_READBACK_AND_VISUAL_QA',
    }


def wrap_outer_braced_sum(
    script: str,
    *,
    expected_sha256: str,
    safe_break_indices: list[int],
    normalize_single_digit_extents: bool = False,
) -> dict:
    """Stack a reviewed additive outer-brace expression with native ``pile``.

    The source must be one outer braced expression such as ``=-{a+b+c}``.
    Only top-level safe points *inside* that outer body can be selected.  The
    outer brace remains intact and the rows concatenate exactly back to the
    source body, so this is a display transformation rather than an algebraic
    rewrite.
    """
    if hashlib.sha256(script.encode()).hexdigest() != expected_sha256:
        raise ValueError('LINE_LAYOUT_SOURCE_HASH_MISMATCH')
    if re.search(r'[가-힣]', script):
        raise ValueError('SOURCE_PROSE_REQUIRES_EXPLICIT_TEXT_BLOCK')
    if any(char in script for char in ('#', '&')):
        raise ValueError('ALREADY_STRUCTURED_EQUATION')
    writer_source = _group_single_digit_script_extents(script) if normalize_single_digit_extents else script
    validate_hancom_script(writer_source)
    open_index = writer_source.find('{')
    if open_index <= 0:
        raise ValueError('OUTER_BRACED_SUM_REQUIRED')
    depth = 0
    outer_close: int | None = None
    for index in range(open_index, len(writer_source)):
        char = writer_source[index]
        if char == '{':
            depth += 1
        elif char == '}':
            depth -= 1
            if depth == 0:
                outer_close = index
                break
            if depth < 0:
                break
    if outer_close is None or outer_close != len(writer_source) - 1:
        raise ValueError('OUTER_BRACED_SUM_REQUIRED')
    prefix, body = writer_source[:open_index], writer_source[open_index + 1:outer_close]
    if not prefix.strip() or not body.strip():
        raise ValueError('OUTER_BRACED_SUM_REQUIRED')
    candidates = _top_level_safe_boundaries(body)
    if (not safe_break_indices or safe_break_indices != sorted(set(safe_break_indices))
            or any(type(item) is not int or not 1 <= item <= len(candidates) for item in safe_break_indices)):
        raise ValueError('INVALID_SAFE_MATH_BREAKS')
    offsets = [0] + [candidates[item - 1][1] for item in safe_break_indices] + [len(body)]
    raw_rows = [body[start:end] for start, end in zip(offsets, offsets[1:])]
    if ''.join(raw_rows) != body or any(not row.strip() for row in raw_rows):
        raise ValueError('EQUATION_TOKEN_CHANGE')
    layout = 'eqalign {' + prefix.strip() + '{pile {' + ' # '.join(row.strip() for row in raw_rows) + '}}}'
    validate_hancom_script(layout)
    return {
        'original_script': script,
        'original_script_sha256': expected_sha256,
        'layout_script': layout,
        'layout_kind': 'outer_braced_sum',
        'safe_break_indices': safe_break_indices,
        'normalize_single_digit_extents': bool(normalize_single_digit_extents),
        'rows': [row.strip() for row in raw_rows],
        'semantic_tokens_preserved': True,
        'final': False,
        'status': 'PRESENTATION_CHANGED_REQUIRES_NATIVE_READBACK_AND_VISUAL_QA',
    }

def canonical_script(actual: str, plan: dict) -> str:
    """Accept only the exact reviewed layout, not arbitrary equivalent math."""
    if actual.strip()!=plan['layout_script'].strip():raise ValueError('LINE_LAYOUT_READBACK_MISMATCH')
    if plan.get('layout_kind') == 'safe_math_boundaries':
        expected=wrap_safe_math_boundaries(plan['original_script'],expected_sha256=plan['original_script_sha256'],safe_break_indices=plan['safe_break_indices'],normalize_single_digit_extents=plan.get('normalize_single_digit_extents', False),allow_mixed_prose=plan.get('allow_mixed_prose', False))
    elif plan.get('layout_kind') == 'parenthesized_division_fraction':
        expected=wrap_parenthesized_division_as_fraction(plan['original_script'],expected_sha256=plan['original_script_sha256'])
    elif plan.get('layout_kind') == 'adjacent_braced_factors':
        expected=wrap_adjacent_braced_factors(plan['original_script'],expected_sha256=plan['original_script_sha256'],factor_break_indices=plan['factor_break_indices'],normalize_single_digit_extents=plan.get('normalize_single_digit_extents', False))
    elif plan.get('layout_kind') == 'outer_braced_sum':
        expected=wrap_outer_braced_sum(plan['original_script'],expected_sha256=plan['original_script_sha256'],safe_break_indices=plan['safe_break_indices'],normalize_single_digit_extents=plan.get('normalize_single_digit_extents', False))
    else:
        expected=wrap_equality_chain(plan['original_script'],expected_sha256=plan['original_script_sha256'],before_equals=plan['before_equals'],trailing_punctuation=plan.get('trailing_punctuation',''))
    if expected['layout_script']!=plan['layout_script']:raise ValueError('LINE_LAYOUT_PLAN_CHANGED')
    return plan['original_script']
