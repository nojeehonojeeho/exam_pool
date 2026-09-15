import json
import pytest

from app.teacher_workflow import file_hash
from tools.teacher_com_roundtrip_merge import merge
from tools.teacher_workflow_com import classify_roundtrip_pages


def report(source_hash, pages=(12,12), *, physical=True):
    sessions=[]
    for index,page in enumerate(pages):
        sessions.append({'input':f'input-{index}','register_module_return':True,'approval_windows':[],
                         'owned_pids_remaining':[],'b4_pdf':{'pages':page},'gui_pages':page+2 if index else page})
    return {'source_sha256':source_hash,'status':'COM_OPERATIONS_PASS_REQUIRES_PAYLOAD_QA',
            'source_unchanged':True,'physical_b4_page_count_match':physical,'sessions':sessions,
            'gui_page_count_divergences':[]}


def test_physical_page_parity_preserves_gui_warning():
    result=classify_roundtrip_pages([{'gui_pages':12,'b4_pdf':{'pages':12}},{'gui_pages':14,'b4_pdf':{'pages':12}}])
    assert result['physical_b4_page_count_match'] is True
    assert result['gui_page_count_warning_nonphysical'] is True
    assert result['gui_page_count_divergences'][0]['gui_pages']==14


def test_physical_page_difference_is_blocking():
    result=classify_roundtrip_pages([{'gui_pages':12,'b4_pdf':{'pages':12}},{'gui_pages':13,'b4_pdf':{'pages':13}}])
    assert result['physical_b4_page_count_match'] is False


def test_pair_merge_requires_each_target_and_physical_parity(tmp_path):
    hwp=tmp_path/'target.hwp';hwpx=tmp_path/'target.hwpx';hwp.write_bytes(b'hwp');hwpx.write_bytes(b'hwpx')
    left=report(file_hash(hwp));right=report(file_hash(hwpx));left_path=tmp_path/'left.json';right_path=tmp_path/'right.json'
    left_path.write_text(json.dumps(left));right_path.write_text(json.dumps(right))
    result=merge({'hwp':file_hash(hwp),'hwpx':file_hash(hwpx)},left_path,left,right_path,right)
    assert result['physical_b4_page_count_match'] is True
    right['physical_b4_page_count_match']=False
    with pytest.raises(ValueError,match='COM_PHYSICAL_B4_PAGE_COUNT_MISMATCH'):
        merge({'hwp':file_hash(hwp),'hwpx':file_hash(hwpx)},left_path,left,right_path,right)
