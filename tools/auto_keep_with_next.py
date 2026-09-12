"""Apply ``keepWithNext`` to automatic question blocks in an HWPX package.

The HIGH-END integrated documents place a question stem (usually a paragraph
whose ``paraPrIDRef`` is ``29``) followed by its conditions and choices.  Some
of those choices are represented by paragraphs inside a nested table cell.
This helper discovers each block from one question heading to the next flow
heading, expands nested paragraphs in document order, and sets
``keepWithNext=1`` on every paragraph except the final one.

The operation is deliberately an offline HWPX rewrite.  It does not open
Hanword/COM, does not mutate the input package, and never overwrites an
existing output.  Paragraph properties are cloned per patched paragraph so
that shared source styles retain their original pagination behavior.  Every
clone receives a fresh ``id`` and each ``paraProperties/@itemCnt`` is updated
to the actual number of direct ``paraPr`` children.
"""
from __future__ import annotations

import argparse
import copy
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Iterable, Pattern
from zipfile import ZIP_DEFLATED, ZipFile


HEADER_PATH = "Contents/header.xml"
_SECTION_RE = re.compile(r"(?:^|/)section\d+\.xml$", re.IGNORECASE)
_SOLUTION_HEADING_RE = re.compile(
    r"^\s*(?:(?:[A-Za-z0-9ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]+(?:[-_.][A-Za-z0-9]+)?|\d+)\s+){0,3}"
    r"(?:해설\s*정답|정답\s*(?:및|/)?\s*풀이)\b",
    re.IGNORECASE,
)
_DEFAULT_DIRECT_HEADING_PATTERNS = (
    re.compile(r"^\s*(?:문항|문제)\s*[-.]?\s*\d+(?=$|[\s.)])", re.IGNORECASE),
    re.compile(r"^\s*question\s*[-.]?\s*\d+(?=$|[\s.)])", re.IGNORECASE),
    re.compile(r"^\s*q\s*[-.]?\s*\d+(?=$|[\s.)])", re.IGNORECASE),
)


def _local_name(tag: str) -> str:
    """Return an XML local name for namespaced and unnamespaced tags."""

    return str(tag).rsplit("}", 1)[-1].split(":", 1)[-1]


def _normalise_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _paragraph_text(paragraph: ET.Element, *, direct: bool = True) -> str:
    """Return visible text owned by *paragraph*.

    HWPX tables contain ``hp:p`` descendants.  When matching a heading, text
    from a nested cell must not make its enclosing layout paragraph appear to
    be the heading.  ``direct=True`` therefore skips descendant paragraphs;
    ``direct=False`` is useful for human-readable report previews.
    """

    chunks: list[str] = []

    def walk(node: ET.Element, *, is_root: bool = False) -> None:
        for child in list(node):
            local = _local_name(child.tag)
            if local == "p" and not (is_root and child is paragraph):
                if direct:
                    continue
            if local == "t":
                chunks.append(child.text or "")
            walk(child)

    walk(paragraph, is_root=True)
    return "".join(chunks)


def _paragraphs_in_document_order(paragraph: ET.Element) -> list[ET.Element]:
    """Return *paragraph* and all nested paragraphs in document order."""

    out: list[ET.Element] = [paragraph]

    def walk(node: ET.Element) -> None:
        for child in list(node):
            if _local_name(child.tag) == "p":
                out.append(child)
            walk(child)

    walk(paragraph)
    return out


def _compile_patterns(
    heading_regex: str | Pattern[str] | None,
) -> tuple[Pattern[str], ...]:
    if heading_regex is None:
        return _DEFAULT_DIRECT_HEADING_PATTERNS
    if isinstance(heading_regex, str):
        return (re.compile(heading_regex, re.IGNORECASE),)
    return (heading_regex,)


def _matches_direct_heading(
    paragraph: ET.Element,
    *,
    heading_texts: tuple[str, ...],
    heading_patterns: tuple[Pattern[str], ...],
) -> tuple[bool, str | None]:
    text = _normalise_text(_paragraph_text(paragraph, direct=True))
    if not text:
        return False, None
    for candidate in heading_texts:
        wanted = _normalise_text(candidate)
        if wanted and (text == wanted or text.startswith(wanted + " ") or text.startswith(wanted + "\u3000")):
            return True, f"text:{wanted}"
    for pattern in heading_patterns:
        if pattern.search(text):
            return True, f"regex:{pattern.pattern}"
    return False, None


