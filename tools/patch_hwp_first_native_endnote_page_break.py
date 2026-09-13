"""Force the first native HWP endnote body onto a fresh physical page.

``END_OF_DOCUMENT`` means that Hanword renders native endnotes after the
main story, but it does *not* guarantee that the first endnote does not share
the final problem page.  For classroom handouts, that physical boundary is a
separate contract: all questions must be visible first and the first answer /
solution endnote must begin on the next page.

This tool is deliberately narrow.  It creates a new HWPX package and changes
only the page-break attribute on the existing empty terminal main-story
paragraph.  That puts a physical page boundary *between* the main story and
the endnote region; a page break inside an ``hp:endNote`` body is not honored
by every Hanword version.  Main-story text, equations, pictures, tables,
endnote references, and all endnote bodies remain untouched.  A Hanword serial
save/reopen and rendered-page audit remain mandatory after this offline patch.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile
import xml.etree.ElementTree as ET


REQUIRED_PLACEMENT = "END_OF_DOCUMENT"


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].split(":", 1)[-1]


def _section_members(archive: ZipFile) -> list[str]:
    members = [
        name
        for name in archive.namelist()
        if re.search(r"(?:^|/)section\d+\.xml$", name, flags=re.IGNORECASE)
    ]

    def sort_key(name: str) -> tuple[int, str]:
        match = re.search(r"section(\d+)\.xml$", name, flags=re.IGNORECASE)
        return (int(match.group(1)) if match else 2**31 - 1, name.lower())

    return sorted(members, key=sort_key)


def _placement_values(root: ET.Element) -> list[str]:
    values: list[str] = []
    for property_element in root.iter():
        if _local_name(property_element.tag) != "endNotePr":
            continue
        placements = [
            element
            for element in property_element.iter()
            if _local_name(element.tag) == "placement"
        ]
        if not placements:
            values.append("")
            continue
        for placement in placements:
            values.append(
                next(
                    (
                        value
                        for key, value in placement.attrib.items()
                        if _local_name(key) == "place"
                    ),
                    "",
                )
                .strip()
                .upper()
            )
    return values


def _paragraph_text(paragraph: ET.Element) -> str:
    return "".join(node.text or "" for node in paragraph.iter() if _local_name(node.tag) == "t")


def _locate_first_endnote(
    sections: dict[str, ET.Element],
    ordered_members: list[str],
) -> tuple[str, ET.Element, ET.Element, int]:
    note_count = 0
    for member in ordered_members:
        root = sections[member]
        for note in root.iter():
            if _local_name(note.tag) != "endNote":
                continue
            note_count += 1
            paragraphs = [element for element in note.iter() if _local_name(element.tag) == "p"]
            if not paragraphs:
                raise ValueError(f"first native endnote has no body paragraph: {member}")
            return member, note, paragraphs[0], note_count
    raise ValueError("HWPX package has no native endnote")


def _has_visible_content(paragraph: ET.Element) -> bool:
    """Whether a terminal paragraph contains more than a layout-only shell."""

    ignored = {"p", "run", "linesegarray", "lineseg"}
    for element in paragraph.iter():
        local = _local_name(element.tag)
        if local == "t" and (element.text or "").strip():
            return True
        if local not in ignored and local != "t":
            return True
    return False


def _locate_terminal_main_story_paragraph(
    sections: dict[str, ET.Element], ordered_members: list[str]
) -> tuple[str, ET.Element, int]:
    """Return the existing blank direct paragraph at the end of the main story.

    Native endnote bodies are nested controls, not direct section paragraphs.
    Requiring a pre-existing empty terminal paragraph avoids creating a new
    text object or accidentally moving the final question itself to a new page.
    Writers must emit this normal terminal shell before the endnote stage.
    """

    for member in reversed(ordered_members):
        root = sections[member]
        direct_paragraphs = [element for element in list(root) if _local_name(element.tag) == "p"]
        if not direct_paragraphs:
            continue
        paragraph = direct_paragraphs[-1]
        if _paragraph_text(paragraph).strip() or _has_visible_content(paragraph):
            raise ValueError(
                "terminal main-story paragraph is not empty; writer must supply a blank terminal paragraph "
                "before the native-endnote fresh-page patch"
            )
        return member, paragraph, len(direct_paragraphs) - 1
    raise ValueError("HWPX package has no direct main-story paragraph for the endnote page boundary")


def patch_first_native_endnote_page_break(input_path: Path, output_path: Path) -> dict[str, Any]:
    """Create a derived HWPX whose first native endnote starts on a new page."""

    input_path = input_path.resolve()
    output_path = output_path.resolve()
    if input_path == output_path:
        raise ValueError("output must be a fresh path")
    if output_path.exists():
        raise FileExistsError(output_path)
    if not input_path.is_file():
        raise FileNotFoundError(input_path)

    before_bytes = input_path.read_bytes()
    with ZipFile(input_path) as source:
        section_names = _section_members(source)
        if not section_names:
            raise ValueError("HWPX package has no section XML")
        payloads = {info.filename: source.read(info.filename) for info in source.infolist()}
        infos = list(source.infolist())
    sections = {
        member: ET.fromstring(payloads[member])
        for member in section_names
    }
    placements = [
        value
        for root in sections.values()
        for value in _placement_values(root)
    ]
    if not placements or any(value != REQUIRED_PLACEMENT for value in placements):
        raise ValueError(
            "native endnote placement must be explicit END_OF_DOCUMENT before physical-boundary patch"
        )

    _first_note_member, _note, _first_note_paragraph, first_note_number = _locate_first_endnote(
        sections, section_names
    )
    member, paragraph, terminal_main_paragraph_index = _locate_terminal_main_story_paragraph(
        sections, section_names
    )
    before = paragraph.attrib.get("pageBreak", "0")
    paragraph.set("pageBreak", "1")
    after = paragraph.attrib.get("pageBreak", "0")
    text = _paragraph_text(paragraph)

    ET.register_namespace("hp", "http://www.hancom.co.kr/hwpml/2011/paragraph")
    ET.register_namespace("hs", "http://www.hancom.co.kr/hwpml/2011/section")
    payloads[member] = ET.tostring(sections[member], encoding="utf-8", xml_declaration=True)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output_path, "w", ZIP_DEFLATED) as target:
        for info in infos:
            target.writestr(info, payloads[info.filename])

    output_bytes = output_path.read_bytes()
    return {
        "schema": "hwp-first-native-endnote-new-page-patch-v1",
        "status": "PASS",
        "input": str(input_path),
        "output": str(output_path),
        "input_sha256": hashlib.sha256(before_bytes).hexdigest(),
        "output_sha256": hashlib.sha256(output_bytes).hexdigest(),
        "endnote_placement": REQUIRED_PLACEMENT,
        "first_native_endnote_number": first_note_number,
        "section": member,
        "terminal_main_paragraph_index": terminal_main_paragraph_index,
        "terminal_main_paragraph_text": text,
        "page_break_before": before,
        "page_break_after": after,
        "changed": before != after,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create a new HWPX whose first native endnote body begins on a fresh page."
    )
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    report = patch_first_native_endnote_page_break(args.input, args.output)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
