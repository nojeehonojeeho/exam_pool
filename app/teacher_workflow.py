"""Portable, fail-closed teacher worksheet handoff primitives.

Native import is a separate, reviewed stage. This module consumes an explicit
native candidate, never searches for a previous book, retypes a formula, or
equates an accepted layout reference with source-fidelity evidence.
"""
from __future__ import annotations
import copy
import hashlib
import json
from pathlib import Path
import re
import zipfile
from lxml import etree as E

HP='http://www.hancom.co.kr/hwpml/2011/paragraph'
HH='http://www.hancom.co.kr/hwpml/2011/head'
HC='http://www.hancom.co.kr/hwpml/2011/core'
NS={'p':HP,'h':HH,'c':HC}
P=lambda s:f'{{{HP}}}{s}'
H=lambda s:f'{{{HH}}}{s}'

def digest(value):
    return hashlib.sha256(value).hexdigest()

def file_hash(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def json_hash(value):
    return digest(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode())

def write_json(path,value):
    path=Path(path)
    if path.exists():raise FileExistsError(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf8')

class Package:
    def __init__(self,path):
        self.path=Path(path)
        with zipfile.ZipFile(path) as z:
            if z.testzip():raise ValueError('CORRUPT_PACKAGE')
            self.members={n:z.read(n) for n in z.namelist()}
        self.header=E.fromstring(self.members['Contents/header.xml'])
        names=sorted((n for n in self.members if re.fullmatch(r'Contents/section\d+\.xml',n)),key=lambda n:int(re.search(r'(\d+)\.xml',n)[1]))
        if not names:raise ValueError('NO_SECTION')
        self.sections={n:E.fromstring(self.members[n]) for n in names}
        manifest=E.fromstring(self.members['Contents/content.hpf'])
        self.assets={}
        for n in manifest.iter():
            if E.QName(n).localname=='item' and n.get('href'):
                href=n.get('href').lstrip('./')
                if href not in self.members and 'Contents/'+href in self.members:href='Contents/'+href
                self.assets[n.get('id')]=href
        self.catalogs={}
        for tag in ('charPr','paraPr','borderFill','tabPr','numbering','bullet','style'):
            self.catalogs[tag]={n.get('id'):n for n in self.header.iter(H(tag))}
        self.fonts={f.get('lang').lower():{n.get('id'):n for n in f.findall(H('font'))} for f in self.header.iter(H('fontface'))}
        self._style_hashes={}

    def asset_hash(self,ref):
        href=self.assets.get(ref)
        if href not in self.members:raise ValueError(f'UNRESOLVED_IMAGE:{ref}')
        return digest(self.members[href])

    def resolved(self,node,stack=()):
        """Resolve references by catalogue semantics, not numerically equal IDs."""
        refmap={'charPrIDRef':'charPr','paraPrIDRef':'paraPr','borderFillIDRef':'borderFill',
                'tabPrIDRef':'tabPr','styleIDRef':'style','nextStyleIDRef':'style'}
        attrs={}
        for key,val in sorted(node.attrib.items()):
            if key=='id':continue
            if key=='binaryItemIDRef':attrs[key]={'sha256':self.asset_hash(val)} if val else {'not_embedded':True}
            elif E.QName(node).localname=='fontRef':
                font=self.fonts.get(key,{}).get(val)
                if font is None:raise ValueError(f'UNRESOLVED_FONT:{key}:{val}')
                attrs[key]=self.resolved(font,stack)
            elif key in refmap:
                tag=refmap[key]; ident=(tag,val)
                if tag=='charPr' and val=='4294967295':attrs[key]={'inherit_paragraph_character':True};continue
                if ident in stack:attrs[key]={'cyclic_role':tag};continue
                record=self.catalogs[tag].get(val)
                if record is None:raise ValueError(f'UNRESOLVED_STYLE:{tag}:{val}')
                attrs[key]=self.resolved(record,stack+(ident,))
            elif key=='idRef' and E.QName(node).localname=='heading' and node.get('type') in ('OUTLINE','NUMBER','BULLET'):
                tag='bullet' if node.get('type')=='BULLET' else 'numbering'
                record=self.catalogs[tag].get(val)
                if record is None and val=='0' and node.get('type')=='OUTLINE':attrs[key]={'inherit_section_outline':True}
                elif record is None:raise ValueError(f'UNRESOLVED_NUMBERING:{tag}:{val}')
                else:attrs[key]=self.resolved(record,stack+((tag,val),))
            else:attrs[key]=val
        return {'tag':E.QName(node).localname,'attrs':attrs,'text':node.text or '',
                'children':[self.resolved(c,stack) for c in node]}

    def style_hash(self,tag,ident):
        if (tag,str(ident)) in self._style_hashes:return self._style_hashes[tag,str(ident)]
        node=self.catalogs[tag].get(str(ident))
        if node is None:raise ValueError(f'UNKNOWN_STYLE:{tag}:{ident}')
        value=json_hash(self.resolved(node,((tag,str(ident)),)))
        self._style_hashes[tag,str(ident)]=value
        return value

    def find_style(self,tag,semantic_hash):
        ids=[i for i in self.catalogs[tag] if self.style_hash(tag,i)==semantic_hash]
        if not ids:raise ValueError(f'PROFILE_ROLE_NOT_FOUND:{tag}:{semantic_hash}')
        return ids[0]

def profile(path):
    p=Package(path)
    catalogs={tag:[{'local_id':i,'semantic_sha256':p.style_hash(tag,i),'value':p.resolved(n,((tag,i),))} for i,n in entries.items()] for tag,entries in p.catalogs.items()}
    geometry={}
    for name,section in p.sections.items():
        geometry[name]={tag:[p.resolved(n) for n in section.iter(P(tag))] for tag in ('secPr','colPr','endNotePr','header','footer')}
    assets=[]
    for name,data in p.members.items():
        if re.fullmatch(r'Contents/masterpage\d+\.xml',name):
            node=E.fromstring(data)
            assets.append({'member':name,'sha256':digest(data),'images':[p.asset_hash(n.get('binaryItemIDRef')) for n in node.iter(f'{{{HC}}}img')],
                           'resolved_structure':p.resolved(node),
                           'geometry':[{k:n.get(k) for k in n.attrib} for n in node.iter() if E.QName(n).localname in ('sz','pos','line') ]})
    usage=[]
    for name,section in p.sections.items():
        for i,node in enumerate(section.iter(P('p'))):
            usage.append({'section':name,'paragraph_index':i,'in_note':bool(node.xpath('ancestor::p:endNote',namespaces=NS)),
                          'native_path':section.getroottree().getpath(node),
                          'containers':[E.QName(a).localname for a in node.iterancestors() if E.QName(a).localname in ('header','footer','endNote','tbl','tc')],
                          'para':p.style_hash('paraPr',node.get('paraPrIDRef')),
                          'chars':sorted({p.style_hash('charPr',r.get('charPrIDRef')) for r in node.findall(P('run'))}),
                          'has_table':bool(node.findall('.//'+P('tbl'))),'has_choices':any(c in ''.join(node.xpath('./p:run/p:t/text()',namespaces=NS)) for c in '①②③④⑤')})
    equations={json.dumps({k:n.get(k) for k in ('font','baseUnit','lineMode')},sort_keys=True) for sec in p.sections.values() for n in sec.iter(P('equation'))}
    object_styles=[]
    for name,section in p.sections.items():
        for node in section.iter():
            if E.QName(node).localname not in ('tbl','tc','equation'):continue
            # Keep ownership and layout attributes, not a flattened text sample.
            object_styles.append({'section':name,'native_path':section.getroottree().getpath(node),
                'kind':E.QName(node).localname,'attrs':dict(node.attrib),
                'border':p.resolved(p.catalogs['borderFill'][node.get('borderFillIDRef')]) if node.get('borderFillIDRef') in p.catalogs['borderFill'] else None,
                'geometry':[p.resolved(c) for c in node if E.QName(c).localname in ('sz','pos','inMargin','outMargin','cellSz','cellAddr','cellSpan','cellMargin')],
                'in_note':bool(node.xpath('ancestor::p:endNote',namespaces=NS))})
    result={'schema':'teacher-style-profile/v1','reference_sha256':file_hash(path),'catalogs':catalogs,'sections':geometry,'masterpages':assets,'object_styles':object_styles,
            'usage':usage,'equation_profiles':[json.loads(s) for s in sorted(equations)],'render_confirmation':'NOT_IMPLIED_BY_XML'}
    result['profile_sha256']=json_hash(result)
    return result

def payload(package,nodes,*,omit_notes=True):
    """Ordered native semantic checkpoint. Spaces are never erased.

    Does not prove source identity by itself; compare per owner and revision.
    HWPX rewrites split runs, so adjacent text events are joined. Paragraph and
    line breaks are retained separately; picture bytes resolve through hc:img.
    """
    events=[]
    def emit(tag,value):
        if tag=='text' and events and events[-1][0]=='text':events[-1][1]+=value
        else:events.append([tag,value])
    def visit(n):
        local=E.QName(n).localname
        if local=='endNote' and omit_notes:return
        if local in ('secPr','header','footer','linesegarray','autoNum','newNum'):return
        if local=='equation':
            emit('equation',(n.findtext(P('script')) or '').replace('\r\n','\n'));return
        if local=='img':emit('image',package.asset_hash(n.get('binaryItemIDRef')));return
        if local in ('tbl','tr','tc'):
            emit(local+':start',{k:v for k,v in sorted(n.attrib.items()) if k in ('rowCnt','colCnt')})
        if local in ('cellAddr','cellSpan','cellSz','picRect','picClip','imgRect','imgClip'):
            emit(local,dict(n.attrib));return
        if local=='t' and n.text:emit('text',n.text)
        if local in ('lineBreak','tab'):emit(local,None)
        # Non-raster drawings require an opaque checkpoint and explicit render QA.
        if local in ('line','rect','ellipse','arc','polygon','curve','connectLine','container'):
            def signature(x):
                return {'tag':E.QName(x).localname,'attrs':{k:(package.asset_hash(v) if k=='binaryItemIDRef' else v) for k,v in x.attrib.items() if k not in ('id','instid','zOrder')},'text':x.text or '', 'children':[signature(c) for c in x if E.QName(c).localname!='linesegarray']}
            emit('drawing',signature(n));return
        for child in n:
            visit(child)
            if child.tail and local=='t':emit('text',child.tail)
        if local=='p':emit('paragraph_end',None)
        if local in ('tbl','tr','tc'):emit(local+':end',None)
    for n in nodes:visit(n)
    return events

def item_ranges(section,nonquestion):
    top=list(section); starts=[]
    for i,n in enumerate(top):
        notes=n.findall('.//'+P('endNote'))
        if len(notes)>1:raise ValueError('MULTIPLE_REFERENCES_PER_ANCHOR')
        if notes:starts.append(i)
    if not starts:raise ValueError('NO_NATIVE_ANCHORS')
    ranges=[]
    for j,start in enumerate(starts):
        end=starts[j+1] if j+1<len(starts) else len(top)
        while end>start+1 and nonquestion(top[end-1]):end-=1
        ranges.append((start,end))
    return ranges

def leaked_section_metadata(notes):
    """EBS metadata tables are context candidates, never silent solution tails."""
    found=[]
    for i,note in enumerate(notes):
        for j,node in enumerate(note.find(P('subList'))):
            text=''.join(node.xpath('.//p:t/text()',namespaces=NS)).replace(' ','')
            if node.findall('.//'+P('tbl')) and '교재명' in text and 'Page' in text:found.append((i,j))
    return found

def build(config,config_base):
    """Recompose explicit source-owned native blocks, with new layout and IDs.

    Adapter scope is native_staged_reflow, not arbitrary raw HWP importing.
    The full source mapper/COM native transfer precedes this adapter.
    """
    from app.hwpx_teacher_release_repair import remove_page_frame,trim_terminal_endnote_blank_paragraphs
    base=Path(config_base)
    def bound(key):
        ref=config[key];path=(base/ref['path']).resolve()
        if file_hash(path)!=ref['sha256']:raise ValueError('INPUT_HASH_MISMATCH:'+key)
        return path
    if config.get('schema')!='teacher-native-reflow/v1':raise ValueError('CONFIG_SCHEMA')
    if config.get('mode') not in ('template_only','append_to_teacher'):raise ValueError('EXPLICIT_MODE_REQUIRED')
    if config['mode']=='append_to_teacher':raise ValueError('APPEND_REQUIRES_NATIVE_MERGE_ADAPTER_AND_PREFIX_PROOF')
    candidate=bound('native_candidate');bound('source');bound('inventory');bound('style_reference')
    p=Package(candidate)
    if len(p.sections)!=1:raise ValueError('MULTISECTION_ADAPTER_REQUIRED')
    section=next(iter(p.sections.values()));top=list(section)
    styles=config['roles']
    spacer_id=p.find_style('paraPr',styles['workspace_para_sha256'])
    body_id=p.find_style('paraPr',styles['body_para_sha256'])
    body_char=p.find_style('charPr',styles['body_char_sha256'])
    heading_ids={p.find_style('paraPr',s) for s in styles['heading_para_sha256s']}
    heading_text_hashes=set(styles['heading_text_sha256s'])
    def is_heading(n):
        value=''.join(n.xpath('./p:run/p:t/text()',namespaces=NS))
        return n.get('paraPrIDRef') in heading_ids and digest(value.encode()) in heading_text_hashes
    def nonquestion(n):
        if n.find('.//'+P('endNote')) is not None:return False
        return n.get('paraPrIDRef')==spacer_id or is_heading(n) or not payload(p,[n]) or payload(p,[n])==[['paragraph_end',None]]
    ranges=item_ranges(section,nonquestion)
    inventory=json.loads(bound('inventory').read_text(encoding='utf-8-sig'))
    ids=config['candidate_item_ids']
    if len(ids)!=len(ranges) or len(set(ids))!=len(ids):raise ValueError('CANDIDATE_IDS_NOT_BIJECTIVE')
    inventory_ids=[str(r['id']) for r in inventory['items']]
    if set(ids)!=set(inventory_ids):raise ValueError('SOURCE_CANDIDATE_SCOPE_MISMATCH')
    selected=config['selected_item_ids']
    if not selected or len(selected)!=len(set(selected)) or not set(selected)<=set(ids):raise ValueError('SELECTION_INVALID')
    if [i for i in ids if i in selected]!=selected:raise ValueError('SOURCE_ORDER_REQUIRED')
    note_column_starts=config.get('note_column_start_item_ids',[])
    if not set(note_column_starts)<=set(selected):raise ValueError('LAYOUT_EXCEPTION_OUTSIDE_SELECTION')
    if note_column_starts:
        proof=config['layout_exception_evidence']
        if file_hash(base/proof['path'])!=proof['sha256']:raise ValueError('LAYOUT_EXCEPTION_EVIDENCE_HASH')
    note_keep_with_next=set(config.get('note_keep_with_next_item_ids',[]))
    if not note_keep_with_next<=set(selected):raise ValueError('LAYOUT_EXCEPTION_OUTSIDE_SELECTION')
    note_page_break_before=set(config.get('note_page_break_before_item_ids',[]))
    if not note_page_break_before<=set(selected):raise ValueError('LAYOUT_EXCEPTION_OUTSIDE_SELECTION')
    # Question-body pagination is distinct from the endnote-only controls
    # above.  It is deliberately opt-in and evidence-bound: a question is
    # moved to a new physical page only when a rendered semantic endpoint
    # proves that its usable writing space is too small.  Do not infer this
    # from paragraph counts or cached line heights.
    question_page_break_before=set(config.get('question_page_break_before_item_ids',[]))
    if not question_page_break_before<=set(selected):raise ValueError('LAYOUT_EXCEPTION_OUTSIDE_SELECTION')
    if question_page_break_before:
        proof=config.get('question_layout_exception_evidence')
        if not isinstance(proof,dict) or not proof.get('path') or not proof.get('sha256'):
            raise ValueError('QUESTION_LAYOUT_EXCEPTION_EVIDENCE_REQUIRED')
        if file_hash(base/proof['path'])!=proof['sha256']:
            raise ValueError('QUESTION_LAYOUT_EXCEPTION_EVIDENCE_HASH')
    note_spacer_before=set(config.get('note_spacer_before_item_ids',[]))
    if not note_spacer_before<=set(selected):raise ValueError('LAYOUT_EXCEPTION_OUTSIDE_SELECTION')
    spacer_percent=config.get('note_spacer_line_spacing_percent',1000)
    if type(spacer_percent) is not int or spacer_percent<100:raise ValueError('NOTE_SPACER_PERCENT_INVALID')
    note_image_before_label=set(config.get('note_image_before_label_item_ids',[]))
    if not note_image_before_label<=set(selected):raise ValueError('LAYOUT_EXCEPTION_OUTSIDE_SELECTION')
    para_clone_cache={}
    spacer_clone_cache={}
    def apply_keep_with_next(paragraph, page_break_before=False):
        source_id=paragraph.get('paraPrIDRef')
        if source_id is None:return
        if source_id in para_clone_cache:
            paragraph.set('paraPrIDRef',para_clone_cache[source_id])
            if page_break_before:
                clone=p.catalogs['paraPr'][para_clone_cache[source_id]]
                setting=next((x for x in clone.iter() if E.QName(x).localname=='breakSetting'),None)
                if setting is None:raise ValueError('BREAK_SETTING_MISSING')
                setting.set('pageBreakBefore','1')
            return
        source=p.catalogs['paraPr'].get(source_id)
        if source is None:raise ValueError('UNKNOWN_NOTE_PARAPR:'+str(source_id))
        clone=copy.deepcopy(source)
        container=next((parent for parent in p.header.iter() if source in list(parent)),None)
        if container is None:raise ValueError('PARAPR_CONTAINER_MISSING')
        next_id=str(max([int(x) for x in p.catalogs['paraPr'] if str(x).isdigit()] or [0])+1+len(para_clone_cache));clone.set('id',next_id)
        setting=next((x for x in clone.iter() if E.QName(x).localname=='breakSetting'),None)
        if setting is None:raise ValueError('BREAK_SETTING_MISSING')
        setting.set('keepWithNext','1');setting.set('keepLines','1')
        if page_break_before:setting.set('pageBreakBefore','1')
        container.append(clone);p.catalogs['paraPr'][next_id]=clone;para_clone_cache[source_id]=next_id;paragraph.set('paraPrIDRef',next_id)
    def insert_note_spacer(sublist, first_paragraph):
        source_id=first_paragraph.get('paraPrIDRef')
        if source_id is None:raise ValueError('UNKNOWN_NOTE_PARAPR')
        key=(source_id,spacer_percent)
        next_id=spacer_clone_cache.get(key)
        if next_id is None:
            source=p.catalogs['paraPr'].get(source_id)
            if source is None:raise ValueError('UNKNOWN_NOTE_PARAPR:'+str(source_id))
            clone=copy.deepcopy(source)
            container=next((parent for parent in p.header.iter() if source in list(parent)),None)
            if container is None:raise ValueError('PARAPR_CONTAINER_MISSING')
            next_id=str(max([int(x) for x in p.catalogs['paraPr'] if str(x).isdigit()] or [0])+1+len(para_clone_cache)+len(spacer_clone_cache));clone.set('id',next_id)
            line=next((x for x in clone.iter() if E.QName(x).localname=='lineSpacing'),None)
            if line is None:
                line=E.Element(H('lineSpacing'));clone.append(line)
            line.set('type','PERCENT');line.set('value',str(spacer_percent));line.set('unit','HWPUNIT')
            container.append(clone);p.catalogs['paraPr'][next_id]=clone;spacer_clone_cache[key]=next_id
        spacer=E.Element(P('p'),paraPrIDRef=next_id,styleIDRef=first_paragraph.get('styleIDRef','0'),pageBreak='0',columnBreak='0',merged='0')
        run=E.SubElement(spacer,P('run'),charPrIDRef=first_paragraph.find(P('run')).get('charPrIDRef','0') if first_paragraph.find(P('run')) is not None else '0')
        E.SubElement(run,P('t')).text=''
        sublist.insert(0,spacer)
    # Explicit source-owned header manifest; package-wide image1 substitution is forbidden.
    header=config['header']
    all_master_imgs=[]
    for name,data in p.members.items():
        if re.fullmatch(r'Contents/masterpage\d+\.xml',name):
            root=E.fromstring(data)
            all_master_imgs.extend(p.asset_hash(n.get('binaryItemIDRef')) for n in root.iter(f'{{{HC}}}img'))
    if not all_master_imgs or set(all_master_imgs)!=set(header['allowed_asset_sha256s']):raise ValueError('SOURCE_HEADER_BINDING_MISMATCH')
    if header['source_sha256']!=config['source']['sha256']:raise ValueError('HEADER_WRONG_SOURCE')
    changes=remove_page_frame(p.header,[section])
    notes=section.findall('.//'+P('endNote')) # runtime-resolved, never an implicit global
    trims=trim_terminal_endnote_blank_paragraphs(section)
    exclusions=config.get('note_exclusions',[])
    exclusion_changes=[]
    for ex in exclusions:
        if ex['item_id'] not in ids or ex['reason']!='source_section_metadata_not_solution':raise ValueError('UNREVIEWED_NOTE_EXCLUSION')
        proof=ex['evidence'];proof_path=(base/proof['path']).resolve()
        if file_hash(proof_path)!=proof['sha256']:raise ValueError('EXCLUSION_EVIDENCE_HASH')
        note=notes[ids.index(ex['item_id'])];body=note.find(P('subList'));node=body[int(ex['paragraph_index'])]
        if json_hash(payload(p,[node]))!=ex['payload_sha256']:raise ValueError('EXCLUSION_CONTENT_CHANGED')
        if not node.findall('.//'+P('tbl')):raise ValueError('EXCLUSION_NOT_METADATA_TABLE')
        body.remove(node);exclusion_changes.append(ex)
    if leaked_section_metadata(notes):raise ValueError('ENDNOTE_SECTION_METADATA_LEAK_REQUIRES_SOURCE_BOUNDARY_REVIEW')
    spacer=copy.deepcopy(next(n for n in top if n.get('paraPrIDRef')==spacer_id))
    if payload(p,[spacer])!=[['paragraph_end',None]]:raise ValueError('WORKSPACE_HAS_CONTENT')
    prefix=[copy.deepcopy(n) for n in top[:ranges[0][0]]]
    # Discard old chapter text; preserve only document/column/header control runs.
    for n in prefix:
        for t in n.xpath('./p:run/p:t',namespaces=NS):t.text=''
    # Chapter headings may share the body paragraph style. Content-bound
    # identification is mandatory; a body-style ID is never a heading filter.
    heading_for_start={};active_heading=None
    for i,n in enumerate(top):
        if is_heading(n):active_heading=n
        if i in {a for a,b in ranges}:heading_for_start[i]=active_heading
    generated=prefix;plan=[];expected=[];page=1;slot=0;right_height=0;prior_heading=None
    def cached_height(nodes):
        return sum(sum(int(l.get('vertsize','0'))+int(l.get('spacing','0')) for l in n.findall('./'+P('linesegarray')+'/'+P('lineseg'))) or 1840 for n in nodes)
    for number,item_id in enumerate(selected,1):
        start,end=ranges[ids.index(item_id)]
        nodes=[copy.deepcopy(n) for n in top[start:end] if not nonquestion(n)]
        if not nodes:raise ValueError('EMPTY_ITEM:'+item_id)
        chapter=heading_for_start[start]
        heading_added=False
        if chapter is not None and chapter is not prior_heading:
            if plan:page+=1
            slot=0;heading_added=True
            heading=copy.deepcopy(chapter)
            # The initial section controls already live in the prefix.
            for c in heading.xpath('./p:run/p:secPr | ./p:run/p:ctrl',namespaces=NS):c.getparent().remove(c)
            heading.set('pageBreak','1' if plan else '0');heading.set('columnBreak','0')
            generated.append(heading);prior_heading=chapter
        height=cached_height(nodes)
        # A manual question break is a physical-layout repair, not merely a
        # paraPr keep flag.  It resets the slot before the normal 3-up plan so
        # the current question starts at a page top.  A chapter heading already
        # performs that reset, so it must not create a blank intervening page.
        force_question_page_break=item_id in question_page_break_before and bool(plan) and not heading_added
        if force_question_page_break:
            slot=0;page+=1
        if slot>=3 or (slot==2 and right_height+height+config['layout']['reserved_right_gap_hwpunit']>config['layout']['column_height_hwpunit']):slot=0;page+=1
        for n in nodes:n.set('pageBreak','0');n.set('columnBreak','0')
        # Do not mutate the shared paragraph style: ``pageBreakBefore`` on a
        # cloned paraPr caused Hanword's PDF exporter to omit a trailing
        # source-owned range.  An empty break-only paragraph is also ignored
        # by this exporter in a two-column story.  The native pageBreak
        # attribute on the actual next question anchor is the same mechanism
        # used by ordinary planned page transitions and survives HWP/HWPX
        # roundtrip without sharing a style ID.
        if slot==0 and plan and not heading_added:
            nodes[0].set('pageBreak','1')
        if slot==1:nodes[0].set('columnBreak','1')
        if slot==2:generated.append(copy.deepcopy(spacer))
        note=nodes[0].find('.//'+P('endNote'))
        if note is None:raise ValueError('ANCHOR_NOT_FIRST_PARAGRAPH')
        note.set('number',str(number))
        for a in note.findall('.//'+P('autoNum')):a.set('num',str(number))
        if config.get('join_generated_note_label'):
            body=note.find(P('subList'));paragraphs=list(body)
            if len(paragraphs)<2:raise ValueError('NOTE_BODY_MISSING')
            label,first=paragraphs[:2]
            label_text=''.join(label.xpath('.//p:t/text()',namespaces=NS))
            if not label_text.lstrip().startswith('정답:'):raise ValueError('GENERATED_ANSWER_LABEL_NOT_IDENTIFIED')
            # Join only the generated answer heading, never two source prose
            # paragraphs. Native numbering stays attached, token order unchanged.
            lead=[copy.deepcopy(r) for r in label.findall(P('run'))]
            br=E.Element(P('run'),charPrIDRef=body_char);E.SubElement(E.SubElement(br,P('t')),P('lineBreak'))
            for pos,r in enumerate(lead+[br]):first.insert(pos,r)
            first.set('paraPrIDRef',label.get('paraPrIDRef'));body.remove(label)
            for pic in first.findall('.//'+P('pic')):
                for pos in pic.iter():
                    if E.QName(pos).localname=='pos' and pos.get('treatAsChar')=='1':pos.set('affectLSpacing','1')
        if item_id in note_column_starts:note.find(P('subList')+'/'+P('p')).set('columnBreak','1')
        if item_id in note_keep_with_next or item_id in note_page_break_before:
            apply_keep_with_next(note.find(P('subList')+'/'+P('p')), page_break_before=item_id in note_page_break_before)
        if item_id in note_spacer_before:
            sublist=note.find(P('subList'));first_note_p=sublist.find(P('p'))
            if first_note_p is None:raise ValueError('NOTE_BODY_MISSING')
            insert_note_spacer(sublist,first_note_p)
        if item_id in note_image_before_label:
            sublist=note.find(P('subList'));paragraphs=list(sublist.findall(P('p')))
            if len(paragraphs)<2:
                if not any(E.QName(n).localname=='pic' for n in sublist.iter()):raise ValueError('NOTE_BODY_MISSING')
            else:
                first_note_p,source_p=paragraphs[:2]
                first_run=first_note_p.find(P('run'))
                if first_run is None:raise ValueError('NOTE_BODY_MISSING')
                pics=[node for node in source_p.iter() if E.QName(node).localname=='pic']
                if not pics:raise ValueError('NOTE_IMAGE_NOT_FOUND')
                for pic in pics:
                    parent=pic.getparent();parent.remove(pic);first_run.insert(0,pic)
        note_page_starts=set(config.get('note_page_start_item_ids',[]))
        if item_id in note_page_starts:
            # A native page break on the first note paragraph is the only
            # accepted stronger fallback for a title/figure pair that cannot
            # be kept in one column.  It is validated by COM/B4 render.
            note.find(P('subList')+'/'+P('p')).set('pageBreak','1')
        if item_id in set(config.get('inline_note_images_item_ids',[])):
            # Some Hanword builds float a treat-as-character figure from the
            # remaining column while leaving its generated answer label behind.
            # Normalize only the explicitly evidenced item; payload/script is
            # unchanged and the B4 render remains the deciding evidence.
            for pic in note.findall('.//'+P('pic')):
                pic.set('textWrap','NONE')
                for pos in pic.iter():
                    if E.QName(pos).localname!='pos':continue
                    pos.set('treatAsChar','1');pos.set('flowWithText','1');pos.set('affectLSpacing','1')
        if item_id in set(config.get('note_image_para_anchor_item_ids',[])):
            for pic in note.findall('.//'+P('pic')):
                for pos in pic.iter():
                    if E.QName(pos).localname!='pos':continue
                    pos.set('treatAsChar','1');pos.set('flowWithText','1');pos.set('affectLSpacing','1')
                    pos.set('vertRelTo','PARA');pos.set('horzRelTo','PARA');pos.set('vertAlign','TOP');pos.set('horzAlign','LEFT')
        expected.append({'id':item_id,'body':payload(p,nodes),'note':payload(p,list(note),omit_notes=False)})
        generated.extend(nodes)
        plan.append({'id':item_id,'slot':slot+1,'page_group':page,'cached_height':height,'physical_qa':'REQUIRED'})
        if slot==1:right_height=height
        slot+=1
    terminal=E.Element(P('p'),id='0',paraPrIDRef=body_id,styleIDRef='0',pageBreak='1',columnBreak='0',merged='0')
    E.SubElement(E.SubElement(terminal,P('run'),charPrIDRef=body_char),P('t'))
    generated.append(terminal)
    for n in list(section):section.remove(n)
    for i,n in enumerate(generated):n.set('id',str(8000000+i));section.append(n)
    for n in section.findall('.//'+P('linesegarray')):n.getparent().remove(n)
    for place in section.findall('.//'+P('endNotePr')+'/'+P('placement')):place.set('place','END_OF_DOCUMENT')
    if not section.findall('.//'+P('endNotePr')+'/'+P('placement')):raise ValueError('ENDNOTE_PLACEMENT_MISSING')
    p.members['Contents/header.xml']=E.tostring(p.header,xml_declaration=True,encoding='UTF-8',standalone=True)
    p.members['Contents/section0.xml']=E.tostring(section,xml_declaration=True,encoding='UTF-8',standalone=True)
    out=(base/config['output']).resolve()
    if out.exists():raise FileExistsError(out)
    out.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
        for name,data in p.members.items():z.writestr(name,data)
    report={'schema':'teacher-native-reflow-result/v1','status':'BUILT_REQUIRES_QA','final':False,'adapter':'native_staged_reflow',
            'config_sha256':json_hash(config),'candidate_sha256':file_hash(candidate),'output_sha256':file_hash(out),
            'selected_item_ids':selected,'source_scope_count':len(inventory_ids),'represented_count':len(selected),
            'page_plan':plan,'expected':expected,'page_border_changes':changes,'terminal_blank_removals':trims,
            'native_note_count':len(selected),'source_native_note_count':len(notes),'header_binding':header}
    report['note_exclusions']=exclusion_changes
    report['joined_generated_note_labels']=bool(config.get('join_generated_note_label'))
    report['note_column_start_item_ids']=note_column_starts
    report['note_keep_with_next_item_ids']=sorted(note_keep_with_next)
    report['note_page_break_before_item_ids']=sorted(note_page_break_before)
    report['question_page_break_before_item_ids']=sorted(question_page_break_before)
    report['question_page_break_mechanism']='native_question_anchor_page_break_attribute' if question_page_break_before else None
    report['note_spacer_before_item_ids']=sorted(note_spacer_before)
    report['note_spacer_line_spacing_percent']=spacer_percent
    report['note_image_before_label_item_ids']=sorted(note_image_before_label)
    report['note_page_start_item_ids']=sorted(set(config.get('note_page_start_item_ids',[])))
    report['inline_note_images_item_ids']=sorted(set(config.get('inline_note_images_item_ids',[])))
    report['note_image_para_anchor_item_ids']=sorted(set(config.get('note_image_para_anchor_item_ids',[])))
    write_json(out.with_suffix('.build.json'),report)
    return report

REQUIRED={'source_scope','source_payload','style_roles','font_render','header_render','workspace','endnote_order','com_roundtrip','whole_question_transfer','visual_qa'}

def release_gate(run,base):
    """Every report is nonempty, target-bound, versioned, and independently true.

    Existing book acceptance cannot fulfill a new run. Aggregator computes only
    evidence completeness; it does not manufacture observations or attestations.
    """
    base=Path(base);fail=[]
    if not isinstance(run,dict):return {'schema':'teacher-release-result/v1','status':'BLOCKED','final':False,'scope_count':0,'failures':['RUN_NOT_OBJECT']}
    if run.get('schema')!='teacher-release/v1':fail.append('RUN_SCHEMA')
    targets=run.get('targets',{})
    if not isinstance(targets,dict):targets={};fail.append('TARGETS_NOT_OBJECT')
    if set(targets)!={'hwp','hwpx'}:fail.append('TARGET_PAIR_REQUIRED')
    for key,ref in targets.items():
        try:
            if file_hash(base/ref['path'])!=ref['sha256']:fail.append('TARGET_HASH:'+key)
        except (KeyError,TypeError,OSError):fail.append('TARGET_MISSING:'+str(key))
    reports=run.get('evidence',{})
    if not isinstance(reports,dict):reports={};fail.append('EVIDENCE_NOT_OBJECT')
    if set(reports)!=REQUIRED:fail.append('REQUIRED_EVIDENCE_SET')
    for kind in REQUIRED:
        try:
            ref=reports[kind];path=base/ref['path']
            if file_hash(path)!=ref['sha256']:raise ValueError('REPORT_HASH')
            r=json.loads(path.read_text(encoding='utf8'))
            if r['schema']!='teacher-evidence/v1' or r['kind']!=kind:raise ValueError('REPORT_SCHEMA')
            if r['target_sha256']!={k:v['sha256'] for k,v in targets.items()}:raise ValueError('STALE_TARGET')
            checks=r['checks']
            if not isinstance(checks,dict) or not checks or any(v is not True for v in checks.values()):raise ValueError('CHECKS_NOT_CLOSED')
            if r['status']!='PASS' or r['open_items']!=[]:raise ValueError('OPEN_ITEMS')
            if r['scope_ids']!=run['scope_ids'] or not r['scope_ids']:raise ValueError('SCOPE_MISMATCH')
            obs=r['observations']
            if not isinstance(obs,list) or not obs:raise ValueError('EMPTY_OBSERVATIONS')
            for o in obs:
                if not o['method'] or file_hash(base/o['artifact']['path'])!=o['artifact']['sha256']:raise ValueError('OBSERVATION_ARTIFACT')
            if kind=='endnote_order':
                b=r['boundary']
                if 'title_backcalculation' in (b['last_question_method'],b['first_note_method']):raise ValueError('BOUNDARY_INFERRED')
                if any(type(b[k]) is not int or b[k]<1 for k in ('last_question_page','first_note_page')):raise ValueError('BOUNDARY_PAGE_INVALID')
                if not b['last_question_method'] or not b['first_note_method'] or b['first_note_page']!=b['last_question_page']+1:raise ValueError('BOUNDARY_NOT_ADJACENT')
            if kind=='font_render':
                if r['coverage']!='all_applicable_roles':raise ValueError('FONT_ROLE_COVERAGE')
                roles=r['role_renders'];required=r['required_roles']
                if not roles or not required or len(set(required))!=len(required) or sorted(t['role'] for t in roles)!=sorted(required):raise ValueError('FONT_ROLE_ROWS')
                for t in roles:
                    if t['font_match'] is not True or not t['actual_fonts'] or not t['expected_fonts'] or t['actual_fonts']!=t['expected_fonts']:raise ValueError('FONT_SUBSTITUTION')
                    if not t['pages'] or any(type(v) is not int or v<1 for v in t['pages']):raise ValueError('FONT_RENDER_PAGES')
                    if file_hash(base/t['render_artifact']['path'])!=t['render_artifact']['sha256']:raise ValueError('FONT_RENDER_ARTIFACT')
            if kind=='whole_question_transfer':
                rows=r['transfers']
                if not rows or not any(t['operation']=='move' for t in rows):raise ValueError('TRANSFER_MOVE_MISSING')
                for t in rows:
                    if t['id'] not in r['scope_ids'] or t['whole_question'] is not True or t['readback'] is not True or t['payload_equal'] is not True:raise ValueError('TRANSFER_ROW_FAIL')
                    if file_hash(base/t['readback_artifact']['path'])!=t['readback_artifact']['sha256']:raise ValueError('TRANSFER_READBACK_HASH')
                    if not re.fullmatch('[0-9a-f]{64}',t['before_payload_sha256']) or t['before_payload_sha256']!=t['after_payload_sha256']:raise ValueError('TRANSFER_PAYLOAD_HASH')
            if kind=='visual_qa':
                if type(r['physical_page_count']) is not int or r['physical_page_count']<1 or r['automated_pages']!=list(range(1,r['physical_page_count']+1)):raise ValueError('RENDER_COVERAGE')
                if not r['human_reviewed_pages'] or any(type(v) is not int or v not in r['automated_pages'] for v in r['human_reviewed_pages']):raise ValueError('HUMAN_REPRESENTATIVE_MISSING')
        except (KeyError,TypeError,OSError,ValueError) as e:fail.append(kind+':'+str(e))
    ids=run.get('scope_ids',[])
    if not isinstance(ids,list) or any(not isinstance(i,str) or not i for i in ids):ids=[];fail.append('SCOPE_INVALID')
    if not ids or len(set(ids))!=len(ids):fail.append('SCOPE_EMPTY_OR_DUPLICATE')
    return {'schema':'teacher-release-result/v1','status':'PASS' if not fail else 'BLOCKED','final':not fail,
            'scope_count':len(ids),'failures':fail,'claim':'Evidence completeness only; reviewer observations remain auditable.'}