def _is_solution_boundary(
    paragraph: ET.Element,
    *,
    boundary_para_pr_ids: frozenset[str],
) -> bool:
    """Recognise the solution anchor between item blocks.

    Integrated HWPX packages commonly store an endnote anchor as a paragraph
    containing only its automatic number; the visible ``해설정답`` text lives
    in the nested ``hp:endNote`` payload.  The anchor paragraph properties
    are stable (currently IDs ``20`` and ``34``), so accept those IDs in
    addition to the direct-text form used by simpler packages.
    """

    if paragraph.get("paraPrIDRef") in boundary_para_pr_ids:
        return True
    text = _normalise_text(_paragraph_text(paragraph, direct=True))
    if text and _SOLUTION_HEADING_RE.search(text):
        return True

    # Detect an endNote descendant without letting an endNote nested inside a
    # child paragraph turn that child paragraph's enclosing layout paragraph
    # into a boundary.  A paragraph is a flow item in its own right.
    def has_direct_endnote(node: ET.Element) -> bool:
        for child in list(node):
            local = _local_name(child.tag)
            if local == "p":
                continue
            if local == "endNote":
                return True
            if has_direct_endnote(child):
                return True
        return False

    return has_direct_endnote(paragraph)


def _is_question_heading(
    paragraph: ET.Element,
    *,
    heading_para_pr_ids: frozenset[str],
    heading_texts: tuple[str, ...],
    heading_patterns: tuple[Pattern[str], ...],
) -> tuple[bool, str | None]:
    ref = paragraph.get("paraPrIDRef")
    if ref in heading_para_pr_ids:
        return True, f"paraPrIDRef:{ref}"
    return _matches_direct_heading(
        paragraph,
        heading_texts=heading_texts,
        heading_patterns=heading_patterns,
    )


def _ancestor_depth(node: ET.Element, parent_map: dict[ET.Element, ET.Element]) -> int:
    depth = 0
    cursor = parent_map.get(node)
    while cursor is not None:
        depth += 1
        cursor = parent_map.get(cursor)
    return depth


def _heading_blocks(
    root: ET.Element,
    *,
    heading_para_pr_ids: frozenset[str],
    heading_texts: tuple[str, ...],
    heading_patterns: tuple[Pattern[str], ...],
    include_solution_boundaries: bool,
    boundary_para_pr_ids: frozenset[str],
) -> list[dict[str, Any]]:
    """Discover question blocks in every paragraph flow of *root*.

    HWPX paragraph flows are the direct ``hp:p`` children of a container
    (``hs:sec`` or ``hp:subList`` in the integrated files).  Selecting
    siblings inside each flow prevents a heading in one table cell from
    accidentally consuming paragraphs in a different cell.  Blocks are
    sorted deepest-first for reporting, but paragraph targets are merged by
    identity by the caller so nested/outer flow overlap is harmless.
    """

    parent_map = {child: parent for parent in root.iter() for child in parent}
    flows: list[tuple[int, int, ET.Element, list[tuple[int, ET.Element]]]] = []
    for order, parent in enumerate(root.iter()):
        paragraph_children = [
            (index, child)
            for index, child in enumerate(list(parent))
            if _local_name(child.tag) == "p"
        ]
        if paragraph_children:
            flows.append((_ancestor_depth(parent, parent_map), order, parent, paragraph_children))

    # A nested cell is a more precise flow than its enclosing layout
    # paragraph.  Target merging means the order does not change final XML,
    # but deepest-first makes report ordering stable and intuitive.
    flows.sort(key=lambda item: (-item[0], item[1]))
    blocks: list[dict[str, Any]] = []
    for depth, _order, parent, paragraph_children in flows:
        heading_positions: list[tuple[int, ET.Element, str]] = []
        boundary_positions: set[int] = set()
        for ordinal, (child_index, paragraph) in enumerate(paragraph_children):
            is_heading, reason = _is_question_heading(
                paragraph,
                heading_para_pr_ids=heading_para_pr_ids,
                heading_texts=heading_texts,
                heading_patterns=heading_patterns,
            )
            if is_heading:
                heading_positions.append((ordinal, paragraph, reason or "heading"))
                continue
            if include_solution_boundaries and _is_solution_boundary(
                paragraph,
                boundary_para_pr_ids=boundary_para_pr_ids,
            ):
                boundary_positions.add(ordinal)

        if not heading_positions:
            continue
        heading_starts = {ordinal for ordinal, _paragraph, _reason in heading_positions}
        for heading_ordinal, heading, reason in heading_positions:
            next_boundary = next(
                (
                    ordinal
                    for ordinal in range(heading_ordinal + 1, len(paragraph_children))
                    if ordinal in heading_starts or ordinal in boundary_positions
                ),
                len(paragraph_children),
            )
            selected = [
                paragraph_children[ordinal][1]
                for ordinal in range(heading_ordinal, next_boundary)
            ]
            expanded: list[ET.Element] = []
            seen: set[int] = set()
            for paragraph in selected:
                for nested in _paragraphs_in_document_order(paragraph):
                    marker = id(nested)
                    if marker not in seen:
                        expanded.append(nested)
                        seen.add(marker)
            if not expanded:
                continue
            boundary_kind = "end_of_flow"
            if next_boundary < len(paragraph_children):
                boundary_paragraph = paragraph_children[next_boundary][1]
                boundary_kind = (
                    "question_heading"
                    if next_boundary in heading_starts
                    else "solution_heading"
                )
            else:
                boundary_paragraph = None
            blocks.append(
                {
                    "parent": parent,
                    "depth": depth,
                    "heading": heading,
                    "heading_reason": reason,
                    "heading_text": _paragraph_text(heading, direct=True),
                    "selected": selected,
                    "paragraphs": expanded,
                    "boundary": boundary_paragraph,
                    "boundary_kind": boundary_kind,
                }
            )
    return blocks


