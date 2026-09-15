import copy,json,zipfile
from pathlib import Path
import pytest
from lxml import etree as E
from app.teacher_workflow import *
from app.hwpx_teacher_release_repair import trim_terminal_endnote_blank_paragraphs

def fixture(tmp_path,count=4):
    header=E.Element(H('head'));refs=E.SubElement(header,H('refList'))
    fonts=E.SubElement(refs,H('fontfaces'));ff=E.SubElement(fonts,H('fontface'),lang='HANGUL');E.SubElement(ff,H('font'),id='0',face='KoPubWorld돋움체 Medium')
    chars=E.SubElement(refs,H('charProperties'));c=E.SubElement(chars,H('charPr'),id='0',height='1150');E.SubElement(c,H('fontRef'),hangul='0')
    paras=E.SubElement(refs,H('paraProperties'))
    for i in range(3):
        pp=E.SubElement(paras,H('paraPr'),id=str(i),role=['body','workspace','heading'][i])
        E.SubElement(pp,H('breakSetting'))
    styles=E.SubElement(refs,H('styles'));E.SubElement(styles,H('style'),id='0',paraPrIDRef='0',charPrIDRef='0')
    borders=E.SubElement(refs,H('borderFills'));b=E.SubElement(borders,H('borderFill'),id='1');E.SubElement(b,H('leftBorder'),type='SOLID')
    sec=E.Element(P('sec'));ctrl=E.SubElement(E.SubElement(E.SubElement(sec,P('p'),paraPrIDRef='0',styleIDRef='0'),P('run'),charPrIDRef='0'),P('secPr'))
    E.SubElement(ctrl,P('pageBorderFill'),borderFillIDRef='1')
    E.SubElement(E.SubElement(ctrl,P('endNotePr')),P('placement'),place='END_OF_DOCUMENT')
    for i in range(count):
        p=E.SubElement(sec,P('p'),paraPrIDRef='0',styleIDRef='0');r=E.SubElement(p,P('run'),charPrIDRef='0');E.SubElement(r,P('t')).text=f'Question {i+1} '
        note=E.SubElement(E.SubElement(r,P('ctrl')),P('endNote'),number=str(i+1));sub=E.SubElement(note,P('subList'))
        n=E.SubElement(sub,P('p'),paraPrIDRef='0',styleIDRef='0');rr=E.SubElement(n,P('run'),charPrIDRef='0');E.SubElement(rr,P('t')).text=f'Answer {i+1}'
        if i==0:
            pic=E.SubElement(rr,P('pic'));E.SubElement(pic,f'{{{HC}}}img',binaryItemIDRef='asset');E.SubElement(pic,f'{{{HC}}}pos',treatAsChar='0')
        eq=E.SubElement(r,P('equation'),baseUnit='1100',font='HYhwpEQ');E.SubElement(eq,P('script')).text='x^2 + 1'
        sp=E.SubElement(sec,P('p'),paraPrIDRef='1',styleIDRef='0');E.SubElement(E.SubElement(sp,P('run'),charPrIDRef='0'),P('t'))
    master=E.Element(P('masterPage'));E.SubElement(master,f'{{{HC}}}img',binaryItemIDRef='asset')
    manifest=E.fromstring('<package><manifest><item id="asset" href="BinData/logo.bin"/></manifest></package>')
    path=tmp_path/'candidate.hwpx'
    with zipfile.ZipFile(path,'w') as z:
        for name,node in [('Contents/header.xml',header),('Contents/section0.xml',sec),('Contents/masterpage0.xml',master),('Contents/content.hpf',manifest)]:z.writestr(name,E.tostring(node))
        z.writestr('BinData/logo.bin',b'synthetic')
    return path

