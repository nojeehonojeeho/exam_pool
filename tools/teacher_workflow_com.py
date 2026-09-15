"""Serial secure pilot roundtrip with an external deadline and shared lease.

A timeout preserves the worker, owned HWP, log and lease for safe recovery;
neither supervisor nor worker terminates unrelated processes. No auto-retry.
"""
from __future__ import annotations
import argparse,json,os,subprocess,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.teacher_workflow import Package,P,NS,payload,file_hash,write_json

def arguments():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--lock',type=Path,required=True);p.add_argument('--deadline',type=float,default=120)
    p.add_argument('--transfer',type=int,nargs='*')
    p.add_argument('--transfer-all',action='store_true',help='exercise every source-owned question by native copy and native cut/move')
    p.add_argument('--item-ids-json',type=Path,help='JSON evidence with scope_ids in source order; required for a full source-owned ledger')
    p.add_argument('--worker',action='store_true')
    p.add_argument('--visible',action='store_true',help='show the isolated owned HWP window for a one-shot clipboard diagnostic')
    return p.parse_args()

def validate_transfer_selection(indices,count):
    if len(indices)<2 or len(set(indices))!=len(indices) or any(i<0 or i>=count for i in indices):
        raise ValueError('TRANSFER_REQUIRES_TWO_OR_MORE_DISTINCT_IN_RANGE_ITEMS')

def item_ranges(package):
    """Return native-endnote anchored main-story ranges, excluding only proven context tails."""
    section=next(iter(package.sections.values()));top=list(section)
    starts=[i for i,node in enumerate(top) if node.find('.//'+P('endNote')) is not None]
    ranges=[]
    for ordinal,start in enumerate(starts):
        end=starts[ordinal+1] if ordinal+1<len(starts) else len(top)
        while end>start+1:
            node=top[end-1];text=''.join(node.xpath('./p:run/p:t/text()',namespaces=NS))
            if payload(package,[node])==[['paragraph_end',None]] or ' · 유형편 · ' in text or ' · 실전편 · ' in text:end-=1
            else:break
        ranges.append((start,end))
    return top,ranges

def payload_sha256(value):
    import hashlib
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf8')).hexdigest()

def scope_ids_from(path,count):
    if path is None:return [f'ordinal:{index+1}' for index in range(count)]
    source=json.loads(path.read_text(encoding='utf-8-sig'))
    ids=source.get('scope_ids',source if isinstance(source,list) else [])
    if not isinstance(ids,list) or len(ids)!=count or any(not isinstance(value,str) or not value for value in ids):
        raise ValueError('TRANSFER_ITEM_IDS_SCOPE_MISMATCH')
    return ids

