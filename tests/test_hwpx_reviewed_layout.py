import hashlib
import zipfile
import pytest
from lxml import etree as E
from app.hwpx_reviewed_layout import revise_section, revise_package

XML = b'<s xmlns:p="urn:p"><p:endNotePr><p:autoNumFormat supscript="0"/></p:endNotePr><p:p><p:run><p:equation><p:pos treatAsChar="1"/><p:outMargin left="56" right="56"/><p:script>N</p:script></p:equation><p:t>suffix</p:t></p:run></p:p></s>'
ROW = {'index':0,'expected_script':'N','expected_right_hwpunit':56,'right_hwpunit':142}

def test_only_reviewed_presentation_changes():
    changed, log = revise_section(XML,[ROW],superscript_endnote=True)
    r = E.fromstring(changed)
    assert r.find('.//{*}script').text == 'N'
    assert r.find('.//{*}t').text == 'suffix'
    assert r.find('.//{*}outMargin').attrib == {'left':'56','right':'142'}
    assert r.find('.//{*}autoNumFormat').get('supscript') == '1'
    r.find('.//{*}outMargin').set('right','56')
    r.find('.//{*}autoNumFormat').set('supscript','0')
    assert E.tostring(r,method='c14n') == E.tostring(E.fromstring(XML),method='c14n')
    assert log == [ROW]

@pytest.mark.parametrize('patch',[{'index':True},{'index':5},{'expected_script':'M'},{'expected_right_hwpunit':0},{'right_hwpunit':284}])
def test_invalid_plan_rejected(patch):
    with pytest.raises(ValueError): revise_section(XML,[{**ROW,**patch}])

def test_duplicate_and_false_string_rejected():
    with pytest.raises(ValueError): revise_section(XML,[ROW,ROW])
    with pytest.raises(ValueError): revise_section(XML,[],superscript_endnote='false')

def test_fresh_hash_bound_package_preserves_binary(tmp_path):
    source=tmp_path/'source.hwpx'; target=tmp_path/'new.hwpx'
    with zipfile.ZipFile(source,'w') as z:
        z.writestr('Contents/section0.xml',XML)
        z.writestr('BinData/image.png',b'unchanged-image')
    original=source.read_bytes()
    plan={'source_sha256':hashlib.sha256(original).hexdigest(),'sections':{'Contents/section0.xml':{'equations':[ROW]}}}
    result=revise_package(source,target,plan)
    assert result['final'] is False
    assert source.read_bytes()==original
    with zipfile.ZipFile(target) as z: assert z.read('BinData/image.png')==b'unchanged-image'
    with pytest.raises(ValueError): revise_package(source,target,plan)
    with pytest.raises(ValueError): revise_package(source,source,plan)
    with pytest.raises(ValueError): revise_package(source,tmp_path/'other.hwpx',{**plan,'source_sha256':'wrong'})