def configuration(tmp_path,count=4):
    path=fixture(tmp_path,count);pkg=Package(path);ref={'path':str(path),'sha256':file_hash(path)}
    inv=tmp_path/'inventory.json';write_json(inv,{'items':[{'id':f'id{i}'} for i in range(count)]})
    return {'schema':'teacher-native-reflow/v1','mode':'template_only','native_candidate':ref,'source':ref,'style_reference':ref,
            'inventory':{'path':str(inv),'sha256':file_hash(inv)},'candidate_item_ids':[f'id{i}' for i in range(count)],'selected_item_ids':['id0',f'id{count-1}'],
            'roles':{'workspace_para_sha256':pkg.style_hash('paraPr','1'),'body_para_sha256':pkg.style_hash('paraPr','0'),'body_char_sha256':pkg.style_hash('charPr','0'),'heading_para_sha256s':[pkg.style_hash('paraPr','2')],'heading_text_sha256s':[]},
            'header':{'source_sha256':ref['sha256'],'allowed_asset_sha256s':[digest(b'synthetic')]},
            'layout':{'reserved_right_gap_hwpunit':34016,'column_height_hwpunit':82000},'output':'result.hwpx'}

@pytest.mark.parametrize('count',[2,4,7])
def test_real_build_not_hardcoded(tmp_path,count):
    cfg=configuration(tmp_path,count);report=build(cfg,tmp_path)
    assert report['represented_count']==2 and report['source_scope_count']==count
    assert report['native_note_count']==2 and report['final'] is False
    assert file_hash(tmp_path/'result.hwpx')!=cfg['native_candidate']['sha256']

@pytest.mark.parametrize('mutation,error',[
    (lambda c:c.update(mode='append_to_teacher'),'APPEND'),
    (lambda c:c['source'].update(sha256='0'*64),'HASH'),
    (lambda c:c.update(selected_item_ids=[]),'SELECTION'),
    (lambda c:c.update(selected_item_ids=['id0','id0']),'SELECTION'),
    (lambda c:c.update(candidate_item_ids=['id0']),'BIJECTIVE'),
    (lambda c:c['header'].update(allowed_asset_sha256s=['0'*64]),'HEADER'),
    (lambda c:c['roles'].update(body_para_sha256='0'*64),'ROLE')])
def test_build_refuses_bad_contract(tmp_path,mutation,error):
    c=configuration(tmp_path);mutation(c)
    with pytest.raises(ValueError,match=error):build(c,tmp_path)
    assert not (tmp_path/'result.hwpx').exists()

def test_style_ids_not_meaning(tmp_path):
    pkg=Package(fixture(tmp_path));before=pkg.style_hash('charPr','0')
    font=pkg.fonts['hangul'].pop('0');font.set('id','99');pkg.fonts['hangul']['99']=font
    pkg.catalogs['charPr']['0'].find(H('fontRef')).set('hangul','99');pkg._style_hashes.clear()
    assert before==pkg.style_hash('charPr','0')
    font.set('face','Wrong font');pkg._style_hashes.clear()
    assert before!=pkg.style_hash('charPr','0')

def test_core_image_payload_and_spaces(tmp_path):
    pkg=Package(fixture(tmp_path));p=E.fromstring(f'<p xmlns="{HP}"><run><t>a b</t><pic><img xmlns="{HC}" binaryItemIDRef="asset"/></pic></run></p>')
    a=payload(pkg,[p]);assert ['image',digest(b'synthetic')] in a
    p.find('.//'+P('t')).text='ab';assert a!=payload(pkg,[p])
    p.find(f'.//{{{HC}}}img').set('binaryItemIDRef','bad')
    with pytest.raises(ValueError,match='UNRESOLVED_IMAGE'):payload(pkg,[p])

def test_table_cell_content_not_count_only(tmp_path):
    pkg=Package(fixture(tmp_path));p=E.fromstring(f'<p xmlns="{HP}"><run><tbl rowCnt="1" colCnt="1"><tr><tc><cellSpan colSpan="1" rowSpan="1"/><subList><p><run><t>x</t></run></p></subList></tc></tr></tbl></run></p>')
    a=payload(pkg,[p]);p.find('.//'+P('cellSpan')).set('colSpan','2')
    assert payload(pkg,[p])!=a

