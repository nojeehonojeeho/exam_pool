"""Explicit, idempotent adapter for the local reviewed-manifest writer.

Only these two validated layout changes are applied; unknown writer layouts
fail closed. No manifests, source material or document files are included.
"""
import argparse
import ast
from pathlib import Path


def patch_source(source):
    ast.parse(source)
    edits=[
        ('_insert_display_equation',
         '        keep=True,\n    )',
         '        keep=True,\n        with_next=bool(block.get("keep_with_next", False)),\n    )'),
        ('_build_solution',
         '            _insert_item_heading(hwp, item, role="solution")\n            hwp.BreakPara()\n',
         '            _insert_item_heading(hwp, item, role="solution")\n'),
    ]
    for name,old,new in edits:
        tree=ast.parse(source)
        functions=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==name]
        if len(functions)!=1:raise ValueError(f"writer function not unique: {name}")
        node=functions[0];lines=source.splitlines(keepends=True)
        body=''.join(lines[node.lineno-1:node.end_lineno])
        if old in body:
            if body.count(old)!=1:raise ValueError(f"ambiguous writer patch: {name}")
            body=body.replace(old,new,1)
        elif new not in body:
            raise ValueError(f"unknown writer contract: {name}")
        lines[node.lineno-1:node.end_lineno]=[body]
        source=''.join(lines)
    ast.parse(source)
    return source


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('writer',type=Path)
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    original=args.writer.read_text(encoding='utf-8')
    updated=patch_source(original)
    if args.apply and updated!=original:
        backup=args.writer.with_suffix(args.writer.suffix+'.pre-solution-flow')
        if backup.exists():raise FileExistsError(backup)
        backup.write_bytes(args.writer.read_bytes())
        args.writer.write_text(updated,encoding='utf-8')
    print('already applied' if updated==original else ('applied' if args.apply else 'patch available; no files changed'))

if __name__=='__main__':main()
