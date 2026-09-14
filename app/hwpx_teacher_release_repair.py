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

def main_question_range(section, note_index, *, trailing_nonquestion=None):
    """Half-open main paragraph range, never just the native anchor paragraph.

    Caller verifies these positions against the actual COM selection before
    copying, and supplies profile-specific trailing spacer/title recognition.
    """
    nodes=list(section)
    starts=[i for i,node in enumerate(nodes) if node.find('.//{%s}endNote'%P) is not None]
    if not 0<=note_index<len(starts):raise IndexError(note_index)
    start=starts[note_index]
    end=starts[note_index+1] if note_index+1<len(starts) else len(nodes)
    if trailing_nonquestion:
        while end>start+1 and trailing_nonquestion(nodes[end-1]):end-=1
    return start,end

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

def export_b4_pdf(hwp, path):
    """Hanword HPrint dimensions are HWPUNIT, not DEVMODE tenths of mm.

    Caller owns the secured serial session. No global printer setting changes.
    A4 SaveAs output must not be resized and presented as native B4 evidence.
    """
    from pathlib import Path
    import time
    import fitz
    path=Path(path).resolve()
    if path.exists():raise FileExistsError(path)
    p=hwp.HParameterSet.HPrint
    hwp.HAction.GetDefault('PrintToPDFEx',p.HSet)
    p.filename=str(path);p.PrinterName='Hancom PDF'
    p.PrinterPaperSize=0;p.PrinterPaperWidth=72852;p.PrinterPaperLength=103180
    p.PrintMethod=1;p.ZoomX=100;p.ZoomY=100;p.PrintToFile=1
    if not hwp.HAction.Execute('PrintToPDFEx',p.HSet):raise RuntimeError('B4_PDF_EXPORT_FAILED')
    for _ in range(20):
        if path.exists() and path.stat().st_size:break
        time.sleep(1)
    with fitz.open(path) as doc:
        sizes=[(p.rect.width,p.rect.height) for p in doc]
    if not sizes or any(abs(w-728.52)>1.5 or abs(h-1031.80)>1.5 for w,h in sizes):
        raise RuntimeError('B4_PDF_MEDIABOX_MISMATCH')
    return {'pages':len(sizes),'sizes_pt':sorted(set(sizes)),'native_export':True}
