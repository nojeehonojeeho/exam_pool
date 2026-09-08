import hashlib
from unittest.mock import Mock
import pytest
from PIL import Image
from app.hwp_inline_figure import insert_inline_figure

@pytest.fixture
def illustration(tmp_path):
    p=tmp_path/'synthetic.png'
    Image.new('RGB',(20,10),'white').save(p)
    return {'type':'figure','placement':'inline','allowed':True,
            'reason':'pure_illustration','path':str(p),
            'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),
            'width_mm':8,'figure_id':'synthetic-pair'}

def test_inline_keeps_paragraph_and_audits(illustration,tmp_path):
    hwp=Mock()
    audit=insert_inline_figure(hwp,illustration,asset_root=tmp_path,context={'segment_index':2})
    assert audit['width_mm']==8 and audit['height_mm']==4
    assert audit['segment_index']==2 and audit['figure_id']=='synthetic-pair'
    assert audit['sha256']==illustration['sha256']
    hwp.insert_picture.assert_called_once_with(illustration['path'],treat_as_char=True,
        embedded=True,sizeoption=1,width=8,height=4)
    assert [c[0] for c in hwp.method_calls]==['insert_picture','MoveParaEnd']

@pytest.mark.parametrize('field,value',[
    ('placement','block'),('allowed',False),('reason','equation_screenshot'),
    ('representation','semantic_description'),('sha256','bad'),
    ('width_mm',0),('width_mm',float('nan')),('width_mm',float('inf'))])
def test_rejects_before_com(illustration,tmp_path,field,value):
    hwp=Mock();illustration[field]=value
    with pytest.raises(ValueError):insert_inline_figure(hwp,illustration,asset_root=tmp_path,context={})
    assert not hwp.method_calls

def test_failed_insert_does_not_advance_cursor(illustration,tmp_path):
    hwp=Mock();hwp.insert_picture.return_value=False
    with pytest.raises(RuntimeError):insert_inline_figure(hwp,illustration,asset_root=tmp_path,context={})
    hwp.MoveParaEnd.assert_not_called()

@pytest.mark.parametrize('inline,nested,expected',[(True,True,'PASS'),(False,False,'PASS'),(True,False,'FAIL'),(False,True,'FAIL')])
def test_preflight_placement_context(illustration,tmp_path,inline,nested,expected):
    from app.hwp_authoring_preflight import audit_authoring_items
    illustration['placement']='inline' if inline else 'block'
    body=[{'type':'text','segments':[illustration]}] if nested else [illustration]
    item={'item_id':'synthetic','problem_blocks':body,'solution_blocks':[{'type':'text','text':'설명'}]}
    assert audit_authoring_items([item],asset_root=tmp_path)['status']==expected