def test_trim_never_table_cell_or_only_note_paragraph():
    s=E.fromstring(f'<sec xmlns="{HP}"><p><run><ctrl><endNote><subList><p><run><tbl><tr><tc><subList><p><run><t/></run></p></subList></tc></tr></tbl></run></p></subList></endNote></ctrl></run></p></sec>')
    before=E.tostring(s);assert trim_terminal_endnote_blank_paragraphs(s)==0;assert E.tostring(s)==before

def test_body_style_is_not_a_heading_filter(tmp_path):
    cfg=configuration(tmp_path)
    pkg=Package(Path(cfg['native_candidate']['path']))
    cfg['roles']['heading_para_sha256s']=[pkg.style_hash('paraPr','0')]
    cfg['roles']['heading_text_sha256s']=[digest(b'Only this heading')]
    result=build(cfg,tmp_path)
    assert len(result['expected'])==2
    assert 'Question 1' in ''.join(v for k,v in result['expected'][0]['body'] if k=='text')

def test_rebuild_prefix_does_not_duplicate_header(tmp_path):
    cfg=configuration(tmp_path);path=Path(cfg['native_candidate']['path']);pkg=Package(path);sec=next(iter(pkg.sections.values()))
    title=sec[0];run=title.find(P('run'));E.SubElement(run,P('t')).text='Chapter'
    ctrl=E.SubElement(run,P('ctrl'));hd=E.SubElement(ctrl,P('header'),id='17');E.SubElement(hd,P('subList'))
    pkg.members['Contents/section0.xml']=E.tostring(sec)
    with zipfile.ZipFile(path,'w') as z:
        for name,data in pkg.members.items():z.writestr(name,data)
    for key in ('native_candidate','source','style_reference'):cfg[key]['sha256']=file_hash(path)
    cfg['header']['source_sha256']=file_hash(path)
    cfg['roles']['heading_para_sha256s']=[pkg.style_hash('paraPr','0')]
    cfg['roles']['heading_text_sha256s']=[digest(b'Chapter')]
    build(cfg,tmp_path);out=Package(tmp_path/'result.hwpx');sec=next(iter(out.sections.values()))
    assert len(sec.findall('.//'+P('secPr')))==1
    assert len(sec.findall('.//'+P('header')))==1

def test_gate_bad_endnote_boundary(tmp_path):
    run=valid_release(tmp_path);ref=run['evidence']['endnote_order'];path=Path(ref['path']);r=json.loads(path.read_text())
    r['boundary']['first_note_page']=3;path.write_text(json.dumps(r));ref['sha256']=file_hash(path)
    assert release_gate(run,tmp_path)['final'] is False

def test_metadata_table_is_not_implicitly_solution():
    note=E.fromstring(f'<endNote xmlns="{HP}"><subList><p><run><tbl><tr><tc><subList><p><run><t>교재명 Sample Page 20</t></run></p></subList></tc></tr></tbl></run></p></subList></endNote>')
    assert leaked_section_metadata([note])==[(0,0)]

def valid_release(tmp_path):
    artifact=tmp_path/'artifact';artifact.write_text('synthetic');ref={'path':str(artifact),'sha256':file_hash(artifact)}
    run={'schema':'teacher-release/v1','scope_ids':['q'],'targets':{'hwp':ref,'hwpx':ref},'evidence':{}}
    for kind in REQUIRED:
        r={'schema':'teacher-evidence/v1','kind':kind,'target_sha256':{'hwp':ref['sha256'],'hwpx':ref['sha256']},'checks':{'checked':True},'status':'PASS','open_items':[],
           'scope_ids':['q'],'observations':[{'method':'synthetic test','artifact':ref}],
           'boundary':{'last_question_method':'main object position','first_note_method':'note object position','last_question_page':3,'first_note_page':4},
           'coverage':'all_applicable_roles','required_roles':['body'],
           'role_renders':[{'role':'body','font_match':True,'actual_fonts':['Synthetic font'],'expected_fonts':['Synthetic font'],'pages':[1],'render_artifact':ref}],
           'transfers':[{'id':'q','operation':'move','whole_question':True,'readback':True,'payload_equal':True,'readback_artifact':ref,'before_payload_sha256':ref['sha256'],'after_payload_sha256':ref['sha256']}],
           'automated_pages':[1,2,3,4],'human_reviewed_pages':[1,4],'physical_page_count':4}
        f=tmp_path/(kind+'.json');write_json(f,r);run['evidence'][kind]={'path':str(f),'sha256':file_hash(f)}
    return run

