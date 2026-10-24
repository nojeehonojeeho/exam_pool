"""Pure, content-agnostic gates for native university-document collections.

No textbook content, COM activation, file mutation, or implicit PASS escalation.
"""
from __future__ import annotations

import hashlib
import json
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET


class CollectionGateError(ValueError):
    pass


def assert_exact_pair(problem_ids: list[str], solution_ids: list[str]) -> None:
    if problem_ids != solution_ids:
        raise CollectionGateError("PROBLEM_SOLUTION_ORDER_MISMATCH")
    if len(problem_ids) != len(set(problem_ids)):
        raise CollectionGateError("DUPLICATE_CANONICAL_ID")
    if not problem_ids:
        raise CollectionGateError("EMPTY_COLLECTION")


def assert_partition(total: int, regions: list[tuple[int, int]], retained_context: list[int]) -> None:
    """All body paragraphs must be owned exactly once, including shared context."""
    seen = set()
    for start, stop in regions:
        if not 0 <= start < stop <= total:
            raise CollectionGateError("INVALID_NATIVE_REGION")
        for index in range(start, stop):
            if index in seen:
                raise CollectionGateError("OVERLAPPING_NATIVE_REGIONS")
            seen.add(index)
    for index in retained_context:
        if not 0 <= index < total or index in seen:
            raise CollectionGateError("INVALID_OR_DUPLICATE_SHARED_CONTEXT")
        seen.add(index)
    if seen != set(range(total)):
        raise CollectionGateError("UNACCOUNTED_NATIVE_PARAGRAPH")


def source_digest(path: str | Path) -> str:
    with Path(path).open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def assert_bound_file(path: str | Path, expected_sha256: str) -> None:
    if not Path(path).is_file() or source_digest(path) != expected_sha256:
        raise CollectionGateError("SOURCE_OR_EVIDENCE_HASH_CHANGED")


def audit_native_references(path: str | Path) -> dict:
    """Check imported char/para/style/border/tab and image reference bindings.

    Definitions with identical numeric IDs in different tables are intentional.
    This checks referential integrity, not that two styles have equal semantics.
    Hanword's native InsertFile API performs the actual cross-document remapping.
    """
    local = lambda element: element.tag.rsplit("}", 1)[-1]
    targets = {
        "charPrIDRef": "charPr", "paraPrIDRef": "paraPr",
        "styleIDRef": "style", "nextStyleIDRef": "style",
        "borderFillIDRef": "borderFill", "tabPrIDRef": "tabPr",
    }
    with zipfile.ZipFile(path) as archive:
        if archive.testzip() is not None:
            raise CollectionGateError("HWPX_ZIP_CORRUPT")
        header = ET.fromstring(archive.read("Contents/header.xml"))
        definitions = {kind: {e.get("id") for e in header.iter() if local(e) == kind}
                       for kind in targets.values()}
        manifest = ET.fromstring(archive.read("Contents/content.hpf"))
        binaries = {e.get("id"): e.get("href") for e in manifest.iter()
                    if e.get("id") and e.get("href")}
        sections = [ET.fromstring(archive.read(name)) for name in archive.namelist()
                    if re.fullmatch(r"Contents/section\d+\.xml", name)]
        used_paras = {e.get("paraPrIDRef") for root in sections for e in root.iter()
                      if local(e) == "p"}
        active_numbering = any(local(e) == "paraPr" and e.get("id") in used_paras
                               and any(local(x) == "heading" and x.get("type", "NONE") != "NONE"
                                       for x in e.iter()) for e in header.iter())
        checked = 0
        unused_numbering_records = 0
        for root in [header, *sections]:
            for element in root.iter():
                for attr, value in element.attrib.items():
                    if attr in targets:
                        # Hanword-generated, unused numbering templates are not
                        # body font references. Do not relax this for active
                        # numbering or a body run with an invalid charPr ID.
                        if (root is header and local(element) == "paraHead"
                                and attr == "charPrIDRef" and value == "4294967295"
                                and not active_numbering):
                            unused_numbering_records += 1
                            continue
                        if value not in definitions[targets[attr]]:
                            raise CollectionGateError(f"UNBOUND_{attr}:{value}")
                        checked += 1
                    elif attr == "binaryItemIDRef":
                        filename = binaries.get(value)
                        if not filename:
                            raise CollectionGateError(f"UNBOUND_BINARY:{value}")
                        filename = filename.removeprefix("../")
                        if filename not in archive.namelist():
                            filename = "Contents/" + filename
                        if filename not in archive.namelist():
                            raise CollectionGateError(f"MISSING_BINARY_PAYLOAD:{value}")
                        checked += 1
        return {"status": "REFERENCES_BOUND", "checked_references": checked,
                "unused_numbering_auto_char_records": unused_numbering_records,
                "source_semantics_verified": False}


def release_decision(gates: dict[str, bool | None], evidence: dict[str, dict]) -> dict:
    """Missing, false, or stale evidence can never become FINAL by aggregation."""
    required = ("source", "math", "equations", "figures", "style", "com", "all_pages")
    unresolved = []
    for gate in required:
        item = evidence.get(gate, {})
        if gates.get(gate) is not True or not item.get("path") or not item.get("sha256"):
            unresolved.append(gate)
            continue
        try:
            assert_bound_file(item["path"], item["sha256"])
        except CollectionGateError:
            unresolved.append(gate)
    return {"FINAL": not unresolved, "status": "PASS" if not unresolved else "NOT_FINAL",
            "unresolved_gates": unresolved}


def classify_korean_render_fonts(spans: list[dict], equation_scripts: list[str]) -> dict:
    """Separate body font substitution from Korean text inside native equations.

    A math-text exception must bind to an unchanged equation occurrence. This is
    not permission to accept arbitrary non-KoPub Korean body text. The caller
    must also verify every used HWPX body charPr against the style contract.
    """
    exceptions = []
    for span in spans:
        text, font = span["text"], span["font"]
        if not re.search("[가-힣]", text) or "KoPub" in font:
            continue
        token = text.strip()
        occurrences = [i for i, script in enumerate(equation_scripts) if token and token in script]
        if font not in {"Haansoft Batang", "HancomEQN", "HYhwpEQ"} or not occurrences:
            raise CollectionGateError("KOPUB_FONT_NOT_ACTIVE")
        exceptions.append({"text": text, "font": font, "bbox": span.get("bbox"),
                           "native_equation_occurrences": occurrences})
    return {"body_font_substitution_count": 0, "native_math_text_font_exceptions": exceptions}
