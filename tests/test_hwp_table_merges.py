import pytest
from app.hwp_table_merges import validated_merges,apply_native_merges


def test_source_spans_are_sorted_bottom_first_and_content_retained():
    m=[['','','v'],['A','b','c'],['','d','e']]
    assert validated_merges(m,[[0,0,1,2],[1,0,2,1]])==[(1,0,2,1),(0,0,1,2)]


@pytest.mark.parametrize('matrix,merges,code',[
    ([['a','b']],[[0,0,1,2]],'COVERED_CONTENT'),
    ([['a','']],[[0,0,1,2],[0,0,1,2]],'OVERLAP'),
    ([['a']],[[0,0,2,1]],'OUT_OF_BOUNDS'),
    ([['a',''],['','']],[[0,0,2,2]],'STRAIGHT'),
    ([['a','']],[[False,0,1,2]],'ROW_COL'),
])
def test_invalid_merge_fails_before_any_com(matrix,merges,code):
    with pytest.raises(ValueError,match=code):validated_merges(matrix,merges)


def test_exact_native_actions_and_failure():
    class Hwp:
        def __getattr__(self,name):return lambda:True
    positions=[]
    actions=apply_native_merges(Hwp(),[['A','b'],['','c']],[[0,0,2,1]],lambda r,c:positions.append((r,c)))
    assert positions==[(0,0)]
    assert [a['action'] for a in actions]==['TableCellBlock','TableCellBlockExtend','TableLowerCell','TableMergeCell','Cancel']
    class Failing:
        def TableCellBlock(self):return False
    with pytest.raises(RuntimeError,match='ACTION_FAILED'):
        apply_native_merges(Failing(),[['A','b'],['','c']],[[0,0,2,1]],lambda r,c:None)
