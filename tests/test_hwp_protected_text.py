from app.hwp_protected_text import protected_chunks,insert_protected_text
import pytest

def test_only_declared_spaces_are_protected_and_text_is_preserved():
    text='설명 why? ① 다음 문장'
    parts=protected_chunks(text,['why? ①'])
    assert ''.join(v for _,v in parts)==text
    assert sum(flag for flag,_ in parts)==1
    assert protected_chunks(text,[])==[(False,text)]

def test_undeclared_phrase_remains_ordinary_text():
    assert not any(flag for flag,_ in protected_chunks('why? ②',['why? ①']))

def test_native_failure_is_not_silently_flattened():
    class Fake:
        def insert_text(self,text):pass
        def InsertNonBreakingSpace(self):return False
    with pytest.raises(RuntimeError):insert_protected_text(Fake(),'why? ①',['why? ①'])

def test_snapshot_preserves_native_nonbreaking_control_distinct_from_plain_space():
    import xml.etree.ElementTree as ET
    from app.hwpx_content_snapshot import snapshot_node
    node=ET.fromstring('<p><run><t>why?<nbSpace/>①</t></run></p>')
    snap=snapshot_node(node)
    assert snap[0]['content'][0]['text']=='why?\u00a0①'
    assert snap[0]['content'][0]['text']!='why? ①'
