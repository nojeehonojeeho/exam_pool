"""Apply an explicit, hash-bound presentation correction to a fresh package.

No automatic source-fidelity judgement, text padding, or equation-script edits.
The caller must run actual HWP/HWPX readback and visual QA afterwards.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import zipfile
from lxml import etree as E


def revise_section(data: bytes, corrections: list[dict], *, superscript_endnote: bool = False):
    root = E.fromstring(data)
    equations = root.findall('.//{*}equation')
    seen = set()
    changes = []
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
                superscript_endnote=spec.get('superscript_endnote', False))
        # Exclusive create: never overwrite a candidate or source on a race.
        with zipfile.ZipFile(target, 'x') as zout:
            for info in infos:
                zout.writestr(info, members[info.filename])
    return {'source_sha256': digest, 'output_sha256': hashlib.sha256(target.read_bytes()).hexdigest(),
            'applied': applied, 'status': 'LAYOUT_CHANGED_REQUIRES_COM_AND_VISUAL_QA', 'final': False}
