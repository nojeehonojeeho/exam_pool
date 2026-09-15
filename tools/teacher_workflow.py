"""Explicit CLI for teacher layout extraction, native staged reflow and gating."""
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.teacher_workflow import profile,build,release_gate,write_json

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=['profile','build','gate'])
    p.add_argument('--input',type=Path,required=True)
    p.add_argument('--report',type=Path,required=True)
    a=p.parse_args()
    if a.action=='profile':result=profile(a.input)
    else:
        config=json.loads(a.input.read_text(encoding='utf-8-sig'))
        result=build(config,a.input.parent) if a.action=='build' else release_gate(config,a.input.parent)
    write_json(a.report,result)
    print(json.dumps({'action':a.action,'status':result.get('status','EXTRACTED_XML_ONLY'),'report':str(a.report)}))
    return 2 if result.get('status')=='BLOCKED' else 0
if __name__=='__main__':raise SystemExit(main())
