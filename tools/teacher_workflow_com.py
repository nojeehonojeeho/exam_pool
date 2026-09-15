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
    p.add_argument('--transfer',type=int,nargs='*');p.add_argument('--worker',action='store_true')
    return p.parse_args()

def validate_transfer_selection(indices,count):
    if len(indices)<2 or len(set(indices))!=len(indices) or any(i<0 or i>=count for i in indices):
        raise ValueError('TRANSFER_REQUIRES_TWO_OR_MORE_DISTINCT_IN_RANGE_ITEMS')

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
        hwp=create_secure_hwp(new=True,visible=False,on_quit=False);owned=pids()-before
        registered=getattr(hwp,'_hwp_security_registration').returned
        row={'input':str(path),'input_sha256':file_hash(path),'register_module_return':registered,'owned_pids':sorted(owned)};report['sessions'].append(row)
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
        step('quit');hwp.quit(save=False);hwp=None
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
        if a.transfer is None:
            row=open_session(a.input,'HWPX')
            save(a.out/'pilot.hwp','HWP');save(a.out/'pilot.hwpx','HWPX');row['gui_pages']=int(hwp.PageCount)
            quit_session(row)
            for fmt in ('HWP','HWPX'):
                row=open_session(a.out/('pilot.'+fmt.lower()),fmt)
                save(a.out/(fmt.lower()+'-readback.hwpx'),'HWPX');row['gui_pages']=int(hwp.PageCount)
                step('physical_b4_export_'+fmt);row['b4_pdf']=export_b4_pdf(hwp,a.out/(fmt.lower()+'-b4.pdf'))
                quit_session(row)
        else:
            import win32clipboard,pythoncom
            from app.hwp_native_clipboard import wait_native_payload
            pkg=Package(a.input.with_suffix('.hwpx'));sec=next(iter(pkg.sections.values()));top=list(sec)
            starts=[i for i,p in enumerate(top) if p.find('.//'+P('endNote')) is not None]
            validate_transfer_selection(a.transfer,len(starts))
            ranges=[]
            for index in a.transfer:
                start=starts[index];end=starts[index+1] if index+1<len(starts) else len(top)
                while end>start+1:
                    n=top[end-1];t=''.join(n.xpath('./p:run/p:t/text()',namespaces=NS))
                    if payload(pkg,[n])==[['paragraph_end',None]] or ' · 유형편 · ' in t or ' · 실전편 · ' in t:end-=1
                    else:break
                ranges.append((start,end))
            row=open_session(a.input,'HWP');hwp.add_tab();hwp.switch_to(0)
            report['transfer_source_indices']=a.transfer
            report['selected_ranges']=ranges
            for index,(start,end) in zip(a.transfer,ranges):
                hwp.switch_to(0);step('copy_whole_question_'+str(index))
                if not hwp.SetPos(0,end-1,0):raise RuntimeError('RANGE_END')
                hwp.MoveParaEnd();finish=tuple(hwp.GetPos())
                if not hwp.select_text_by_get_pos((0,start,0),finish):raise RuntimeError('SELECT_WHOLE_QUESTION')
                seq=win32clipboard.GetClipboardSequenceNumber();hwp.Copy()
                if not wait_native_payload(win32clipboard,seq,pump=pythoncom.PumpWaitingMessages)['ready']:raise RuntimeError('CLIPBOARD')
                hwp.switch_to(1);hwp.MoveDocEnd()
                if not paste_once('PASTE'):raise RuntimeError('PASTE')
                hwp.MoveDocEnd();hwp.BreakPara()
            save(a.out/'transferred.hwp','HWP');save(a.out/'transferred.hwpx','HWPX');quit_session(row)
            row=open_session(a.out/'transferred.hwp','HWP');save(a.out/'transfer-readback.hwpx','HWPX');quit_session(row)
            # A second actual cut/paste moves the first whole question to the end.
            pkg2=Package(a.out/'transfer-readback.hwpx');sec2=next(iter(pkg2.sections.values()));top2=list(sec2)
            starts2=[i for i,n in enumerate(top2) if n.find('.//'+P('endNote')) is not None]
            if len(starts2)!=len(a.transfer):raise RuntimeError('TRANSFER_ANCHOR_COUNT')
            row=open_session(a.out/'transferred.hwp','HWP')
            step('cut_move_whole_question')
            if not hwp.select_text_by_get_pos((0,starts2[0],0),(0,starts2[1],0)):raise RuntimeError('MOVE_SELECTION')
            seq=win32clipboard.GetClipboardSequenceNumber();hwp.Cut()
            if not wait_native_payload(win32clipboard,seq,pump=pythoncom.PumpWaitingMessages)['ready']:raise RuntimeError('MOVE_CLIPBOARD')
            hwp.MoveDocEnd()
            if not paste_once('MOVE_PASTE'):raise RuntimeError('MOVE_PASTE')
            save(a.out/'moved.hwp','HWP');save(a.out/'moved.hwpx','HWPX');quit_session(row)
            row=open_session(a.out/'moved.hwp','HWP');save(a.out/'move-readback.hwpx','HWPX');quit_session(row)
        report['source_unchanged']=file_hash(a.input)==report['source_sha256']
        if not report['source_unchanged']:raise RuntimeError('SOURCE_CHANGED_DURING_COM')
        report['status']='COM_OPERATIONS_PASS_REQUIRES_PAYLOAD_QA'
    except Exception as e:
        report['error']=repr(e)
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