def worker(a):
    import psutil,win32gui
    from app.integrations.hwp_security import create_secure_hwp,security_snapshot
    from app.hwpx_teacher_release_repair import export_b4_pdf
    report={'schema':'teacher-com-pilot/v1','status':'FAIL','source_sha256':file_hash(a.input),'security':security_snapshot(),'sessions':[]}
    step_path=a.out/'progress.json'
    def step(name):
        step_path.write_text(json.dumps({'step':name,'time':time.time(),'worker_pid':os.getpid()}),encoding='utf8')
    def pids():return {p.pid for p in psutil.process_iter(['name']) if (p.info['name'] or '').lower()=='hwp.exe'}
    def popups():
        result=[]
        def visit(hwnd,_):
            title=win32gui.GetWindowText(hwnd)
            if win32gui.IsWindowVisible(hwnd) and any(t in title.lower() for t in ('파일 접근','file access','pathchecker')):result.append(title)
        win32gui.EnumWindows(visit,None)
        return result
    hwp=None;owned=set()
    def open_session(path,fmt):
        nonlocal hwp,owned
        before=pids();step('create_secure_session')
        hwp=create_secure_hwp(new=True,visible=bool(a.visible),on_quit=False);owned=pids()-before
        registered=getattr(hwp,'_hwp_security_registration').returned
        row={'input':str(path),'input_sha256':file_hash(path),'register_module_return':registered,
             'visible_session':bool(a.visible),'owned_pids':sorted(owned)};report['sessions'].append(row)
        if registered is not True:raise RuntimeError('HWP_SECURITY_MODULE_NOT_ACTIVE')
        step('open_'+fmt)
        if not hwp.open(str(path),format=fmt,arg='forceopen:true;suspendpassword:true'):raise RuntimeError('OPEN_FAILED')
        row['approval_windows']=popups()
        if row['approval_windows']:raise RuntimeError('HWP_SECURITY_MODULE_NOT_ACTIVE')
        return row
    def save(path,fmt):
        if path.exists():raise FileExistsError(path)
        step('save_'+fmt)
        if not hwp.save_as(str(path),format=fmt):raise RuntimeError('SAVE_FAILED')
        if popups():raise RuntimeError('HWP_SECURITY_MODULE_NOT_ACTIVE')
    def quit_session(row):
        nonlocal hwp
        # `pyhwpx.Hwp.quit()` clears only the active document before asking
        # HwpObject to quit.  A native clipboard transfer intentionally opens
        # a source and a destination tab, so clear every *owned* tab with the
        # documented discard-close operation first.  This is graceful COM
        # shutdown, never a process kill, and keeps the saved transfer
        # artifacts while discarding the temporary source-tab mutations.
        step('graceful_close_owned_documents')
        documents=hwp.hwp.XHwpDocuments
        before_count=int(documents.Count);closed=0
        for index in range(before_count-1,-1,-1):
            document=documents[index]
            document.SetActive_XHwpDocument()
            try:document.Close(isDirty=False)
            except TypeError:document.Close(False)
            closed+=1
        remaining=int(documents.Count)
        row['graceful_document_close']={'before_count':before_count,'close_calls':closed,'after_count':remaining}
        step('quit')
        if remaining:hwp.quit(save=False)
        else:hwp.hwp.Quit()
        hwp=None
        deadline=time.monotonic()+15
        while owned & pids() and time.monotonic()<deadline:time.sleep(.2)
        row['owned_pids_remaining']=sorted(owned&pids())
        if row['owned_pids_remaining']:raise RuntimeError('OWNED_PROCESS_DID_NOT_EXIT')
    def paste_once(label):
        """Use the pyhwpx selection-option paste once when HAction.Run reports False.

        Hanword 2024 sometimes returns False for ``Paste`` while the clipboard
        is already a native HWP payload.  The explicit HSelectionOpt action is
        a bounded compatibility fallback, not an auto-retry loop; subsequent
        readback/anchor QA remains mandatory.
        """
        if hwp.Paste():return True
        hwp.paste(option=4)
        time.sleep(.4)
        return True
    try:
        if a.transfer is None and not a.transfer_all:
            input_format='HWP' if a.input.suffix.lower()=='.hwp' else 'HWPX'
            row=open_session(a.input,input_format)
            save(a.out/'pilot.hwp','HWP');save(a.out/'pilot.hwpx','HWPX');row['gui_pages']=int(hwp.PageCount)
            quit_session(row)
            for fmt in ('HWP','HWPX'):
                row=open_session(a.out/('pilot.'+fmt.lower()),fmt)
                save(a.out/(fmt.lower()+'-readback.hwpx'),'HWPX');row['gui_pages']=int(hwp.PageCount)
                step('physical_b4_export_'+fmt);row['b4_pdf']=export_b4_pdf(hwp,a.out/(fmt.lower()+'-b4.pdf'))
                row['gui_pdf_page_count_match'] = row['gui_pages'] == row['b4_pdf'].get('pages')
                quit_session(row)
        else:
            import win32clipboard,pythoncom
            from app.hwp_native_clipboard import wait_native_payload
            pythoncom.CoInitialize()
            report['sta_message_pump']=True
            pkg=Package(a.input.with_suffix('.hwpx'));top,all_ranges=item_ranges(pkg)
            all_ids=scope_ids_from(a.item_ids_json,len(all_ranges))
            if a.transfer_all and a.transfer is not None:raise ValueError('TRANSFER_ALL_AND_EXPLICIT_SELECTION_CONFLICT')
            selection=list(range(len(all_ranges))) if a.transfer_all else list(a.transfer)
            validate_transfer_selection(selection,len(all_ranges))
            ranges=[all_ranges[index] for index in selection]
            expected={
                index:{'id':all_ids[index],'payload_sha256':payload_sha256(payload(pkg,top[start:end]))}
                for index,(start,end) in zip(selection,ranges)
            }
            row=open_session(a.input,'HWP');hwp.add_tab();hwp.switch_to(0)
            report['transfer_source_indices']=selection
            report['transfer_scope_ids']=[all_ids[index] for index in selection]
            report['selected_ranges']=ranges
            copy_clipboard={}
            for index,(start,end) in zip(selection,ranges):
                hwp.switch_to(0);step('copy_whole_question_'+str(index))
                if not hwp.SetPos(0,end-1,0):raise RuntimeError('RANGE_END')
                hwp.MoveParaEnd();finish=tuple(hwp.GetPos())
                if not hwp.select_text_by_get_pos((0,start,0),finish):raise RuntimeError('SELECT_WHOLE_QUESTION')
                seq=win32clipboard.GetClipboardSequenceNumber();hwp.Copy()
                clipboard=wait_native_payload(win32clipboard,seq,pump=pythoncom.PumpWaitingMessages,timeout=10.0)
                clipboard_row={'operation':'copy','item_index':index,'item_id':all_ids[index],'record':clipboard}
                row.setdefault('clipboard_records',[]).append(clipboard_row);copy_clipboard[index]=clipboard
                if not clipboard['ready']:raise RuntimeError('CLIPBOARD_NATIVE_UNAVAILABLE')
                hwp.switch_to(1);hwp.MoveDocEnd()
                if not paste_once('PASTE'):raise RuntimeError('PASTE')
                hwp.MoveDocEnd();hwp.BreakPara()
            save(a.out/'transferred.hwp','HWP');save(a.out/'transferred.hwpx','HWPX');quit_session(row)
            row=open_session(a.out/'transferred.hwp','HWP');save(a.out/'transfer-readback.hwpx','HWPX');quit_session(row)
            # Native Cut/Paste is independently exercised for every copied
            # question.  Reverse traversal keeps each untouched source range
            # stable while creating a deliberately reordered destination.
            pkg2=Package(a.out/'transfer-readback.hwpx');top2,ranges2=item_ranges(pkg2)
            if len(ranges2)!=len(selection):raise RuntimeError('TRANSFER_ANCHOR_COUNT')
            row=open_session(a.out/'transferred.hwp','HWP');hwp.add_tab();hwp.switch_to(0)
            move_clipboard={}
            for index,(start,end) in reversed(list(zip(selection,ranges2))):
                step('cut_move_whole_question_'+str(index));hwp.switch_to(0)
                if not hwp.SetPos(0,end-1,0):raise RuntimeError('MOVE_RANGE_END')
                hwp.MoveParaEnd();finish=tuple(hwp.GetPos())
                if not hwp.select_text_by_get_pos((0,start,0),finish):raise RuntimeError('MOVE_SELECTION')
                seq=win32clipboard.GetClipboardSequenceNumber();hwp.Cut()
                clipboard=wait_native_payload(win32clipboard,seq,pump=pythoncom.PumpWaitingMessages,timeout=10.0)
                clipboard_row={'operation':'move','item_index':index,'item_id':all_ids[index],'record':clipboard}
                row.setdefault('clipboard_records',[]).append(clipboard_row);move_clipboard[index]=clipboard
                if not clipboard['ready']:raise RuntimeError('CLIPBOARD_NATIVE_UNAVAILABLE')
                hwp.switch_to(1);hwp.MoveDocEnd()
                if not paste_once('MOVE_PASTE'):raise RuntimeError('MOVE_PASTE')
                hwp.MoveDocEnd();hwp.BreakPara()
            save(a.out/'moved.hwp','HWP');save(a.out/'moved.hwpx','HWPX');quit_session(row)
            row=open_session(a.out/'moved.hwp','HWP');save(a.out/'move-readback.hwpx','HWPX');quit_session(row)
            def readback_hashes(path):
                candidate=Package(path);candidate_top,candidate_ranges=item_ranges(candidate)
                return [payload_sha256(payload(candidate,candidate_top[start:end])) for start,end in candidate_ranges]
            copied_hashes=readback_hashes(a.out/'transfer-readback.hwpx')
            moved_hashes=readback_hashes(a.out/'move-readback.hwpx')
            if len(copied_hashes)!=len(selection) or len(moved_hashes)!=len(selection):raise RuntimeError('TRANSFER_READBACK_ANCHOR_COUNT')
            transfers=[]
            for position,index in enumerate(selection):
                observed=copied_hashes[position];source=expected[index]['payload_sha256']
                transfers.append({'id':all_ids[index],'item_index':index,'operation':'copy','whole_question':True,
                    'readback':observed==source,'payload_equal':observed==source,'source_payload_sha256':source,
                    'readback_payload_sha256':observed,'readback_artifact':str((a.out/'transfer-readback.hwpx').resolve()),
                    'native_clipboard_ready':copy_clipboard[index]['ready'],'native_clipboard_sha256':copy_clipboard[index].get('native_sha256')})
            for position,index in enumerate(reversed(selection)):
                observed=moved_hashes[position];source=expected[index]['payload_sha256']
                transfers.append({'id':all_ids[index],'item_index':index,'operation':'move','whole_question':True,
                    'readback':observed==source,'payload_equal':observed==source,'source_payload_sha256':source,
                    'readback_payload_sha256':observed,'readback_artifact':str((a.out/'move-readback.hwpx').resolve()),
                    'native_clipboard_ready':move_clipboard[index]['ready'],'native_clipboard_sha256':move_clipboard[index].get('native_sha256')})
            report['transfers']=transfers
            report['internal_hwp_cut_paste']={'performed':True,'item_count':len(selection),'destination_order':'reverse_source_order',
                                              'separate_from_windows_native_clipboard':True}
            if not all(item['payload_equal'] and item['native_clipboard_ready'] for item in transfers):raise RuntimeError('TRANSFER_PAYLOAD_OR_NATIVE_CLIPBOARD_MISMATCH')
        report['source_unchanged']=file_hash(a.input)==report['source_sha256']
        if not report['source_unchanged']:raise RuntimeError('SOURCE_CHANGED_DURING_COM')
        divergences = [row for row in report['sessions'] if 'b4_pdf' in row and row.get('gui_pdf_page_count_match') is not True]
        report['page_count_divergences'] = [{
            'input': row['input'], 'gui_pages': row.get('gui_pages'),
            'pdf_pages': row.get('b4_pdf', {}).get('pages'),
        } for row in divergences]
        report['status'] = ('COM_OPERATIONS_REVIEW_REQUIRED_PAGE_COUNT_DIVERGENCE'
                            if divergences else 'COM_OPERATIONS_PASS_REQUIRES_PAYLOAD_QA')
    except Exception as e:
        report['error']=repr(e)
        # A native clipboard failure is a specific, reproducible release
        # blocker.  Do not collapse it into a generic COM failure or treat
        # HWP's internal Cut/Paste as a substitute for Windows clipboard
        # evidence.
        if 'CLIPBOARD_NATIVE_UNAVAILABLE' in repr(e):
            report['status']='CLIPBOARD_NATIVE_UNAVAILABLE'
    finally:
        if hwp is not None:
            try:quit_session(report['sessions'][-1])
            except Exception as e:report['shutdown_error']=repr(e)
        report['outputs']=[{'path':str(p),'sha256':file_hash(p)} for p in a.out.iterdir() if p.suffix in ('.hwp','.hwpx','.pdf')]
        write_json(a.out/'com-report.json',report);step('finished')
    return 0 if report['status'].startswith('COM_OPERATIONS_PASS') else 2

