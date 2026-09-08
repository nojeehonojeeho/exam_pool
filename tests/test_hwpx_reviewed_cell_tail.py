import pytest
from lxml import etree as E
from app.hwpx_reviewed_layout import revise_section

NS='http://www.hancom.co.kr/hwpml/2011/paragraph'
EMPTY='<hp:p pageBreak="0"><hp:run/><hp:linesegarray><hp:lineseg/></hp:linesegarray></hp:p>'
def xml(tail=EMPTY+EMPTY, body='<hp:p><hp:run><hp:t>Keep exact content.</hp:t></hp:run></hp:p>'):
    return (f'<section xmlns:hp="{NS}"><hp:p><hp:run><hp:tbl><hp:tr><hp:tc><hp:subList>'+body+tail+'</hp:subList></hp:tc></hp:tr></hp:tbl></hp:run></hp:p></section>').encode()
PLAN={'table_index':0,'cell_index':0,'expected_empty_tail_count':2}
def test_only_reviewed_empty_tail_removed():
    out,changes=revise_section(xml(),[],cell_tails=[PLAN])
    root=E.fromstring(out)
    assert len(root.find('.//{*}subList'))==1
    assert root.findtext('.//{*}t')=='Keep exact content.'
    assert changes==[{'kind':'reviewed_empty_cell_tail',**PLAN}]
def test_unrequested_tail_unchanged():
    out,_=revise_section(xml(),[])
    assert len(E.fromstring(out).find('.//{*}subList'))==3
@pytest.mark.parametrize('tail',['<hp:p><hp:run><hp:t> </hp:t></hp:run></hp:p>','<hp:p><hp:run><hp:ctrl/></hp:run></hp:p>','<hp:p pageBreak="1"><hp:run/></hp:p>','<hp:p><hp:run><hp:bookmark/></hp:run></hp:p>'])
def test_visible_or_semantic_tail_rejected(tail):
    with pytest.raises(ValueError,match='MISMATCH'):
        revise_section(xml(tail),[],cell_tails=[{**PLAN,'expected_empty_tail_count':1}])
def test_empty_cell_not_removed():
    with pytest.raises(ValueError,match='MISMATCH'):
        revise_section(xml(body=''),[],cell_tails=[PLAN])
def test_duplicate_or_wrong_count_rejected():
    for rows in ([PLAN,PLAN],[{**PLAN,'expected_empty_tail_count':1}],[{**PLAN,'table_index':True}]):
        with pytest.raises(ValueError):revise_section(xml(),[],cell_tails=rows)

def test_explicit_spacer_requires_exact_style_and_empty_content():
    data=xml(tail=EMPTY.replace('<hp:p ', '<hp:p paraPrIDRef="22" '))
    plan={'table_index':0,'cell_index':0,'paragraph_index':1,'expected_para_pr_id':'22'}
    out,_=revise_section(data,[],cell_spacers=[plan])
    assert len(E.fromstring(out).find('.//{*}subList'))==1
    for invalid in ({**plan,'expected_para_pr_id':'23'},{**plan,'paragraph_index':0}):
        with pytest.raises(ValueError):revise_section(data,[],cell_spacers=[invalid])

def test_overlapping_spacer_tail_rejected():
    data=xml(tail=EMPTY.replace('<hp:p ', '<hp:p paraPrIDRef="22" '))
    with pytest.raises(ValueError,match='OVERLAPPING'):
        revise_section(data,[],cell_tails=[{**PLAN,'expected_empty_tail_count':1}],cell_spacers=[{'table_index':0,'cell_index':0,'paragraph_index':1,'expected_para_pr_id':'22'}])
