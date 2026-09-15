"""Bind independently reopened HWP and HWPX COM reports to one target pair."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.teacher_workflow import file_hash, write_json


def args() -> argparse.Namespace:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target-hwp',type=Path,required=True)
    parser.add_argument('--target-hwpx',type=Path,required=True)
    parser.add_argument('--hwp-report',type=Path,required=True)
    parser.add_argument('--hwpx-report',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    return parser.parse_args()


def load(path:Path)->dict:return json.loads(path.read_text(encoding='utf-8-sig'))
def ref(path:Path)->dict:return {'path':str(path.resolve()),'sha256':file_hash(path),'bytes':path.stat().st_size}


def validate(report:dict, source_hash:str, label:str)->None:
    if report.get('source_sha256')!=source_hash:raise ValueError('COM_SOURCE_TARGET_MISMATCH:'+label)
    if not report.get('status','').startswith('COM_OPERATIONS_PASS'):raise ValueError('COM_REPORT_NOT_PASS:'+label)
    if report.get('source_unchanged') is not True:raise ValueError('COM_SOURCE_CHANGED:'+label)
    if report.get('physical_b4_page_count_match') is not True:raise ValueError('COM_PHYSICAL_B4_PAGE_COUNT_MISMATCH:'+label)
    sessions=report.get('sessions',[])
    if not sessions or not all(row.get('register_module_return') is True and not row.get('approval_windows') and not row.get('owned_pids_remaining') for row in sessions):
        raise ValueError('COM_SECURITY_OR_SHUTDOWN_NOT_CLOSED:'+label)


def merge(targets:dict[str,str], hwp_path:Path, hwp:dict, hwpx_path:Path, hwpx:dict)->dict:
    validate(hwp,targets['hwp'],'hwp');validate(hwpx,targets['hwpx'],'hwpx')
    physical=[]
    for label,report in (('hwp',hwp),('hwpx',hwpx)):
        for row in report.get('sessions',[]):
            if isinstance(row.get('b4_pdf'),dict):physical.append({'source_format':label,'input':row.get('input'),'pages':row['b4_pdf'].get('pages'),'artifact':row['b4_pdf']})
    if not physical or any(not isinstance(row['pages'],int) or row['pages']<1 for row in physical) or len({row['pages'] for row in physical})!=1:
        raise ValueError('COM_PAIR_PHYSICAL_EXPORTS_DIFFER')
    return {
        'schema':'teacher-com-roundtrip-pair/v1','status':'COM_OPERATIONS_PASS_REQUIRES_PAYLOAD_QA',
        'target_sha256':targets,'source_unchanged':True,'sessions':hwp['sessions']+hwpx['sessions'],
        'reports':{'hwp':ref(hwp_path),'hwpx':ref(hwpx_path)},'physical_b4_exports':physical,
        'physical_b4_page_count_match':True,
        'gui_page_count_warnings':{'hwp':hwp.get('gui_page_count_divergences',[]),'hwpx':hwpx.get('gui_page_count_divergences',[])},
        'checks':{'target_hwp_and_hwpx_reopened_separately':True,'security_and_owned_pid_shutdown_closed':True,'physical_b4_exports_have_equal_positive_page_count':True},
    }


def main()->int:
    a=args()
    if a.out.exists():raise FileExistsError(a.out)
    targets={'hwp':file_hash(a.target_hwp),'hwpx':file_hash(a.target_hwpx)}
    result=merge(targets,a.hwp_report,load(a.hwp_report),a.hwpx_report,load(a.hwpx_report))
    write_json(a.out,result)
    print(json.dumps({'status':result['status'],'pages':result['physical_b4_exports'][0]['pages']},ensure_ascii=False))
    return 0


if __name__=='__main__':raise SystemExit(main())
