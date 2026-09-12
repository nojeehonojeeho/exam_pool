"""Patch question-sized blocks with native HWP ``keepWithNext`` flags.

The generated HIGH-END upper/lower books keep each question in a layout
``subList``.  A question heading is a direct paragraph using the reviewed
heading property (paraPrIDRef=29); its condition/choice tables contain nested
paragraphs.  This utility discovers those headings in each containing
``subList`` and clones paragraph properties for every paragraph in a block,
setting ``breakSetting/keepWithNext=1`` on all but the final paragraph.  It
never changes text, equations, tables, pictures, or endnote relationships and
always writes a fresh HWPX package.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile
import xml.etree.ElementTree as ET


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _owned_text(paragraph: ET.Element) -> str:
    parts: list[str] = []
    for node in paragraph.iter():
        if node is not paragraph and _local(node.tag) == "p":
            continue
        if _local(node.tag) == "t":
            parts.append(node.text or "")
    return "".join(parts).strip()


def _descendant_paragraphs(paragraph: ET.Element) -> list[ET.Element]:
    out = [paragraph]
    for child in list(paragraph):
        if _local(child.tag) == "p":
            out.extend(_descendant_paragraphs(child))
        else:
            for nested in child.iter():
                if nested is not paragraph and _local(nested.tag) == "p":
                    out.extend(_descendant_paragraphs(nested))
    # preserve XML order and identity
    seen: set[int] = set()
    return [p for p in out if not (id(p) in seen or seen.add(id(p)))]


def _para_properties(header: ET.Element) -> tuple[dict[str, ET.Element], ET.Element, int]:
    by_id: dict[str, ET.Element] = {}
    container: ET.Element | None = None
    max_id = 0
    for parent in header.iter():
        for child in list(parent):
            if _local(child.tag) != "paraPr":
                continue
            ident = child.get("id")
            if ident is None:
                continue
            by_id[ident] = child
            if container is None:
                container = parent
            try:
                max_id = max(max_id, int(ident))
            except ValueError:
                pass
    if container is None:
        raise ValueError("HWPX header has no paraPr container")
    return by_id, container, max_id


def _patch_block(
    paragraphs: list[ET.Element],
    *,
    by_id: dict[str, ET.Element],
    container: ET.Element,
    next_id: list[int],
    records: list[dict[str, Any]],
    section: str,
) -> None:
    ordered: list[ET.Element] = []
    for paragraph in paragraphs:
        ordered.extend(_descendant_paragraphs(paragraph))
    seen: set[int] = set()
    ordered = [p for p in ordered if not (id(p) in seen or seen.add(id(p)))]
    # Blank paragraphs are intentionally retained: they are part of the source
    # block and must not be removed or replaced with synthetic text.
    for index, paragraph in enumerate(ordered):
        if index == len(ordered) - 1:
            continue
        source_id = paragraph.get("paraPrIDRef")
        if source_id not in by_id:
            raise ValueError(f"unknown paraPrIDRef in {section}: {source_id!r}")
        clone = copy.deepcopy(by_id[source_id])
        next_id[0] += 1
        clone.set("id", str(next_id[0]))
        setting = next((n for n in clone.iter() if _local(n.tag) == "breakSetting"), None)
        if setting is None:
            raise ValueError(f"paragraph property {source_id} has no breakSetting")
        setting.set("keepWithNext", "1")
        container.append(clone)
        by_id[str(next_id[0])] = clone
        paragraph.set("paraPrIDRef", str(next_id[0]))
        records.append(
            {
                "section": section,
                "source_paraPrIDRef": source_id,
                "patched_paraPrIDRef": str(next_id[0]),
                "keepWithNext": True,
                "text": _owned_text(paragraph),
            }
        )


def patch_blocks(input_path: Path, output_path: Path, *, heading_para_pr: str = "29") -> dict[str, Any]:
    source = input_path.resolve()
    target = output_path.resolve()
    if source == target:
        raise ValueError("output must be a fresh path")
    if target.exists():
        raise FileExistsError(target)
    with ZipFile(source) as archive:
        entries = [(info, archive.read(info.filename)) for info in archive.infolist()]
    header_payload = next((payload for info, payload in entries if info.filename == "Contents/header.xml"), None)
    if header_payload is None:
        raise ValueError("Contents/header.xml is missing")
    header = ET.fromstring(header_payload)
    by_id, container, max_id = _para_properties(header)
    records: list[dict[str, Any]] = []
    next_id = [max_id]
    block_count = 0
    updated: list[tuple[Any, bytes]] = []
    for info, payload in entries:
        if not (info.filename.startswith("Contents/section") and info.filename.endswith(".xml")):
            updated.append((info, payload))
            continue
        root = ET.fromstring(payload)
        # Each parent whose direct children contain headings is a candidate
        # question list. Endnote paragraphs usually do not use the reviewed
        # heading property and therefore remain untouched.
        for parent in root.iter():
            children = list(parent)
            headings = [
                i
                for i, child in enumerate(children)
                if _local(child.tag) == "p"
                and child.get("paraPrIDRef") == heading_para_pr
                and bool(_owned_text(child))
            ]
            if not headings:
                continue
            for pos, start in enumerate(headings):
                stop = headings[pos + 1] if pos + 1 < len(headings) else len(children)
                direct = [node for node in children[start:stop] if _local(node.tag) == "p"]
                if not direct:
                    continue
                _patch_block(direct, by_id=by_id, container=container, next_id=next_id, records=records, section=info.filename)
                block_count += 1
        ET.register_namespace("hp", "http://www.hancom.co.kr/hwpml/2011/paragraph")
        ET.register_namespace("hs", "http://www.hancom.co.kr/hwpml/2011/section")
        updated.append((info, ET.tostring(root, encoding="utf-8", xml_declaration=True)))
    if not records:
        raise ValueError("no heading blocks found")
    ET.register_namespace("hh", "http://www.hancom.co.kr/hwpml/2011/head")
    header_bytes = ET.tostring(header, encoding="utf-8", xml_declaration=True)
    with ZipFile(target, "w", ZIP_DEFLATED) as archive:
        for info, payload in updated:
            archive.writestr(info, header_bytes if info.filename == "Contents/header.xml" else payload)
    return {
        "status": "PASS",
        "schema": "hwp-keep-with-next-blocks-v1",
        "input": str(source),
        "output": str(target),
        "heading_para_pr": heading_para_pr,
        "question_block_count": block_count,
        "patched_paragraph_count": len(records),
        "records": records,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--heading-para-pr", default="29")
    args = parser.parse_args()
    print(json.dumps(patch_blocks(args.input, args.output, heading_para_pr=args.heading_para_pr), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
