"""Narrow adapter for declared unbreakable text spans in a local writer."""
import argparse,ast
from pathlib import Path

IMPORT='from app.hwp_protected_text import insert_protected_text\n'
CONTEXT='    context={**context,"unbreakable_phrases":block.get("metadata",{}).get("unbreakable_phrases",())}\n'

def patch_source(source):
    ast.parse(source)
    if IMPORT not in source:
        anchor='from app.integrations.hwp_security import create_secure_hwp\n'
        if source.count(anchor)!=1:raise ValueError('unknown writer import boundary')
        source=source.replace(anchor,anchor+IMPORT,1)
    for name,old,new in [
        ('_insert_segments','                hwp.insert_text(str(segment.get("text", "")))',
         '                insert_protected_text(hwp,str(segment.get("text", "")),context.get("unbreakable_phrases",()))'),
        ('_insert_text_block','        hwp.insert_text(str(block.get("text", "")))',
         '        insert_protected_text(hwp,str(block.get("text", "")),context.get("unbreakable_phrases",()))')]:
        nodes=[n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name==name]
        if len(nodes)!=1:raise ValueError('writer function not unique: '+name)
        node=nodes[0];lines=source.splitlines(keepends=True);body=''.join(lines[node.lineno-1:node.end_lineno])
        if old in body:
            if body.count(old)!=1:raise ValueError('ambiguous writer text insertion')
            body=body.replace(old,new,1)
        elif new not in body:raise ValueError('unknown writer text insertion')
        if name=='_insert_text_block' and CONTEXT not in body:
            anchor='    role = str(block.get("role", "body"))\n'
            if body.count(anchor)!=1:raise ValueError('unknown writer paragraph boundary')
            body=body.replace(anchor,CONTEXT+anchor,1)
        lines[node.lineno-1:node.end_lineno]=[body];source=''.join(lines)
    ast.parse(source)
    return source

def main():
    p=argparse.ArgumentParser();p.add_argument('writer',type=Path);p.add_argument('--apply',action='store_true');a=p.parse_args()
    original=a.writer.read_text(encoding='utf-8');updated=patch_source(original)
    if a.apply and updated!=original:
        backup=a.writer.with_suffix(a.writer.suffix+'.pre-protected-text')
        if backup.exists():raise FileExistsError(backup)
        backup.write_bytes(a.writer.read_bytes());a.writer.write_text(updated,encoding='utf-8')
    print('already applied' if updated==original else ('applied' if a.apply else 'patch available; no changes'))

if __name__=='__main__':main()
