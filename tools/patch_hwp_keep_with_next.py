"""Keep a contiguous paragraph block together during HWP pagination.

HWPX paragraphs inside a table cell do not consistently honor the ad-hoc
``pageBreak`` attribute.  The native paragraph ``breakSetting`` contract is
the reliable way to prevent a question heading, conditions, and its choices
from being split at a page boundary.  This tool clones the referenced
paragraph styles, sets ``keepWithNext=1`` only on the requested block, and
writes a fresh package without changing visible text or object relationships.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile
import copy
import xml.etree.ElementTree as ET


def _paragraph_text(paragraph: ET.Element) -> str:
    """Return text owned by *paragraph*, excluding nested table paragraphs."""
    chunks: list[str] = []

    def walk(node: ET.Element) -> None:
        for child in list(node):
            # A nested paragraph (for example a table cell inside an outer
            # layout table) owns its own text.  Do not let an outer paragraph
            # accidentally match an anchor that belongs to that child.
            if child is not paragraph and child.tag.endswith("p"):
                continue
            if child.tag.endswith("t"):
                chunks.append(child.text or "")
            walk(child)

    walk(paragraph)
    return "".join(chunks)


def _find_match_with_parent(root: ET.Element, anchor: str, occurrence: int) -> tuple[ET.Element, int, list[ET.Element]] | None:
    matches = 0

    def walk(parent: ET.Element):
        nonlocal matches
        children = list(parent)
        for index, child in enumerate(children):
            # Search descendants first so the deepest paragraph that owns the
            # visible anchor wins over an enclosing table/layout paragraph.
            found = walk(child)
            if found is not None:
                return found
            if child.tag.endswith("p") and anchor in _paragraph_text(child):
                matches += 1
                if matches == occurrence:
                    return parent, index, children
        return None

    return walk(root)


def _paragraphs_in_document_order(paragraph: ET.Element) -> list[ET.Element]:
    """Return the paragraph and any nested cell paragraphs in document order."""
    out: list[ET.Element] = [paragraph]

    def walk(node: ET.Element) -> None:
        for child in list(node):
            if child is not paragraph and child.tag.endswith("p"):
                out.append(child)
                # A nested paragraph owns its descendants; continue below it
                # to cover nested tables without duplicating the parent.
                walk(child)
            else:
                walk(child)

    walk(paragraph)
    return out


def _para_pr_nodes(header_root: ET.Element) -> tuple[dict[str, ET.Element], ET.Element | None, int]:
    by_id: dict[str, ET.Element] = {}
    container: ET.Element | None = None
    max_id = 0
    for parent in header_root.iter():
        for child in list(parent):
            if not child.tag.endswith("paraPr"):
                continue
            ident = child.get("id")
            if ident is None:
                continue
            by_id[ident] = child
            try:
                max_id = max(max_id, int(ident))
            except ValueError:
                pass
            if container is None:
                container = parent
    if container is None:
        raise ValueError("HWPX header has no paragraph-property container")
    return by_id, container, max_id


def patch_keep_with_next(
    input_path: Path,
    output_path: Path,
    *,
    anchor: str,
    span: int = 1,
    occurrence: int = 1,
) -> dict[str, Any]:
    input_path = input_path.resolve()
    output_path = output_path.resolve()
    if input_path == output_path:
        raise ValueError("output must be a fresh path")
    if output_path.exists():
        raise FileExistsError(output_path)
    if not anchor:
        raise ValueError("anchor must not be empty")
    if span < 1:
        raise ValueError("span must be >= 1")
    if occurrence < 1:
        raise ValueError("occurrence must be >= 1")

    records: list[dict[str, Any]] = []
    matched = 0
    with ZipFile(input_path) as source:
        entries = [(info, source.read(info.filename)) for info in source.infolist()]
    header_payload = next((payload for info, payload in entries if info.filename == "Contents/header.xml"), None)
    if header_payload is None:
        raise ValueError("HWPX Contents/header.xml is missing")
    header_root = ET.fromstring(header_payload)
    para_pr_by_id, para_pr_container, max_id = _para_pr_nodes(header_root)

    updated_entries: list[tuple[Any, bytes]] = []
    for info, payload in entries:
        if not (info.filename.startswith("Contents/section") and info.filename.endswith(".xml")):
            updated_entries.append((info, payload))
            continue
        root = ET.fromstring(payload)
        found = _find_match_with_parent(root, anchor, occurrence)
        if found is None:
            updated_entries.append((info, payload))
            continue
        parent, start, siblings = found
        selected = [node for node in siblings[start : start + span] if node.tag.endswith("p")]
        if len(selected) < span:
            raise ValueError(
                f"anchor block has fewer than span={span} paragraph siblings: found={len(selected)}"
            )
        # A layout paragraph may contain a nested condition/choice table.  A
        # keep flag on the outer paragraph alone is insufficient in Hanword,
        # so include all nested paragraphs in the same contiguous block.
        expanded: list[ET.Element] = []
        for paragraph in selected:
            expanded.extend(_paragraphs_in_document_order(paragraph))
        seen: set[int] = set()
        selected_all = [p for p in expanded if not (id(p) in seen or seen.add(id(p)))]
        for offset, paragraph in enumerate(selected_all):
            source_id = paragraph.get("paraPrIDRef")
            if source_id is None or source_id not in para_pr_by_id:
                raise ValueError(f"paragraph has unknown paraPrIDRef: {source_id!r}")
            clone = copy.deepcopy(para_pr_by_id[source_id])
            max_id += 1
            clone.set("id", str(max_id))
            setting = next((node for node in clone.iter() if node.tag.endswith("breakSetting")), None)
            if setting is None:
                raise ValueError(f"paragraph property {source_id} has no breakSetting")
            setting.set("keepWithNext", "1")
            para_pr_container.append(clone)
            para_pr_by_id[str(max_id)] = clone
            paragraph.set("paraPrIDRef", str(max_id))
            records.append(
                {
                    "section": info.filename,
                    "paragraph_offset": offset,
                    "text": _paragraph_text(paragraph),
                    "source_paraPrIDRef": source_id,
                    "patched_paraPrIDRef": str(max_id),
                    "keepWithNext": "1",
                }
            )
        ET.register_namespace("hp", "http://www.hancom.co.kr/hwpml/2011/paragraph")
        ET.register_namespace("hs", "http://www.hancom.co.kr/hwpml/2011/section")
        updated_entries.append((info, ET.tostring(root, encoding="utf-8", xml_declaration=True)))

    if not records:
        if output_path.exists():
            output_path.unlink()
        raise ValueError(f"anchor occurrence not found: {anchor!r} (matches={matched})")

    ET.register_namespace("hh", "http://www.hancom.co.kr/hwpml/2011/head")
    updated_header = ET.tostring(header_root, encoding="utf-8", xml_declaration=True)
    with ZipFile(output_path, "w", ZIP_DEFLATED) as target:
        for info, payload in updated_entries:
            if info.filename == "Contents/header.xml":
                payload = updated_header
            target.writestr(info, payload)
    return {
        "status": "PASS",
        "schema": "hwp-keep-with-next-patch-v1",
        "input": str(input_path),
        "output": str(output_path),
        "anchor": anchor,
        "span": span,
        "occurrence": occurrence,
        "records": records,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--anchor", required=True)
    parser.add_argument("--span", type=int, default=1)
    parser.add_argument("--occurrence", type=int, default=1)
    args = parser.parse_args()
    print(
        json.dumps(
            patch_keep_with_next(
                args.input,
                args.output,
                anchor=args.anchor,
                span=args.span,
                occurrence=args.occurrence,
            ),
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