def _para_property_nodes(
    header_root: ET.Element,
) -> tuple[dict[str, tuple[ET.Element, ET.Element]], list[ET.Element], int]:
    """Return ``id -> (container, paraPr)``, containers, and numeric max id."""

    mapping: dict[str, tuple[ET.Element, ET.Element]] = {}
    containers: list[ET.Element] = []
    max_id = -1
    for parent in header_root.iter():
        if _local_name(parent.tag) != "paraProperties":
            continue
        containers.append(parent)
        for child in list(parent):
            if _local_name(child.tag) != "paraPr":
                continue
            ident = child.get("id")
            if ident is None:
                continue
            if ident in mapping:
                raise ValueError(f"duplicate paragraph property id: {ident!r}")
            mapping[ident] = (parent, child)
            try:
                max_id = max(max_id, int(ident))
            except (TypeError, ValueError):
                pass
    if not containers:
        raise ValueError("HWPX header has no paraProperties container")
    return mapping, containers, max_id


def _break_setting(para_pr: ET.Element) -> ET.Element:
    setting = next(
        (node for node in para_pr.iter() if _local_name(node.tag) == "breakSetting"),
        None,
    )
    if setting is None:
        raise ValueError(f"paragraph property {para_pr.get('id')!r} has no breakSetting")
    return setting


def _next_style_id(
    max_id: int,
    style_map: dict[str, tuple[ET.Element, ET.Element]],
) -> tuple[str, int]:
    candidate = max_id + 1
    while str(candidate) in style_map:
        candidate += 1
    return str(candidate), candidate


def _register_namespaces() -> None:
    # Explicit prefixes keep rewritten HWPX readable and avoid arbitrary
    # ``ns0`` prefixes in generated reports.  Unknown source namespaces remain
    # valid through ElementTree's URI-qualified tags.
    namespaces = {
        "hh": "http://www.hancom.co.kr/hwpml/2011/head",
        "hp": "http://www.hancom.co.kr/hwpml/2011/paragraph",
        "hs": "http://www.hancom.co.kr/hwpml/2011/section",
        "hc": "http://www.hancom.co.kr/hwpml/2011/core",
    }
    for prefix, uri in namespaces.items():
        ET.register_namespace(prefix, uri)


def _section_member(name: str) -> bool:
    return bool(_SECTION_RE.search(name))


