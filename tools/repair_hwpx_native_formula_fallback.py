"""Repair one known plain-text formula fallback in a copied HWPX package.

The repair is intentionally narrow and fail-closed.  It converts an exact
formula span in an ``hp:t`` node into a native ``hp:equation`` object by
cloning an equation from the same paragraph.  The input is never modified;
the output must be a new path.  This is useful for a controlled candidate
repair while a full HWP COM round-trip is pending.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from lxml import etree


HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
SECTION_RE = re.compile(r"Contents/section\d+\.xml$")

# This is the exact source span found in HE-P-099's solution.  Do not broaden
# this replacement without a reviewed source manifest and a new test fixture.
DEFAULT_TEXT = r"정답 ④E(X)=E(\bar{X})=18이므로"
DEFAULT_SCRIPT = "E(X)=E(bar{X})=18"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _numeric_attr_max(root: etree._Element, attr: str) -> int:
    values: list[int] = []
    for node in root.iter():
        raw = node.get(attr)
        if raw is None:
            continue
        try:
            values.append(int(raw))
        except ValueError:
            continue
    return max(values, default=0)


def _set_script(equation: etree._Element, script: str) -> None:
    script_node = equation.find(HP + "script")
    if script_node is None:
        script_node = etree.Element(HP + "script")
        equation.insert(0, script_node)
    script_node.text = script


def _set_size(equation: etree._Element, *, width: int = 6000, height: int = 1350) -> None:
    size = equation.find(HP + "sz")
    if size is None:
        size = etree.Element(HP + "sz")
        equation.insert(0, size)
    size.set("width", str(width))
    size.set("height", str(height))
    size.set("widthRelTo", "ABSOLUTE")
    size.set("heightRelTo", "ABSOLUTE")


def _repair_section(
    xml: bytes,
    *,
    target_text: str,
    formula_script: str,
    paragraph_number: int | None,
    next_id: int,
    next_zorder: int,
) -> tuple[bytes, dict[str, object], int, int]:
    parser = etree.XMLParser(remove_blank_text=False, resolve_entities=False)
    root = etree.fromstring(xml, parser)
    paragraphs = root.xpath(".//hp:p", namespaces={"hp": HP[1:-1]})
    matches: list[tuple[etree._Element, etree._Element]] = []
    for index, paragraph in enumerate(paragraphs, start=1):
        if paragraph_number is not None and index != paragraph_number:
            continue
        # Only text nodes in runs directly owned by this paragraph count.
        # Ancestor paragraphs in HWPX can contain nested tables/endnotes; using
        # ``.//hp:t`` there would count the same occurrence multiple times.
        for text_node in paragraph.xpath("./hp:run/hp:t", namespaces={"hp": HP[1:-1]}):
            if text_node.text and target_text in text_node.text:
                matches.append((paragraph, text_node))
    if len(matches) != 1:
        raise ValueError(f"expected exactly one target span, found {len(matches)}")
    paragraph, text_node = matches[0]
    run = text_node.getparent()
    if run is None or run.tag != HP + "run":
        raise ValueError("target hp:t is not a direct child of hp:run")
    template = paragraph.find(".//" + HP + "equation")
    if template is None:
        raise ValueError("target paragraph has no native equation template")
    original = text_node.text or ""
    if target_text not in original:
        raise ValueError("target span disappeared before replacement")
    if not target_text:
        raise ValueError("target text must not be empty")
    # This repair is deliberately tied to the reviewed source span.  Keep
    # the answer marker and trailing prose as ordinary text and make only the
    # mathematical middle a native equation.
    formula_start = original.find("E(X)=")
    formula_end = original.find("이므로", formula_start)
    if formula_start < 0 or formula_end < 0:
        raise ValueError("reviewed target does not contain the expected formula span")
    answer_prefix = original[:formula_start]
    trailing = original[formula_end:]
    text_node.text = answer_prefix
    clone = copy.deepcopy(template)
    clone.set("id", str(next_id))
    clone.set("zOrder", str(next_zorder))
    _set_script(clone, formula_script)
    _set_size(clone)
    index_in_run = run.index(text_node)
    run.insert(index_in_run + 1, clone)
    trailing_node = etree.Element(HP + "t")
    trailing_node.text = trailing
    run.insert(index_in_run + 2, trailing_node)
    repaired = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
    report = {
        "paragraph_number": paragraphs.index(paragraph) + 1,
        "target_text": target_text,
        "formula_script": formula_script,
        "equation_id": str(next_id),
        "equation_zOrder": str(next_zorder),
        "original_text": original,
        "replacement_text": answer_prefix + trailing,
    }
    return repaired, report, next_id + 1, next_zorder + 1


def _count_target_spans(xml: bytes, target_text: str) -> int:
    parser = etree.XMLParser(remove_blank_text=False, resolve_entities=False)
    root = etree.fromstring(xml, parser)
    return sum(
        1
        for text_node in root.xpath(".//hp:p/hp:run/hp:t", namespaces={"hp": HP[1:-1]})
        if text_node.text and target_text in text_node.text
    )


def repair_hwpx(
    input_path: Path,
    output_path: Path,
    *,
    target_text: str = DEFAULT_TEXT,
    formula_script: str = DEFAULT_SCRIPT,
    paragraph_number: int | None = None,
) -> dict[str, object]:
    input_path = Path(input_path).resolve()
    output_path = Path(output_path).resolve()
    if input_path.suffix.casefold() != ".hwpx" or output_path.suffix.casefold() != ".hwpx":
        raise ValueError("input and output must be HWPX files")
    if not input_path.is_file():
        raise FileNotFoundError(input_path)
    if output_path.exists():
        raise FileExistsError(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    next_id = 1
    next_zorder = 1
    replacements: list[dict[str, object]] = []
    with ZipFile(input_path, "r") as source:
        members = source.infolist()
        section_bytes: dict[str, bytes] = {}
        for info in members:
            data = source.read(info.filename)
            if SECTION_RE.fullmatch(info.filename):
                # Compute unique values per section before mutation.
                parser = etree.XMLParser(remove_blank_text=False, resolve_entities=False)
                root = etree.fromstring(data, parser)
                next_id = max(next_id, _numeric_attr_max(root, "id") + 1)
                next_zorder = max(next_zorder, _numeric_attr_max(root, "zOrder") + 1)
                section_bytes[info.filename] = data
            else:
                section_bytes[info.filename] = data
        total_matches = sum(
            _count_target_spans(data, target_text)
            for name, data in section_bytes.items()
            if SECTION_RE.fullmatch(name)
        )
        if total_matches != 1:
            raise ValueError(f"expected exactly one target span, found {total_matches}")
        changed = False
        for name in sorted(section_bytes):
            if not SECTION_RE.fullmatch(name):
                continue
            try:
                patched, report, next_id, next_zorder = _repair_section(
                    section_bytes[name],
                    target_text=target_text,
                    formula_script=formula_script,
                    paragraph_number=paragraph_number,
                    next_id=next_id,
                    next_zorder=next_zorder,
                )
            except ValueError as exc:
                if "found 0" in str(exc):
                    continue
                raise
            section_bytes[name] = patched
            replacements.append({"section": name, **report})
            changed = True
    if len(replacements) != 1 or not changed:
        raise ValueError(f"expected one replacement, found {len(replacements)}")
    with ZipFile(output_path, "w", ZIP_DEFLATED) as dest:
        for info in members:
            # HWPX uses ZIP members; preserving names and content is enough
            # for this derived candidate.  Compression metadata may differ.
            dest.writestr(info.filename, section_bytes[info.filename])
    return {
        "schema": "hwpx-native-formula-fallback-repair-v1",
        "status": "PASS",
        "input": str(input_path),
        "input_sha256": _sha256(input_path),
        "output": str(output_path),
        "output_sha256": _sha256(output_path),
        "replacements": replacements,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--paragraph-number", type=int)
    args = parser.parse_args(argv)
    try:
        result = repair_hwpx(args.input, args.output, paragraph_number=args.paragraph_number)
    except Exception as exc:
        result = {"schema": "hwpx-native-formula-fallback-repair-v1", "status": "FAIL", "error": repr(exc)}
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 2
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
