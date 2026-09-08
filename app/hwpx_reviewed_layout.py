"""Apply an explicit, hash-bound presentation correction to a fresh package.

No automatic source-fidelity judgement, text padding, or equation-script edits.
The caller must run actual HWP/HWPX readback and visual QA afterwards.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import zipfile
from lxml import etree as E


def _empty_layout_paragraph(node) -> bool:
    """Deliberately reject spaces, controls, markers and unknown children."""
    ns = '{http://www.hancom.co.kr/hwpml/2011/paragraph}'
    if node.tag != ns + 'p' or node.text or node.get('pageBreak', '0') != '0' or node.get('columnBreak', '0') != '0':
        return False
    for child in node:
        if child.tail or child.text:
            return False
        if child.tag == ns + 'run':
            if any(x.tag != ns + 't' or x.text or len(x) or x.tail for x in child):
                return False
        elif child.tag == ns + 'linesegarray':
            if any(x.tag != ns + 'lineseg' or x.text or len(x) or x.tail for x in child):
                return False
        else:
            return False
    return True


def revise_section(data: bytes, corrections: list[dict], *, superscript_endnote: bool = False, cell_tails: list[dict] | None = None, cell_spacers: list[dict] | None = None):
    root = E.fromstring(data)
    equations = root.findall('.//{*}equation')
    seen = set()
    changes = []
    tail_plans = []
    tail_seen = set()
    tables = root.findall('.//{*}tbl')
    spacer_plans = []
    spacer_seen = set()
    for row in cell_spacers or []:
        ti, ci, pi = row['table_index'], row['cell_index'], row['paragraph_index']
        if any(type(x) is not int or x < 0 for x in (ti, ci, pi)) or ti >= len(tables) or (ti, ci, pi) in spacer_seen:
            raise ValueError('INVALID_CELL_SPACER_PLAN')
        spacer_seen.add((ti, ci, pi))
        cells = tables[ti].findall('./{*}tr/{*}tc')
        if ci >= len(cells):
            raise ValueError('INVALID_CELL_SPACER_PLAN')
        sub = cells[ci].find('{*}subList')
        if sub is None or pi >= len(sub) or len(sub) <= 1:
            raise ValueError('INVALID_CELL_SPACER_PLAN')
        para = sub[pi]
        if not _empty_layout_paragraph(para) or para.get('paraPrIDRef') != str(row['expected_para_pr_id']):
            raise ValueError('CELL_SPACER_CONTENT_OR_STYLE_MISMATCH')
        spacer_plans.append((sub, para, row))
    for row in cell_tails or []:
        ti, ci, count = row['table_index'], row['cell_index'], row['expected_empty_tail_count']
        if any(type(x) is not int or x < 0 for x in (ti, ci, count)) or count == 0 or ti >= len(tables) or (ti, ci) in tail_seen:
            raise ValueError('INVALID_CELL_TAIL_PLAN')
        tail_seen.add((ti, ci))
        cells = tables[ti].findall('./{*}tr/{*}tc')
        if ci >= len(cells):
            raise ValueError('INVALID_CELL_TAIL_PLAN')
        sub = cells[ci].find('{*}subList')
        if sub is None:
            raise ValueError('CELL_SUBLIST_MISSING')
        tail = []
        for para in reversed(sub):
            if not _empty_layout_paragraph(para):
                break
            tail.append(para)
        if len(tail) != count or len(tail) == len(sub):
            raise ValueError('CELL_EMPTY_TAIL_MISMATCH')
        if any(para in tail for _, para, _ in spacer_plans):
            raise ValueError('OVERLAPPING_CELL_SPACER_PLAN')
        tail_plans.append((sub, tail, row))
    for sub, _, _ in spacer_plans:
        removing = {p for s, p, _ in spacer_plans if s is sub}
        removing.update(p for s, tail, _ in tail_plans if s is sub for p in tail)
        if len(removing) >= len(sub):
            raise ValueError('CELL_MUST_RETAIN_CONTENT_PARAGRAPH')
    # Validate the entire plan before mutating any node.
    for row in corrections:
        index = row['index']
        right = row['right_hwpunit']
        if type(index) is not int or not 0 <= index < len(equations) or index in seen:
            raise ValueError('INVALID_OR_DUPLICATE_EQUATION_INDEX')
        seen.add(index)
        if type(right) is not int or not 0 <= right <= 283:
            raise ValueError('REVIEWED_MARGIN_OUT_OF_RANGE')
        eq = equations[index]
        if eq.findtext('{*}script') != row['expected_script']:
            raise ValueError('EQUATION_PLAN_SCRIPT_MISMATCH')
        pos, margin = eq.find('{*}pos'), eq.find('{*}outMargin')
        if pos is None or pos.get('treatAsChar') != '1' or margin is None:
            raise ValueError('NOT_AN_INLINE_EQUATION')
        if margin.get('right') != str(row['expected_right_hwpunit']):
            raise ValueError('EQUATION_PLAN_MARGIN_MISMATCH')
    for row in corrections:
        margin = equations[row['index']].find('{*}outMargin')
        margin.set('right', str(row['right_hwpunit']))
        changes.append(dict(row))
    if type(superscript_endnote) is not bool:
        raise ValueError('SUPERSCRIPT_FLAG_NOT_BOOLEAN')
    if superscript_endnote:
        for prop in root.findall('.//{*}endNotePr'):
            fmt = prop.find('{*}autoNumFormat')
            if fmt is None:
                raise ValueError('ENDNOTE_FORMAT_MISSING')
            fmt.set('supscript', '1')
    for sub, tail, row in tail_plans:
        for para in tail:
            sub.remove(para)
        changes.append({'kind': 'reviewed_empty_cell_tail', **row})
    for sub, para, row in spacer_plans:
        sub.remove(para)
        changes.append({'kind': 'reviewed_empty_cell_spacer', **row})
    return E.tostring(root, encoding='UTF-8', xml_declaration=True), changes


def revise_package(source: Path, target: Path, plan: dict) -> dict:
    source, target = Path(source).resolve(), Path(target).resolve()
    if source == target or target.exists():
        raise ValueError('FRESH_OUTPUT_REQUIRED')
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    if digest != plan['source_sha256']:
        raise ValueError('LAYOUT_PLAN_SOURCE_HASH_MISMATCH')
    members = {}
    applied = {}
    with zipfile.ZipFile(source) as zin:
        infos = zin.infolist()
        for info in infos:
            members[info.filename] = zin.read(info.filename)
        for name, spec in plan['sections'].items():
            if not name.startswith('Contents/section') or not name.endswith('.xml') or name not in members:
                raise ValueError('INVALID_SECTION_PLAN')
            members[name], applied[name] = revise_section(members[name], spec.get('equations', []),
                superscript_endnote=spec.get('superscript_endnote', False), cell_tails=spec.get('cell_tails'), cell_spacers=spec.get('cell_spacers'))
        # Exclusive create: never overwrite a candidate or source on a race.
        with zipfile.ZipFile(target, 'x') as zout:
            for info in infos:
                zout.writestr(info, members[info.filename])
    return {'source_sha256': digest, 'output_sha256': hashlib.sha256(target.read_bytes()).hexdigest(),
            'applied': applied, 'status': 'LAYOUT_CHANGED_REQUIRES_COM_AND_VISUAL_QA', 'final': False}
