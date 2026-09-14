from lxml import etree as E
from app.hwpx_teacher_release_repair import H,P,remove_page_frame,resolved_page_frames,wrap_top_level_equalities

def test_page_frame_does_not_change_shared_table_border_or_column():
    head=E.fromstring(f'<head xmlns="{H}"><borderFills itemCnt="1"><borderFill id="3"><leftBorder type="SOLID"/><rightBorder type="SOLID"/><topBorder type="SOLID"/><bottomBorder type="SOLID"/></borderFill></borderFills></head>')
    sec=E.fromstring(f'<section xmlns="{P}"><pageBorderFill borderFillIDRef="3"/><tbl borderFillIDRef="3"/><colPr colLineType="SOLID"/></section>')
    before=E.tostring(head[0][0])
    remove_page_frame(head,[sec])
    assert E.tostring(head[0][0])==before
    assert sec[1].get('borderFillIDRef')=='3'
    assert sec[2].get('colLineType')=='SOLID'
    assert all(t=='NONE' for frame in resolved_page_frames(head,[sec]) for _,t in frame)

def test_wrap_preserves_tokens_and_groups():
    s='a + b + c + d + e + f = {x=2} over {y+1} = z'
    got=wrap_top_level_equalities(s,24)
    assert '#' in got
    assert '{x=2}' in got
    assert ''.join(got.replace('#','').split())==''.join(s.split())

def test_does_not_split_relations_or_broken_groups():
    for s in ['a '*40+' <= b','a '*40+' != b','{'+ 'a '*40+' = b']:
        assert wrap_top_level_equalities(s,24)==s

def test_existing_multiline_untouched():
    s='a '*40+' # = b'
    assert wrap_top_level_equalities(s,24)==s