def main():
    a=arguments();a.input=a.input.resolve();a.out=a.out.resolve();a.lock=a.lock.resolve()
    if a.worker:return worker(a)
    if not 10<=a.deadline<=600:raise ValueError('DEADLINE_RANGE')
    if a.out.exists():raise FileExistsError(a.out)
    a.lock.parent.mkdir(parents=True,exist_ok=True)
    with a.lock.open('x',encoding='utf8') as f:json.dump({'supervisor_pid':os.getpid(),'input':str(a.input),'out':str(a.out)},f)
    a.out.mkdir(parents=True)
    command=[sys.executable,str(Path(__file__).resolve()),*sys.argv[1:],'--worker']
    with (a.out/'worker.log').open('w',encoding='utf8') as log:
        process=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT)
        started=time.time()
        while process.poll() is None:
            time.sleep(.5)
            try:last=json.loads((a.out/'progress.json').read_text(encoding='utf8'))['time']
            except (OSError,ValueError,KeyError):last=started
            if time.time()-last>a.deadline:
                write_json(a.out/'timeout.json',{'status':'COM_DEADLINE_EXCEEDED','worker_pid':process.pid,'lease_preserved':True,'force_kill':False})
                return 2
    if process.returncode==0:a.lock.unlink()
    else:write_json(a.out/'failure.json',{'exit_code':process.returncode,'lease_preserved':True})
    return process.returncode
if __name__=='__main__':raise SystemExit(main())