def patch_keep_with_next_blocks(
    input_path: Path,
    output_path: Path,
    *,
    heading_para_pr_ids: Iterable[str] = ("29",),
    heading_texts: Iterable[str] = (),
    heading_regex: str | Pattern[str] | None = None,
    include_solution_boundaries: bool = True,
    boundary_para_pr_ids: Iterable[str] = ("20", "34"),
    allow_no_headings: bool = False,
) -> dict[str, Any]:
    """Create a fresh HWPX with automatic question-block keep flags.

    ``heading_para_pr_ids`` defaults to ``("29",)`` for the integrated
    HIGH-END files.  ``heading_texts`` and ``heading_regex`` cover question
    headings whose style reference was lost and are matched against direct
    paragraph text only.  The default textual patterns recognise ``문항 1``,
    ``문제 1``, ``Question 1`` and ``Q1``; callers can pass an exact text or a
    regular expression for a project-specific heading convention.
    ``boundary_para_pr_ids`` identifies paragraph styles used by native
    endnote/solution anchors (default: ``20`` and ``34``).
    """

    input_path = Path(input_path).resolve()
    output_path = Path(output_path).resolve()
    if input_path == output_path:
        raise ValueError("output must be a fresh path")
    if not input_path.is_file():
        raise FileNotFoundError(input_path)
    if output_path.exists():
        raise FileExistsError(output_path)

    ids = frozenset(str(value) for value in heading_para_pr_ids)
    boundary_ids = frozenset(str(value) for value in boundary_para_pr_ids)
    texts = tuple(str(value) for value in heading_texts)
    patterns = _compile_patterns(heading_regex)
    entries: list[tuple[Any, bytes]] = []
    with ZipFile(input_path) as source:
        for info in source.infolist():
            entries.append((copy.copy(info), source.read(info.filename)))

    header_payload = next(
        (payload for info, payload in entries if info.filename == HEADER_PATH),
        None,
    )
    if header_payload is None:
        raise ValueError(f"HWPX {HEADER_PATH} is missing")
    try:
        header_root = ET.fromstring(header_payload)
    except ET.ParseError as exc:
        raise ValueError(f"invalid HWPX header XML: {exc}") from exc
    style_map, containers, max_style_id = _para_property_nodes(header_root)
    item_counts_before = [container.get("itemCnt") for container in containers]
    style_count_before = sum(
        1
        for container in containers
        for child in list(container)
        if _local_name(child.tag) == "paraPr"
    )

    section_roots: list[tuple[Any, ET.Element, list[dict[str, Any]]]] = []
    heading_count = 0
    for info, payload in entries:
        if not _section_member(info.filename):
            continue
        try:
            root = ET.fromstring(payload)
        except ET.ParseError as exc:
            raise ValueError(f"invalid section XML {info.filename}: {exc}") from exc
        blocks = _heading_blocks(
            root,
            heading_para_pr_ids=ids,
            heading_texts=texts,
            heading_patterns=patterns,
            include_solution_boundaries=include_solution_boundaries,
            boundary_para_pr_ids=boundary_ids,
        )
        heading_count += len(blocks)
        section_roots.append((info, root, blocks))

    if heading_count == 0 and not allow_no_headings:
        raise ValueError("no question headings found in HWPX section XML")

    # Merge overlapping outer/nested flow blocks by element identity.  A
    # paragraph is a target if any discovered block says it is not the final
    # paragraph of that block.
    target_paragraphs: dict[int, ET.Element] = {}
    block_reports: list[dict[str, Any]] = []
    for info, _root, blocks in section_roots:
        for block_index, block in enumerate(blocks):
            paragraphs: list[ET.Element] = block["paragraphs"]
            targets = paragraphs[:-1]
            for paragraph in targets:
                target_paragraphs[id(paragraph)] = paragraph
            block_reports.append(
                {
                    "section": info.filename,
                    "block_index": block_index,
                    "depth": block["depth"],
                    "heading_reason": block["heading_reason"],
                    "heading_text": _normalise_text(block["heading_text"]),
                    "paragraph_count": len(paragraphs),
                    "target_count": len(targets),
                    "boundary_kind": block["boundary_kind"],
                    "boundary_text": (
                        _normalise_text(_paragraph_text(block["boundary"], direct=True))
                        if block["boundary"] is not None
                        else None
                    ),
                }
            )

    # Map paragraph identity to the section name for per-record diagnostics.
    section_by_paragraph: dict[int, str] = {}
    offset_by_paragraph: dict[int, int] = {}
    for info, _root, blocks in section_roots:
        offset = 0
        for block in blocks:
            for paragraph in block["paragraphs"]:
                section_by_paragraph.setdefault(id(paragraph), info.filename)
                offset_by_paragraph.setdefault(id(paragraph), offset)
                offset += 1

    records: list[dict[str, Any]] = []
    for paragraph in target_paragraphs.values():
        source_id = paragraph.get("paraPrIDRef")
        if source_id is None or source_id not in style_map:
            raise ValueError(f"paragraph has unknown paraPrIDRef: {source_id!r}")
        source_container, source_style = style_map[source_id]
        cloned = copy.deepcopy(source_style)
        new_id, max_style_id = _next_style_id(max_style_id, style_map)
        cloned.set("id", new_id)
        _break_setting(cloned).set("keepWithNext", "1")
        source_container.append(cloned)
        style_map[new_id] = (source_container, cloned)
        paragraph.set("paraPrIDRef", new_id)
        records.append(
            {
                "section": section_by_paragraph.get(id(paragraph)),
                "paragraph_offset": offset_by_paragraph.get(id(paragraph)),
                "text": _normalise_text(_paragraph_text(paragraph, direct=True)),
                "source_paraPrIDRef": source_id,
                "patched_paraPrIDRef": new_id,
                "keepWithNext": "1",
            }
        )

    # ``itemCnt`` is metadata, not a hint.  Keep it coherent for every
    # paraProperties container that declares it, even when no target was
    # found in that particular section.
    item_counts_after: list[str | None] = []
    for container in containers:
        actual = sum(1 for child in list(container) if _local_name(child.tag) == "paraPr")
        if container.get("itemCnt") is not None:
            container.set("itemCnt", str(actual))
            item_counts_after.append(str(actual))
        else:
            item_counts_after.append(None)

    _register_namespaces()
    updated_header = ET.tostring(header_root, encoding="utf-8", xml_declaration=True)
    payload_by_name: dict[str, bytes] = {}
    for info, root, _blocks in section_roots:
        payload_by_name[info.filename] = ET.tostring(root, encoding="utf-8", xml_declaration=True)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    # The output is opened only after all XML validation and rewriting has
    # succeeded, so malformed input cannot leave a misleading partial target.
    with ZipFile(output_path, "w", ZIP_DEFLATED) as target:
        for info, payload in entries:
            if info.filename == HEADER_PATH:
                payload = updated_header
            elif info.filename in payload_by_name:
                payload = payload_by_name[info.filename]
            target.writestr(info, payload)

    return {
        "status": "PASS",
        "schema": "hwp-keep-with-next-blocks-v1",
        "input": str(input_path),
        "output": str(output_path),
        "heading_para_pr_ids": sorted(ids),
        "heading_texts": list(texts),
        "heading_regex": heading_regex.pattern if hasattr(heading_regex, "pattern") else heading_regex,
        "include_solution_boundaries": include_solution_boundaries,
        "boundary_para_pr_ids": sorted(boundary_ids),
        "heading_count": heading_count,
        "block_count": len(block_reports),
        "patched_paragraph_count": len(records),
        "style_count_before": style_count_before,
        "style_count_after": sum(
            1
            for container in containers
            for child in list(container)
            if _local_name(child.tag) == "paraPr"
        ),
        "item_counts_before": item_counts_before,
        "item_counts_after": item_counts_after,
        "blocks": block_reports,
        "records": records,
    }


