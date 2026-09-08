import pytest
from tools.highend_writer_flow_patch import patch_source

SOURCE='''def _insert_display_equation(hwp,block):
    _style(
        hwp,
        keep=True,
    )
    hwp.BreakPara()

def _build_solution(items):
    for item in items:
        if item:
            _insert_item_heading(hwp, item, role="solution")
            hwp.BreakPara()
            _insert_blocks(item)
'''

def test_patch_is_narrow_idempotent_and_keeps_equation_delimiter():
    result=patch_source(SOURCE)
    assert 'with_next=bool(block.get("keep_with_next", False))' in result
    assert result.count('hwp.BreakPara()')==1
    assert patch_source(result)==result

def test_unknown_writer_fails_instead_of_silent_success():
    with pytest.raises(ValueError):patch_source('def other(): pass\n')
