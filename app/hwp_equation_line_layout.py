"""Explicit presentation-only wrapping of a reviewed equality chain.

No algebra, token deletion, size reduction or source verification inference.
The exact original script remains the canonical semantic/readback target.
"""
from __future__ import annotations
import hashlib
import re
from app.hwp_equation_compiler import validate_hancom_script

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
    rows=[script[a:b].strip() for a,b in zip(offsets,offsets[1:])]
    if any(not row for row in rows):raise ValueError('EMPTY_EQUATION_ROW')
    canonical=lambda s:re.sub(r'\s+',' ',s).strip()
    if canonical(' '.join(rows))!=canonical(script):raise ValueError('EQUATION_TOKEN_CHANGE')
    layout='eqalign {'+' # '.join(rows)+(' , ' if trailing_punctuation else '')+'}'
    validate_hancom_script(layout)
    return {'original_script':script,'original_script_sha256':expected_sha256,'layout_script':layout,'before_equals':before_equals,'rows':rows,'trailing_punctuation':trailing_punctuation,'semantic_tokens_preserved':True,'final':False,'status':'PRESENTATION_CHANGED_REQUIRES_NATIVE_READBACK_AND_VISUAL_QA'}

def canonical_script(actual: str, plan: dict) -> str:
    """Accept only the exact reviewed layout, not arbitrary equivalent math."""
    if actual.strip()!=plan['layout_script'].strip():raise ValueError('LINE_LAYOUT_READBACK_MISMATCH')
    expected=wrap_equality_chain(plan['original_script'],expected_sha256=plan['original_script_sha256'],before_equals=plan['before_equals'],trailing_punctuation=plan.get('trailing_punctuation',''))
    if expected['layout_script']!=plan['layout_script']:raise ValueError('LINE_LAYOUT_PLAN_CHANGED')
    return plan['original_script']
