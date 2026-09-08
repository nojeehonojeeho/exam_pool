"""Idempotent, fail-closed adapter for source-declared native table spans."""
import argparse
import ast
from pathlib import Path

VALIDATE = '''    from app.hwp_table_merges import apply_native_merges, validated_merges
    merges = block.get("metadata", {}).get("cell_merges", [])
    if merges:
        validated_merges(matrix, merges)
'''
APPLY = '''    if merges:
        def go_to_cell(row, col):
            _enter_table_ctrl(hwp, table_ctrl)
            for _ in range(col):
                if hwp.TableRightCell() is not True:
                    raise RuntimeError("MERGE_ANCHOR_NAVIGATION_FAILED")
            for _ in range(row):
                if hwp.TableLowerCell() is not True:
                    raise RuntimeError("MERGE_ANCHOR_NAVIGATION_FAILED")
        apply_native_merges(hwp, matrix, merges, go_to_cell)
'''


def patch_source(source):
    nodes = [n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == '_insert_matrix']
    if len(nodes) != 1:
        raise ValueError('unknown writer matrix boundary')
    node = nodes[0]
    lines = source.splitlines(keepends=True)
    body = ''.join(lines[node.lineno - 1:node.end_lineno])
    for anchor, addition, before in [
        ('    rows, cols = len(matrix), len(matrix[0])\n', VALIDATE, False),
        ('    hwp.CloseEx()\n', APPLY, True),
    ]:
        if addition in body:
            continue
        if body.count(anchor) != 1:
            raise ValueError('unknown writer table merge boundary')
        body = body.replace(anchor, addition + anchor if before else anchor + addition, 1)
    lines[node.lineno - 1:node.end_lineno] = [body]
    result = ''.join(lines)
    ast.parse(result)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('writer', type=Path)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    source = args.writer.read_text(encoding='utf-8')
    result = patch_source(source)
    if args.apply and result != source:
        backup = args.writer.with_suffix(args.writer.suffix + '.pre-table-merges')
        if backup.exists():
            raise FileExistsError(backup)
        backup.write_bytes(args.writer.read_bytes())
        args.writer.write_text(result, encoding='utf-8')
    print('already applied' if source == result else 'applied' if args.apply else 'patch available; no changes')


if __name__ == '__main__':
    main()
