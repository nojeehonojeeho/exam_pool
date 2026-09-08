import ast
import pytest
from tools.highend_writer_table_merges_patch import patch_source


def test_validation_precedes_table_creation_and_merge_precedes_exit():
    source = '''def _insert_matrix(hwp, block):
    matrix = _matrix(block)
    rows, cols = len(matrix), len(matrix[0])
    hwp.create_table(rows=rows, cols=cols)
    table_ctrl = _enter_new_table(hwp)
    hwp.CloseEx()
'''
    result = patch_source(source)
    ast.parse(result)
    assert result.index('validated_merges(matrix, merges)') < result.index('hwp.create_table')
    assert result.index('apply_native_merges(hwp, matrix, merges, go_to_cell)') < result.index('hwp.CloseEx()')
    assert patch_source(result) == result
    assert 'context.get("unbreakable_phrases", ())' in result
    assert result.index('context = {**context') < result.index('hwp.create_table')


def test_unknown_writer_is_not_silently_patched():
    with pytest.raises(ValueError):
        patch_source('def _insert_matrix(hwp):\n    hwp.CloseEx()\n')


def test_table_protected_phrase_context_is_local_and_inherited():
    from tools.highend_writer_table_merges_patch import PROTECTED_CONTEXT
    scope = {}
    exec('def update(block, context):\n' + PROTECTED_CONTEXT + '    return context\n', scope)
    inherited = {'item_id':'synthetic-1', 'unbreakable_phrases':['NOTE 1']}
    assert scope['update']({}, inherited) == inherited
    changed = scope['update']({'metadata':{'unbreakable_phrases':['why? ②']}}, inherited)
    assert changed['unbreakable_phrases'] == ['why? ②']
    assert inherited['unbreakable_phrases'] == ['NOTE 1']
    assert changed['item_id'] == 'synthetic-1'
