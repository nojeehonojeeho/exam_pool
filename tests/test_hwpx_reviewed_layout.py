import hashlib
import zipfile
import pytest
from lxml import etree as E
from app.hwpx_reviewed_layout import revise_section, revise_package

XML = b'<s xmlns:p="urn:p"><p:endNotePr><p:autoNumFormat supscript="0"/></p:endNotePr><p:p><p:run><p:equation><p:pos treatAsChar="1"/><p:outMargin left="56" right="56"/><p:script>N</p:script></p:equation><p:t>suffix</p:t></p:run></p:p></s>'
ROW = {'index':0,'expected_script':'N','expected_right_hwpunit':56,'right_hwpunit':142}
LONG = 'x=y+z'
LAYOUT = {
    'equation_id': 'eq-1',
    'expected_script': LONG,
    'expected_script_sha256': hashlib.sha256(LONG.encode()).hexdigest(),
    'before_equals': [1],
    'width_hwpunit': 18000,
    'height_hwpunit': 2200,
}

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


def test_hash_bound_compact_equation_layout_preserves_source_plan():
    xml = (XML.replace(b'<p:equation>', b'<p:equation id="eq-1"><p:sz width="12000" height="1100"/>')
           .replace(b'<p:script>N</p:script>', b'<p:script>x=y+z</p:script>'))
    changed, log = revise_section(xml, [], equation_layouts=[LAYOUT])
    root = E.fromstring(changed)
    equation = root.find('.//{*}equation')
    assert equation.findtext('{*}script') == 'eqalign {x # =y+z}'
    assert equation.find('{*}sz').attrib == {'width': '18000', 'height': '2200'}
    assert log[0]['kind'] == 'reviewed_equation_line_layout'
    assert log[0]['source_script_sha256'] == LAYOUT['expected_script_sha256']


def test_equation_layout_rejects_unbound_or_wrong_source():
    xml = (XML.replace(b'<p:equation>', b'<p:equation id="eq-1"><p:sz width="12000" height="1100"/>')
           .replace(b'<p:script>N</p:script>', b'<p:script>x=y+z</p:script>'))
    with pytest.raises(ValueError, match='EQUATION_LAYOUT_SOURCE_HASH_MISMATCH'):
        revise_section(xml, [], equation_layouts=[{**LAYOUT, 'expected_script_sha256': '0' * 64}])
    with pytest.raises(ValueError, match='EQUATION_LAYOUT_ID_NOT_FOUND'):
        revise_section(xml, [], equation_layouts=[{**LAYOUT, 'equation_id': 'other'}])


def test_hash_bound_safe_math_layout_is_explicit_and_no_prose_is_mixed():
    script = '0=a^{2}+b^{2}'
    row = {
        'equation_id': 'eq-1',
        'expected_script': script,
        'expected_script_sha256': hashlib.sha256(script.encode()).hexdigest(),
        'layout_kind': 'safe_math_boundaries',
        'safe_break_indices': [2],
        'width_hwpunit': 18000,
        'height_hwpunit': 2200,
    }
    xml = (XML.replace(b'<p:equation>', b'<p:equation id="eq-1"><p:sz width="12000" height="1100"/>')
           .replace(b'<p:script>N</p:script>', b'<p:script>0=a^{2}+b^{2}</p:script>'))
    changed, log = revise_section(xml, [], equation_layouts=[row])
    assert E.fromstring(changed).findtext('.//{*}script') == 'eqalign {0=a^{2}+ # b^{2}}'
    assert log[0]['layout_kind'] == 'safe_math_boundaries'


def test_hash_bound_safe_math_layout_records_explicit_mixed_prose_opt_in():
    script = '조건 (가): f(1)-2=0, f(-2)-2=0; 조건 (나): f(-2)-2=0, f(4)-2=0'
    row = {
        'equation_id': 'eq-1',
        'expected_script': script,
        'expected_script_sha256': hashlib.sha256(script.encode()).hexdigest(),
        'layout_kind': 'safe_math_boundaries',
        'safe_break_indices': [2],
        'allow_mixed_prose': True,
        'width_hwpunit': 18000,
        'height_hwpunit': 2200,
    }
    xml = (b'<?xml version="1.0" encoding="UTF-8"?>' +
           XML.replace(b'<p:equation>', b'<p:equation id="eq-1"><p:sz width="12000" height="1100"/>')
           .replace(b'<p:script>N</p:script>', b'<p:script>' + script.encode() + b'</p:script>'))
    changed, log = revise_section(xml, [], equation_layouts=[row])
    assert E.fromstring(changed).findtext('.//{*}script') == (
        'eqalign {조건 (가): f(1)-2=0, # f(-2)-2=0; 조건 (나): f(-2)-2=0, f(4)-2=0}'
    )
    assert log[0]['allow_mixed_prose'] is True
    assert log[0]['mixed_prose_retained'] is True


def test_hash_bound_outer_braced_sum_layout_is_written_as_native_pile():
    script = '=-{(1+2i-3-4i)+(5+6i-7-8i)+⋯+(13+14i-15-16i)+17}'
    row = {
        'equation_id': 'eq-1',
        'expected_script': script,
        'expected_script_sha256': hashlib.sha256(script.encode()).hexdigest(),
        'layout_kind': 'outer_braced_sum',
        'safe_break_indices': [3],
        'width_hwpunit': 18000,
        'height_hwpunit': 2600,
    }
    xml = (b'<?xml version="1.0" encoding="UTF-8"?>' +
           XML.replace(b'<p:equation>', b'<p:equation id="eq-1"><p:sz width="12000" height="1100"/>')
           .replace(b'<p:script>N</p:script>', b'<p:script>' + script.encode() + b'</p:script>'))
    changed, log = revise_section(xml, [], equation_layouts=[row])
    assert E.fromstring(changed).findtext('.//{*}script') == (
        'eqalign {=-{pile {(1+2i-3-4i)+(5+6i-7-8i)+⋯+ # (13+14i-15-16i)+17}}}'
    )
    assert log[0]['layout_kind'] == 'outer_braced_sum'
