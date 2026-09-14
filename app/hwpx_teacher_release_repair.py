"""Isolated teacher-layout repairs; never replace a package's style catalogue.

The caller supplies a source-owned logo and explicitly reviews formula layouts.
Existing shared border records and mathematical token sequences are preserved.
"""
from __future__ import annotations
import copy
import re
from lxml import etree as E

P='http://www.hancom.co.kr/hwpml/2011/paragraph'
H='http://www.hancom.co.kr/hwpml/2011/head'
NS={'p':P,'h':H}

def remove_page_frame(header, sections):
    records=header.find('.//{%s}borderFills'%H)
    if records is None: raise ValueError('BORDER_CATALOGUE_MISSING')
    new_id=str(max(int(x.get('id')) for x in records)+1)
    record=copy.deepcopy(records[0]); record.set('id',new_id)
    for node in record:
        if E.QName(node).localname.endswith('Border'): node.set('type','NONE')
    records.append(record); records.set('itemCnt',str(len(records)))
    changes=[]
    for section in sections:
        for node in section.xpath('.//p:pageBorderFill',namespaces=NS):
            changes.append({'before':node.get('borderFillIDRef'),'after':new_id,'type':node.get('type')})
            node.set('borderFillIDRef',new_id)
    return changes

def wrap_top_level_equalities(script, max_chars=64):
    """Display-only breaks before a top-level equality, never inside a group."""
    if '#' in script or len(script)<=max_chars: return script
    depth=0; points=[]
    for i,c in enumerate(script):
        if c in '{([': depth+=1
        elif c in '})]': depth-=1
        elif c=='=' and depth==0 and (i==0 or script[i-1] not in '<>!=') and (i+1==len(script) or script[i+1]!='='):
            points.append(i)
        if depth<0: return script
    if depth!=0 or not points: return script
    cuts=[]; start=0
    for i in points:
        if i-start>=max_chars//2: cuts.append(i); start=i
    result=script
    for i in reversed(cuts): result=result[:i]+' # '+result[i:]
    if re.sub(r'\s|#','',result)!=re.sub(r'\s|#','',script): raise ValueError('MATH_TOKEN_CHANGED')
    return result

def resolved_page_frames(header, sections):
    records={n.get('id'):n for n in header.xpath('.//h:borderFill',namespaces=NS)}
    return [[(E.QName(c).localname,c.get('type')) for c in records[b.get('borderFillIDRef')] if E.QName(c).localname.endswith('Border')]
            for sec in sections for b in sec.xpath('.//p:pageBorderFill',namespaces=NS)]