def test_gate_synthetic_complete(tmp_path):assert release_gate(valid_release(tmp_path),tmp_path)['status']=='PASS'

@pytest.mark.parametrize('kind,field,value',[
 ('source_payload','checks',{}),('style_roles','checks',{'x':'PASS'}),('com_roundtrip','target_sha256',{}),
 ('font_render','coverage','font_name_present_once'),('whole_question_transfer','transfers',[]),
 ('visual_qa','automated_pages',[1]),('source_scope','scope_ids',[]),('header_render','observations',[]),
 ('workspace','open_items',['q']),('font_render','role_renders',[]),('visual_qa','human_reviewed_pages',[]),
 ('visual_qa','physical_page_count',0)])
def test_gate_rejects_vacuous_stale_partial(tmp_path,kind,field,value):
    run=valid_release(tmp_path);ref=run['evidence'][kind];path=Path(ref['path']);r=json.loads(path.read_text());r[field]=value
    path.write_text(json.dumps(r));ref['sha256']=file_hash(path)
    assert release_gate(run,tmp_path)['final'] is False

def test_empty_run_is_blocked(tmp_path):assert release_gate({},tmp_path)['final'] is False

@pytest.mark.parametrize('run',[None,{'targets':None,'evidence':None,'scope_ids':[{}]},{'targets':{'hwp':None},'scope_ids':'q'}])
def test_malformed_run_is_blocked_without_crash(tmp_path,run):
    assert release_gate(run,tmp_path)['final'] is False

@pytest.mark.parametrize('field,value', [('first_note_method','title_backcalculation'),('last_question_method','title_backcalculation'),('last_question_page',False),('last_question_page',-1)])
def test_boundary_independent_real_positive_page(tmp_path,field,value):
    run=valid_release(tmp_path);ref=run['evidence']['endnote_order'];path=Path(ref['path']);r=json.loads(path.read_text());r['boundary'][field]=value
    path.write_text(json.dumps(r));ref['sha256']=file_hash(path)
    assert release_gate(run,tmp_path)['final'] is False

def test_transfer_requires_exact_readback_artifact(tmp_path):
    run=valid_release(tmp_path);ref=run['evidence']['whole_question_transfer'];path=Path(ref['path']);r=json.loads(path.read_text())
    r['transfers'][0]['readback_artifact']={'path':'missing','sha256':'0'*64}
    path.write_text(json.dumps(r));ref['sha256']=file_hash(path)
    assert release_gate(run,tmp_path)['final'] is False

@pytest.mark.parametrize('indices',[[],[0],[0,0],[-1,1],[0,3]])
def test_com_transfer_invalid_selection_before_open(indices):
    from tools.teacher_workflow_com import validate_transfer_selection
    with pytest.raises(ValueError,match='TRANSFER_REQUIRES'):
        validate_transfer_selection(indices,3)

def test_com_transfer_valid_selection():
    from tools.teacher_workflow_com import validate_transfer_selection
    validate_transfer_selection([2,0,1],3)

def test_note_page_start_is_explicit_and_bound(tmp_path):
    cfg=configuration(tmp_path);cfg['note_page_start_item_ids']=['id0']
    result=build(cfg,tmp_path);out=Package(tmp_path/'result.hwpx');sec=next(iter(out.sections.values()))
    starts=[n for n in sec if n.find('.//'+P('endNote')) is not None]
    first=starts[0].find('.//'+P('endNote')+'/'+P('subList')+'/'+P('p'))
    assert first.get('pageBreak')=='1' and result['note_page_start_item_ids']==['id0']

