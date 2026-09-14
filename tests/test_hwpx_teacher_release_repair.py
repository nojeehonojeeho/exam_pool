from lxml import etree as E
from app.hwpx_teacher_release_repair import H,P,remove_page_frame,resolved_page_frames,wrap_top_level_equalities
from app.hwpx_teacher_release_repair import trim_terminal_endnote_blank_paragraphs
from app.hwpx_teacher_release_repair import main_question_range

def test_whole_question_includes_following_conditions_and_choices():
    sec=E.fromstring(f'<section xmlns="{P}"><p/><p><endNote/></p><p><tbl/></p><p/><p role="workspace"/><p><endNote/></p></section>')
    assert main_question_range(sec,0,trailing_nonquestion=lambda p:p.get('role')=='workspace')==(1,4)

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

def test_terminal_endnote_blank_is_removed_without_touching_content():
    sec=E.fromstring(
        f'<section xmlns="{P}"><p><endNote><subList>'
        '<p><run><t>정답: 3</t></run></p>'
        '<p pageBreak="0" columnBreak="0"><run><t>  </t></run></p>'
        '</subList></endNote></p></section>'
    )
    assert trim_terminal_endnote_blank_paragraphs(sec)==1
    paragraphs=sec.xpath('.//p:endNote/p:subList/p:p',namespaces={'p':P})
    assert len(paragraphs)==1
    assert ''.join(paragraphs[0].itertext())=='정답: 3'

def test_terminal_endnote_trimmer_keeps_objects_and_page_breaks():
    sec=E.fromstring(
        f'<section xmlns="{P}"><p><endNote><subList>'
        '<p><run><t>정답: 3</t></run></p>'
        '<p pageBreak="1"><run><t/></run></p>'
        '<p><run><equation/></run></p>'
        '</subList></endNote></p></section>'
    )
    assert trim_terminal_endnote_blank_paragraphs(sec)==0