# Both names are intentionally public: the longer one is explicit in scripts,
# while the short alias is convenient for callers that already call the
# operation an "auto keep" pass.
auto_keep_with_next_blocks = patch_keep_with_next_blocks
patch_hwpx_keep_with_next_blocks = patch_keep_with_next_blocks


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument(
        "--heading-para-id",
        action="append",
        dest="heading_para_pr_ids",
        default=None,
        help="paraPrIDRef used for question headings (repeatable; default: 29)",
    )
    parser.add_argument(
        "--heading-text",
        action="append",
        dest="heading_texts",
        default=[],
        help="exact direct heading text/prefix (repeatable)",
    )
    parser.add_argument(
        "--heading-regex",
        default=None,
        help="regular expression matched against direct heading text",
    )
    parser.add_argument(
        "--no-solution-boundaries",
        action="store_true",
        help="do not stop blocks at direct solution text or native anchors",
    )
    parser.add_argument(
        "--boundary-para-id",
        action="append",
        dest="boundary_para_pr_ids",
        default=None,
        help="paraPrIDRef used for native solution/endnote anchors (repeatable; defaults: 20, 34)",
    )
    parser.add_argument(
        "--allow-no-headings",
        action="store_true",
        help="write an unchanged package when no configured heading is found",
    )
    args = parser.parse_args(argv)
    heading_para_pr_ids = args.heading_para_pr_ids or ["29"]
    boundary_para_pr_ids = args.boundary_para_pr_ids or ["20", "34"]
    report = patch_keep_with_next_blocks(
        args.input,
        args.output,
        heading_para_pr_ids=heading_para_pr_ids,
        heading_texts=args.heading_texts,
        heading_regex=args.heading_regex,
        include_solution_boundaries=not args.no_solution_boundaries,
        boundary_para_pr_ids=boundary_para_pr_ids,
        allow_no_headings=args.allow_no_headings,
    )
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