def test_inline_note_image_normalization_is_explicit(tmp_path):
    cfg=configuration(tmp_path);cfg['inline_note_images_item_ids']=['id0']
    build(cfg,tmp_path);out=Package(tmp_path/'result.hwpx');sec=next(iter(out.sections.values()))
    pic=next(n for n in sec.iter() if E.QName(n).localname=='pic')
    pos=next(n for n in pic.iter() if E.QName(n).localname=='pos')
    assert pic.get('textWrap')=='NONE' and pos.get('treatAsChar')=='1'

def test_note_image_para_anchor_is_explicit(tmp_path):
    cfg=configuration(tmp_path);cfg['note_image_para_anchor_item_ids']=['id0']
    build(cfg,tmp_path);out=Package(tmp_path/'result.hwpx');sec=next(iter(out.sections.values()))
    pos=next(n for n in sec.iter() if E.QName(n).localname=='pos')
    assert pos.get('horzRelTo')=='PARA' and pos.get('vertRelTo')=='PARA'

def test_note_keep_with_next_clones_break_style(tmp_path):
    cfg=configuration(tmp_path);cfg['join_generated_note_label']=False;cfg['note_keep_with_next_item_ids']=['id0']
    build(cfg,tmp_path);out=Package(tmp_path/'result.hwpx');sec=next(iter(out.sections.values()));first=next(n for n in sec if n.find('.//'+P('endNote')) is not None).find('.//'+P('endNote')+'/'+P('subList')+'/'+P('p'))
    para=out.catalogs['paraPr'][first.get('paraPrIDRef')];setting=next(x for x in para.iter() if E.QName(x).localname=='breakSetting')
    assert setting.get('keepWithNext')=='1' and setting.get('keepLines')=='1'

def test_note_page_break_before_clones_break_style(tmp_path):
    cfg=configuration(tmp_path);cfg['join_generated_note_label']=False;cfg['note_page_break_before_item_ids']=['id0']
    build(cfg,tmp_path);out=Package(tmp_path/'result.hwpx');sec=next(iter(out.sections.values()));first=next(n for n in sec if n.find('.//'+P('endNote')) is not None).find('.//'+P('endNote')+'/'+P('subList')+'/'+P('p'))
    para=out.catalogs['paraPr'][first.get('paraPrIDRef')];setting=next(x for x in para.iter() if E.QName(x).localname=='breakSetting')
    assert setting.get('keepWithNext')=='1' and setting.get('keepLines')=='1' and setting.get('pageBreakBefore')=='1'

def test_note_spacer_before_adds_explicit_layout_paragraph(tmp_path):
    cfg=configuration(tmp_path);cfg['note_spacer_before_item_ids']=['id0'];cfg['note_spacer_line_spacing_percent']=1200
    build(cfg,tmp_path);out=Package(tmp_path/'result.hwpx');sec=next(iter(out.sections.values()));note=next(n for n in sec if n.find('.//'+P('endNote')) is not None).find('.//'+P('endNote'));sub=note.find(P('subList'));first=sub.find(P('p'))
    assert first.get('paraPrIDRef')!=sub.findall(P('p'))[1].get('paraPrIDRef')

def test_note_image_before_label_moves_native_picture(tmp_path):
    cfg=configuration(tmp_path);cfg['join_generated_note_label']=False;cfg['note_image_before_label_item_ids']=['id0']
    build(cfg,tmp_path);out=Package(tmp_path/'result.hwpx');sec=next(iter(out.sections.values()));note=next(n for n in sec if n.find('.//'+P('endNote')) is not None).find('.//'+P('endNote'));sub=note.find(P('subList'));first=sub.find(P('p'))
    assert any(E.QName(n).localname=='pic' for n in first.iter())
