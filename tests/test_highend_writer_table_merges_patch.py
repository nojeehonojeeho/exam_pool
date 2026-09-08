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


def test_unknown_writer_is_not_silently_patched():
    with pytest.raises(ValueError):
        patch_source('def _insert_matrix(hwp):\n    hwp.CloseEx()\n')
