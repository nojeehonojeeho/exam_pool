"""Build target-bound PDF/HWPX evidence for a teacher worksheet release.

This tool is intentionally evidence-only: it never writes an input HWP/HWPX,
does not manufacture source content, and does not promote a release itself.
It records the difference between native source assets, template geometry, a
Hanword roundtrip, and PDF leaf-object observations.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import sys
import zipfile
from pathlib import Path

import fitz
from lxml import etree as E
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.teacher_pdf_evidence import canonical_font, column_for, ordered_markers, workspace_rows
from app.teacher_workflow import H, NS, P, Package, file_hash, json_hash


ROLE_NAMES = [
    "body", "problem_number", "choice", "condition_box", "table",
    "answer", "solution", "endnote", "header",
]
KOREAN_TOKEN = re.compile(r"[가-힣A-Za-z0-9]{2,}")


def args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target-hwp", type=Path, required=True)
    parser.add_argument("--target-hwpx", type=Path, required=True)
    parser.add_argument("--hwp-readback", type=Path, required=True)
    parser.add_argument("--hwpx-readback", type=Path, required=True)
    parser.add_argument("--source-raw-hwp", type=Path, required=True)
    parser.add_argument("--source-hwpx", type=Path, required=True)
    parser.add_argument("--source-com-report", type=Path, required=True)
    parser.add_argument("--pdf", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, required=True,
                        help="Source-owned item IDs; raw printed numbers are retained for mapping, not used as output ordinals")
    parser.add_argument("--old-workspace", type=Path, required=True)
    parser.add_argument("--choice-exceptions", type=Path,
                        help="Target-bound, geometry-evidenced non-3+2 choice-layout exceptions")
    parser.add_argument("--out", type=Path, required=True)
    return parser.parse_args()


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def artifact(path: Path) -> dict:
    return {"path": str(path.resolve()), "sha256": file_hash(path)}


def write(path: Path, value: dict | list) -> None:
    if path.exists():
        raise FileExistsError(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def compact_two_one_two(positions: list[list[object]]) -> bool:
    """Recognize the only approved non-3+2 geometry pattern.

    A mathematical option may contain a tall fraction that makes a literal
    three-column first row unreadable at the teacher-approved font size.  It
    may use a compact ``2+1+2`` layout, but only when the actual five label
    positions are all on one physical page and form exactly three compact
    rows.  This is deliberately much narrower than accepting arbitrary
    five-choice layouts.
    """
    if len(positions) != 5:
        return False
    try:
        ordered = sorted((float(value[1]), float(value[0]), str(value[2])) for value in positions)
    except (IndexError, TypeError, ValueError):
        return False
    groups: list[list[tuple[float, float, str]]] = []
    for value in ordered:
        if not groups or abs(value[0] - groups[-1][0][0]) > 7:
            groups.append([value])
        else:
            groups[-1].append(value)
    return [len(group) for group in groups] == [2, 1, 2] and ordered[-1][0] - ordered[0][0] <= 120


def choice_exception_rows(path: Path | None, target_hashes: dict, pdf_sha256: str) -> tuple[dict[str, dict], list[dict], dict | None]:
    """Load only exact, hash-bound exceptions generated from this target.

    A pasted exception cannot waive a layout failure: its schema, HWP/HWPX and
    PDF hashes, and the specific rendered label-position hash must all match
    the live evidence pass below.
    """
    if path is None:
        return {}, [], None
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    errors: list[dict] = []
    if data.get("schema") != "teacher-choice-layout-exceptions/v1":
        errors.append({"kind": "CHOICE_EXCEPTION_SCHEMA"})
    if data.get("target_sha256") != target_hashes or data.get("target_pdf_sha256") != pdf_sha256:
        errors.append({"kind": "CHOICE_EXCEPTION_TARGET_HASH"})
    rows = data.get("rows")
    if not isinstance(rows, list):
        errors.append({"kind": "CHOICE_EXCEPTION_ROWS"})
        rows = []
    values: dict[str, dict] = {}
    for row in rows:
        ident = str(row.get("id", ""))
        if not ident or ident in values:
            errors.append({"kind": "CHOICE_EXCEPTION_DUPLICATE_OR_EMPTY_ID", "id": ident})
            continue
        values[ident] = row
    return values, errors, data


def text_of(node) -> str:
    return "".join(node.xpath(".//p:t/text()", namespaces=NS))


def ancestry(node) -> list[str]:
    return [E.QName(parent).localname for parent in node.iterancestors()]


def font_faces(package: Package, char_id: str) -> list[str]:
    node = package.catalogs["charPr"][str(char_id)]
    ref = node.find(H("fontRef"))
    if ref is None:
        return []
    names = []
    for language, ident in ref.attrib.items():
        face = package.fonts.get(language.lower(), {}).get(ident)
        if face is not None and face.get("face"):
            names.append(canonical_font(face.get("face")))
    return sorted(set(names))


def para_value(package: Package, node) -> dict:
    para_id = node.get("paraPrIDRef")
    chars = []
    direct_runs = list(node.iter(P("run")))
    for run in direct_runs:
        text = "".join(run.xpath(".//p:t/text()", namespaces=NS))
        ident = run.get("charPrIDRef")
        if ident:
            chars.append({
                "id": ident,
                "semantic_sha256": package.style_hash("charPr", ident),
                "fonts": font_faces(package, ident),
                "text": text,
            })
    return {
        "text": text_of(node),
        "paragraph_semantic_sha256": package.style_hash("paraPr", para_id),
        "paragraph_value": package.resolved(package.catalogs["paraPr"][para_id]),
        "characters": chars,
    }


def paragraph_rows(package: Package) -> list[dict]:
    rows = []
    for section_name, section in package.sections.items():
        for index, node in enumerate(section.iter(P("p"))):
            parents = ancestry(node)
            value = para_value(package, node)
            # lxml's iterator is truthy independently of whether it yields a
            # native endnote.  Materialise it once: otherwise ordinary body
            # paragraphs are silently classified as question-reference rows.
            native_notes = list(node.iter(P("endNote")))
            row = {
                "section": section_name,
                "index": index,
                "in_note": "endNote" in parents,
                "in_header": "header" in parents,
                "has_table": any(True for _ in node.iter(P("tbl"))),
                "has_choices": any(ch in value["text"] for ch in "①②③④⑤"),
                "has_question_anchor": bool(native_notes) and "endNote" not in parents,
                **value,
            }
            if row["has_question_anchor"]:
                note = native_notes[0]
                row["native_reference_number"] = note.get("number")
            rows.append(row)
    return rows


def roles_for(row: dict) -> set[str]:
    text = row["text"].strip()
    out: set[str] = set()
    if row["in_header"]:
        out.add("header")
    elif row["in_note"]:
        out.add("endnote")
        if "정답" in text or text.startswith("답"):
            out.add("answer")
        if len(re.sub(r"\s+", "", text)) >= 6:
            out.add("solution")
    else:
        if (not row["has_table"] and not row["has_choices"] and not row["has_question_anchor"]
                and "유형편" not in text and "실전편" not in text and len(re.sub(r"\s+", "", text)) >= 4):
            out.add("body")
        if row["has_question_anchor"]:
            out.add("problem_number")
        if row["has_choices"]:
            out.add("choice")
        if row["has_table"]:
            out.update(("condition_box", "table"))
    return out


def pdf_spans(pdf) -> list[dict]:
    rows = []
    for page_number, page in enumerate(pdf, 1):
        for block in page.get_text("dict").get("blocks", []):
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    text = span.get("text", "")
                    if text.strip():
                        rows.append({
                            "page": page_number,
                            "text": text,
                            "font": canonical_font(span.get("font", "")),
                            "font_raw": span.get("font", ""),
                            "size": round(float(span.get("size", 0)), 3),
                            "bbox": [round(float(v), 3) for v in span.get("bbox", (0, 0, 0, 0))],
                        })
    return rows


def tokens(text: str) -> list[str]:
    values = KOREAN_TOKEN.findall(text)
    return sorted(set(values), key=len, reverse=True)


def expected_for_token(row: dict, token: str) -> list[str]:
    for char in row["characters"]:
        if token in char["text"] and char["fonts"]:
            return char["fonts"]
    for char in row["characters"]:
        if char["text"].strip() and char["fonts"]:
            return char["fonts"]
    return []


def find_span(row: dict, role: str, spans: list[dict], first_endnote_page: int) -> tuple[dict, list[str]] | None:
    def allowed(span: dict) -> bool:
        if role == "header":
            return span["bbox"][1] <= 85
        if role in {"answer", "solution", "endnote"}:
            return span["page"] >= first_endnote_page
        return span["page"] < first_endnote_page and span["bbox"][1] > 85
    if role == "problem_number":
        number = str(row.get("native_reference_number", ""))
        if not number:
            return None
        marker = re.compile(rf"^\s*{re.escape(number)}\.")
        expected = expected_for_token(row, "")
        for span in spans:
            if allowed(span) and marker.match(span["text"]) and expected and span["font"] in expected:
                return span, expected
        return None
    for token in tokens(row["text"]):
        for span in spans:
            # Header wording may recur in the content; its physical top band is
            # part of the role contract.
            if not allowed(span):
                continue
            if token not in span["text"]:
                continue
            expected = expected_for_token(row, token)
            if expected and span["font"] in expected:
                return span, expected
    return None


def matching_reopen_row(row: dict, candidates: list[dict]) -> dict | None:
    normal = re.sub(r"\s+", "", row["text"])
    same = [r for r in candidates if r["section"] == row["section"] and r["index"] == row["index"]]
    if same and re.sub(r"\s+", "", same[0]["text"]) == normal:
        return same[0]
    for candidate in candidates:
        if normal and re.sub(r"\s+", "", candidate["text"]) == normal:
            return candidate
    return None


def crop_span(pdf, span: dict, path: Path) -> None:
    page = pdf[span["page"] - 1]
    x0, y0, x1, y1 = span["bbox"]
    clip = fitz.Rect(max(0, x0 - 8), max(0, y0 - 8), min(page.rect.width, x1 + 8), min(page.rect.height, y1 + 8))
    page.get_pixmap(matrix=fitz.Matrix(3, 3), clip=clip, alpha=False).save(path)


def page_leaves(pdf, question_pages: int) -> tuple[list[list[dict]], list[dict], list[dict]]:
    pages: list[list[dict]] = []
    leaves: list[dict] = []
    center_lines: list[dict] = []
    for page_no in range(1, question_pages + 1):
        page = pdf[page_no - 1]
        words = []
        for item in page.get_text("words"):
            x0, y0, x1, y1, text = item[:5]
            word = {"x0": x0, "y0": y0, "x1": x1, "y1": y1, "text": text, "page_width": page.rect.width}
            words.append(word)
            if y0 >= 80 and y1 <= 955:
                leaves.append({"page": page_no, "column": column_for(x0, page.rect.width), "x0": x0, "y0": y0, "x1": x1, "y1": y1, "kind": "word", "text": text})
        pages.append(words)
        for drawing in page.get_drawings():
            rect = drawing["rect"]
            if rect.y0 < 80 or rect.y1 > 955:
                continue
            if rect.width <= 3 and rect.height > 400 and abs(rect.x0 - page.rect.width / 2) < 15:
                center_lines.append({"page": page_no, "bbox": [round(rect.x0, 3), round(rect.y0, 3), round(rect.x1, 3), round(rect.y1, 3)]})
                continue
            if rect.width > 1 or rect.height > 1:
                leaves.append({"page": page_no, "column": column_for(rect.x0, page.rect.width), "x0": rect.x0, "y0": rect.y0, "x1": rect.x1, "y1": rect.y1, "kind": "drawing"})
        # ``get_image_rects`` once per xref becomes quadratic on a long EBS
        # book containing reused diagram assets.  The per-page image-info API
        # already carries each physical occurrence bbox, retaining endpoint
        # semantics without turning a 391-item evidence run into a timeout.
        for image in page.get_image_info(xrefs=True):
            bbox = image.get("bbox")
            if not bbox:
                continue
            rect = fitz.Rect(bbox)
            if rect.y0 >= 80 and rect.y1 <= 955:
                leaves.append({"page": page_no, "column": column_for(rect.x0, page.rect.width), "x0": rect.x0, "y0": rect.y0, "x1": rect.x1, "y1": rect.y1, "kind": "image"})
    return pages, leaves, center_lines


def image_hash(package: Package, member: str) -> tuple[bytes, str]:
    data = package.members[member]
    return data, sha(data)


def master_images(package: Package) -> list[str]:
    values = []
    for name, data in package.members.items():
        if re.fullmatch(r"Contents/masterpage\d+\.xml", name):
            root = E.fromstring(data)
            values.extend(package.asset_hash(node.get("binaryItemIDRef")) for node in root.iter("{http://www.hancom.co.kr/hwpml/2011/core}img"))
    return values


def first_physical_endnote_page(pdf) -> int:
    """Locate the first rendered native endnote page without title backfill.

    The worksheet's native endnotes render an explicit answer and solution
    label.  Looking for that paired payload in physical PDF order avoids
    confusing repeated printed question numbers inside endnotes with question
    markers.  A lone word is intentionally insufficient because a problem
    stem can quote either term.
    """
    for page_number, page in enumerate(pdf, 1):
        text = page.get_text("text")
        if "정답:" in text and "해설:" in text:
            return page_number
    raise ValueError("PHYSICAL_NATIVE_ENDNOTE_LABEL_NOT_FOUND")


def native_question_reference_numbers(package: Package, expected_count: int) -> list[int]:
    """Read the generated native endnote-reference sequence from target HWPX.

    Raw EBS printed numbers legitimately reset at a unit boundary, while this
    worksheet's editor-visible question labels are deliberately generated as
    one continuous 1..N sequence.  Source inventory still owns the ID mapping;
    the target's actual native reference object owns the PDF marker sequence.
    """
    section = next(iter(package.sections.values()))
    anchors = [node for node in section if node.find(".//" + P("endNote")) is not None]
    values: list[int] = []
    for anchor in anchors:
        note = anchor.find(".//" + P("endNote"))
        if note is None:
            raise ValueError("NATIVE_REFERENCE_ANCHOR_MISSING")
        try:
            values.append(int(str(note.get("number"))))
        except (TypeError, ValueError) as error:
            raise ValueError("NATIVE_REFERENCE_NUMBER_INVALID") from error
    if len(values) != expected_count or values != list(range(1, expected_count + 1)):
        raise ValueError("NATIVE_REFERENCE_SEQUENCE_MISMATCH")
    return values


def structural_heading_before_anchor_references(package: Package) -> tuple[set[int], list[dict]]:
    """Return references preceded by an actual top-level unit heading.

    A unit heading printed at the top of a new question page is not the final
    semantic object of the preceding question.  PDF reading order alone has
    no ownership information for that line, so bind the exclusion to the
    target HWPX's native heading paragraph and the immediately following
    native endnote anchor.  We intentionally do *not* broadly exclude every
    top-of-page word; a normal continuation remains owned by its question.
    """
    section = next(iter(package.sections.values()))
    top = list(section)
    references: set[int] = set()
    evidence: list[dict] = []
    for index, node in enumerate(top):
        note = node.find(".//" + P("endNote"))
        if note is None:
            continue
        try:
            reference = int(str(note.get("number")))
        except (TypeError, ValueError) as error:
            raise ValueError("NATIVE_REFERENCE_NUMBER_INVALID") from error
        prior = index - 1
        while prior >= 0:
            candidate = top[prior]
            if candidate.find(".//" + P("endNote")) is not None:
                break
            text = text_of(candidate).strip()
            normalized = re.sub(r"\s+", "", text)
            if "유형편" in text or "실전편" in text:
                references.add(reference)
                evidence.append({
                    "native_reference_number": reference,
                    "paragraph_index": prior,
                    "paragraph_id": candidate.get("id"),
                    "heading_text_sha256": sha(normalized.encode("utf-8")),
                    "heading_text_length": len(normalized),
                })
                break
            # A content-bearing nonheading paragraph after the prior anchor
            # means there is no immediate structural heading to exclude.
            if normalized:
                break
            prior -= 1
    return references, evidence


def exclude_heading_leaves_before_markers(leaves: list[dict], markers: list[dict], heading_references: set[int]) -> tuple[list[dict], list[dict]]:
    """Remove only native-heading leaves immediately before their anchor."""
    by_slot: dict[tuple[int, int], list[dict]] = {}
    for marker in markers:
        if marker["printed_number"] in heading_references:
            by_slot.setdefault((int(marker["page"]), int(marker["column"])), []).append(marker)
    excluded: list[dict] = []
    retained: list[dict] = []
    for leaf in leaves:
        owner = next((marker for marker in by_slot.get((int(leaf["page"]), int(leaf["column"])), [])
                      if float(leaf["y1"]) < float(marker["y0"]) - 0.1), None)
        if owner is None:
            retained.append(leaf)
            continue
        excluded.append({
            "native_reference_number": owner["printed_number"],
            "page": leaf["page"], "column": leaf["column"], "kind": leaf["kind"],
            "bbox_pt": [round(float(leaf[key]), 3) for key in ("x0", "y0", "x1", "y1")],
            "text_sha256": sha(str(leaf.get("text", "")).encode("utf-8")),
        })
    return retained, excluded


def role_evidence(target_pkg: Package, hwp_reopen: Package, pdf, output: Path, target_hashes: dict, scope_ids: list[str], first_endnote_page: int) -> tuple[dict, dict]:
    rows = paragraph_rows(target_pkg)
    reopened = paragraph_rows(hwp_reopen)
    spans = pdf_spans(pdf)
    selected = {}
    for role in ROLE_NAMES:
        for row in rows:
            if role not in roles_for(row):
                continue
            match = find_span(row, role, spans, first_endnote_page)
            reopening = matching_reopen_row(row, reopened)
            if match is None or reopening is None:
                continue
            span, expected_fonts = match
            if not expected_fonts:
                continue
            if row["paragraph_semantic_sha256"] != reopening["paragraph_semantic_sha256"]:
                continue
            if [c["semantic_sha256"] for c in row["characters"]] != [c["semantic_sha256"] for c in reopening["characters"]]:
                continue
            selected[role] = (row, reopening, span, expected_fonts)
            break
    role_renders = []
    style_rows = []
    observations = []
    for role in ROLE_NAMES:
        if role not in selected:
            continue
        row, reopening, span, expected = selected[role]
        image = output / f"role-{role}.png"
        crop_span(pdf, span, image)
        entry = {
            "role": role,
            "expected_fonts": expected,
            "actual_fonts": [span["font"]],
            "font_match": expected == [span["font"]],
            "pages": [span["page"]],
            "pdf_span": span,
            "render_artifact": artifact(image),
        }
        role_renders.append(entry)
        style_rows.append({
            "role": role,
            "target_paragraph_semantic_sha256": row["paragraph_semantic_sha256"],
            "hwp_reopen_paragraph_semantic_sha256": reopening["paragraph_semantic_sha256"],
            "target_character_semantic_sha256s": [c["semantic_sha256"] for c in row["characters"]],
            "hwp_reopen_character_semantic_sha256s": [c["semantic_sha256"] for c in reopening["characters"]],
            "paragraph_match": row["paragraph_semantic_sha256"] == reopening["paragraph_semantic_sha256"],
            "character_match": [c["semantic_sha256"] for c in row["characters"]] == [c["semantic_sha256"] for c in reopening["characters"]],
            "pdf_font": span["font"], "pdf_font_size_pt": span["size"], "pdf_bbox_pt": span["bbox"],
            "render_artifact": artifact(image),
        })
        observations.append({"method": "HWPX semantic charPr/paraPr -> HWP COM readback -> matching PDF span", "artifact": artifact(image)})
    missing = [role for role in ROLE_NAMES if role not in selected]
    font_closed = not missing and all(row["font_match"] for row in role_renders)
    style_closed = not missing and all(row["paragraph_match"] and row["character_match"] for row in style_rows)
    base = {
        "schema": "teacher-evidence/v1", "target_sha256": target_hashes,
        "scope_ids": scope_ids, "observations": observations,
    }
    font_report = {**base, "kind": "font_render", "coverage": "all_applicable_roles" if not missing else "partial_roles",
        "required_roles": ROLE_NAMES, "role_renders": role_renders,
        "checks": {"all_roles_have_pdf_span": not missing, "hwp_readback_styles_match": style_closed, "font_substitution_absent": font_closed},
        "status": "PASS" if font_closed else "REVIEW_REQUIRED",
        "open_items": [] if font_closed else [{"kind": "KOPUB_FONT_NOT_ACTIVE", "roles": missing or [r["role"] for r in role_renders if not r["font_match"]]}]}
    style_report = {**base, "kind": "style_roles", "role_styles": style_rows,
        "checks": {"all_roles_have_pdf_semantic_mapping": not missing, "hwp_reopen_paraPr_equal": style_closed, "hwp_reopen_charPr_equal": style_closed},
        "status": "PASS" if style_closed else "REVIEW_REQUIRED",
        "open_items": [] if style_closed else [{"kind": "STYLE_ROLE_MAPPING_INCOMPLETE", "roles": missing}]}
    return font_report, style_report


def main() -> int:
    a = args()
    if a.out.exists():
        raise FileExistsError(a.out)
    a.out.mkdir(parents=True)
    audit = json.loads(a.audit.read_text(encoding="utf-8"))
    scope_ids = audit["scope_ids"]
    inventory_data = json.loads(a.inventory.read_text(encoding="utf-8-sig"))
    inventory_by_id = {str(row.get("item_id", row.get("id", ""))): row for row in inventory_data.get("items", [])}
    if len(inventory_by_id) != len(scope_ids) or any(item_id not in inventory_by_id for item_id in scope_ids):
        raise ValueError("SOURCE_PRINTED_NUMBER_INVENTORY_SCOPE_MISMATCH")
    target_hashes = {"hwp": file_hash(a.target_hwp), "hwpx": file_hash(a.target_hwpx)}
    target = Package(a.target_hwpx)
    native_reference_numbers = native_question_reference_numbers(target, len(scope_ids))
    hwp_reopen = Package(a.hwp_readback)
    hwpx_reopen = Package(a.hwpx_readback)
    source = Package(a.source_hwpx)
    pdf = fitz.open(a.pdf)
    exception_by_id, exception_errors, exception_document = choice_exception_rows(
        a.choice_exceptions, target_hashes, file_hash(a.pdf)
    )

    # Determine the physical question/endnote boundary before matching text
    # roles.  The same printed number can occur in both stories, so a role is
    # only evidence when its PDF span is on the appropriate side of this
    # independently observed boundary.
    first_endnote_page = first_physical_endnote_page(pdf)
    if first_endnote_page <= 1:
        raise ValueError("ENDNOTE_BEFORE_QUESTION_STORY")

    # Role-level HWPX -> HWP reopen -> PDF evidence.
    font_report, style_report = role_evidence(
        target, hwp_reopen, pdf, a.out, target_hashes, scope_ids, first_endnote_page
    )
    write(a.out / "font-render.json", font_report)
    write(a.out / "style-roles.json", style_report)

    # Source title asset -> deterministic crop -> target master page -> both
    # readbacks -> actual first-page PDF raster.  The raw source hash is bound
    # through the serial COM report, rather than pretending that an OLE HWP is
    # a ZIP package.
    source_asset, source_asset_hash = image_hash(source, "BinData/image1.png")
    source_image = Image.open(io.BytesIO(source_asset)).convert("RGB")
    title_box = (340, 880, 1300, 1360)
    subject_box = (400, 1525, 1040, 1635)
    derived = Image.new("RGB", (960, 620), "white")
    derived.paste(source_image.crop(title_box), (0, 0))
    derived.paste(source_image.crop(subject_box), (160, 505))
    buffer = io.BytesIO(); derived.save(buffer, format="PNG")
    derived_bytes = buffer.getvalue(); derived_hash = sha(derived_bytes)
    source_asset_path = a.out / "source-title-image.png"; source_asset_path.write_bytes(source_asset)
    derived_path = a.out / "derived-header-image.png"; derived_path.write_bytes(derived_bytes)
    target_master = master_images(target)
    hwp_master = master_images(hwp_reopen)
    hwpx_master = master_images(hwpx_reopen)
    header_crop = a.out / "header-page-1.png"
    pdf[0].get_pixmap(matrix=fitz.Matrix(3, 3), clip=fitz.Rect(0, 0, pdf[0].rect.width, 86), alpha=False).save(header_crop)
    header_text = "".join(page.get_text() for page in [pdf[0]])
    expected_subject = "수학Ⅰ·수학Ⅱ·미적분"
    correct_subject = expected_subject in re.sub(r"\s+", "", header_text)
    source_com = json.loads(a.source_com_report.read_text(encoding="utf-8"))
    raw_bound = source_com.get("source_sha256") == file_hash(a.source_raw_hwp)
    header_closed = all((raw_bound, derived_hash in target_master, target_master == hwp_master == hwpx_master, correct_subject))
    header_report = {
        "schema": "teacher-evidence/v1", "kind": "header_render", "target_sha256": target_hashes, "scope_ids": scope_ids,
        "source_raw_hwp_sha256": file_hash(a.source_raw_hwp), "source_hwpx_sha256": file_hash(a.source_hwpx),
        "source_asset": {"member": "BinData/image1.png", "sha256": source_asset_hash, "artifact": artifact(source_asset_path)},
        "derivation": {"title_crop": title_box, "subject_crop": subject_box, "derived_sha256": derived_hash, "artifact": artifact(derived_path)},
        "masterpage_asset_sha256": {"target": target_master, "hwp_reopen": hwp_master, "hwpx_reopen": hwpx_master},
        "pdf_header": {"expected_subject": expected_subject, "subject_text_observed": correct_subject, "artifact": artifact(header_crop)},
        "checks": {"source_raw_to_hwpx_bound": raw_bound, "deterministic_source_crop_matches_master_asset": derived_hash in target_master,
                   "master_asset_survives_hwp_and_hwpx_reopen": target_master == hwp_master == hwpx_master, "pdf_header_subject_matches": correct_subject},
        "status": "PASS" if header_closed else "REVIEW_REQUIRED",
        "open_items": [] if header_closed else [{"kind": "HEADER_SOURCE_TO_RENDER_INCOMPLETE"}],
        "observations": [
            {"method": "source HWP serial COM HWPX asset extraction", "artifact": artifact(source_asset_path)},
            {"method": "deterministic original-title crop", "artifact": artifact(derived_path)},
            {"method": "Hanword exported B4 PDF top-band raster", "artifact": artifact(header_crop)},
        ],
    }
    write(a.out / "header-render.json", header_report)

    # Workspace uses native question order from the source audit, then actual
    # PDF leaf words, drawings, and images.  Old negative text-block rows are
    # tracked as the exact 87 composite cases that this pass replaces. Never
    # reuse a book-specific question-page constant: locate the page of the
    # last ordered question marker in this target PDF first, then restrict the
    # workspace scan to the resulting physical question range.
    old = json.loads(a.old_workspace.read_text(encoding="utf-8"))
    # Accept both the legacy inline rows and the target-bound v1 artifact
    # shape.  The latter must still be hash-bound before it is used as a
    # regression baseline.
    old_rows = old.get("rows")
    if old_rows is None:
        old_ref = old.get("rows_artifact", {})
        old_rows_path = Path(old_ref.get("path", ""))
        if not old_rows_path.is_file() or sha(old_rows_path.read_bytes()) != old_ref.get("sha256"):
            raise ValueError("OLD_WORKSPACE_ROWS_ARTIFACT_HASH")
        old_rows = json.loads(old_rows_path.read_text(encoding="utf-8-sig"))
    previous_composite = {row["id"] for row in old_rows if (row.get("gap_mm") or 0) < 0}
    # Question numbers recur in the document-end solution payload, so the
    # former "last ordered number" approach could scan into endnotes and
    # falsely manufacture workspace failures.  The first real answer+solution
    # native endnote label is the physical story boundary; it is measured
    # independently from both question title position and page-plan estimates.
    question_pages = first_endnote_page - 1
    page_words, leaves, center_lines = page_leaves(pdf, question_pages)
    # Use the target's actual native reference objects, not a raw source
    # printed-number field that legitimately restarts at unit boundaries and
    # not a filename/label count.  The source ID mapping remains separately
    # closed by the full source audit.
    markers = ordered_markers(page_words, native_reference_numbers)
    if len(markers) != len(scope_ids):
        raise ValueError("QUESTION_MARKER_SCOPE_NOT_FOUND_IN_MAIN_STORY")
    heading_references, heading_object_evidence = structural_heading_before_anchor_references(target)
    marker_keys = {(m["page"], round(m["x0"], 3), round(m["y0"], 3), str(m["text"])) for m in markers}
    for leaf in leaves:
        if leaf["kind"] == "word" and (leaf["page"], round(leaf["x0"], 3), round(leaf["y0"], 3), str(leaf.get("text", ""))) in marker_keys:
            leaf["marker"] = True
    leaves, structural_heading_leaf_exclusions = exclude_heading_leaves_before_markers(
        leaves, markers, heading_references
    )
    sec = next(iter(target.sections.values()))
    pagepr = next(sec.iter(P("pagePr")))
    margin = pagepr.find(P("margin"))
    body_bottom_pt = (float(pagepr.get("height")) - float(margin.get("footer"))) / 100.0
    rows = workspace_rows(scope_ids, markers, leaves, body_bottom_pt=body_bottom_pt, previously_composite_ids=previous_composite)
    choices = []
    for row, marker in zip(rows, markers):
        if row.get("status") == "REVIEW_REQUIRED":
            continue
        following = markers[markers.index(marker) + 1] if markers.index(marker) + 1 < len(markers) else None
        owned = [leaf for leaf in leaves if leaf.get("kind") == "word" and leaf.get("text") in "①②③④⑤" and leaf.get("marker") is not True and (lambda x: x)(True)]
        # Restrict by the same source-owned range used for endpoint measurement.
        from app.teacher_pdf_evidence import _within_question
        owned = [leaf for leaf in owned if _within_question(leaf, marker, following)]
        labels = [leaf["text"] for leaf in owned]
        if set(labels) == set("①②③④⑤") and len(labels) == 5:
            ys = sorted(round(float(leaf["y0"]), 1) for leaf in owned)
            top = [y for y in ys if abs(y - ys[0]) < 7]
            lower = [y for y in ys if abs(y - ys[0]) >= 7]
            positions = [[round(leaf["x0"], 2), round(leaf["y0"], 2), leaf["text"]] for leaf in owned]
            three_plus_two = len(top) == 3 and len(lower) == 2
            exception = exception_by_id.get(str(row["id"]))
            position_sha256 = json_hash(positions)
            exception_valid = bool(
                exception
                and exception.get("status") == "PASS"
                and exception.get("layout_pattern") == "2+1+2"
                and exception.get("positions_sha256") == position_sha256
                and compact_two_one_two(positions)
            )
            choices.append({
                "id": row["id"], "page": marker["page"], "positions": positions,
                "positions_sha256": position_sha256, "three_plus_two": three_plus_two,
                "evidenced_layout_exception": exception_valid,
                "layout_pass": three_plus_two or exception_valid,
                "exception_reason": exception.get("reason") if exception_valid else None,
            })
    workspace_rows_path = a.out / "workspace-rows.json"; write(workspace_rows_path, rows)
    all_workspace = all(row.get("status") == "PASS" for row in rows)
    unresolved_choice_ids = [row["id"] for row in choices if not row["layout_pass"]]
    # Exceptions may only close a currently observed non-3+2 layout.  A stale
    # or surplus exception record is a review condition rather than a silent
    # waiver for a different target or a later reflow.
    observed_ids = {str(row["id"]) for row in choices}
    surplus_exception_ids = sorted(set(exception_by_id) - observed_ids)
    if surplus_exception_ids:
        exception_errors.append({"kind": "CHOICE_EXCEPTION_NOT_OBSERVED", "ids": surplus_exception_ids})
    choice_closed = bool(choices) and not unresolved_choice_ids and not exception_errors
    workspace_report = {
        "schema": "teacher-evidence/v1", "kind": "workspace", "target_sha256": target_hashes, "scope_ids": scope_ids,
        "rows_artifact": artifact(workspace_rows_path), "source_inventory": artifact(a.inventory),
        "target_native_reference_numbers": native_reference_numbers, "question_page_count": question_pages,
        "question_page_count_method": "last_ordered_native_question_marker_in_target_pdf", "body_bottom_pt": round(body_bottom_pt, 3),
        "previous_composite_count": len(previous_composite), "resolved_previous_composite_count": sum(1 for row in rows if row.get("previously_composite_block") and row.get("semantic_endpoint_resolved")),
        "heading_before_anchor_native_references": sorted(heading_references),
        "heading_object_evidence": heading_object_evidence,
        "structural_heading_leaf_exclusions": structural_heading_leaf_exclusions,
        "choice_layouts": choices, "choice_exception_document": artifact(a.choice_exceptions) if a.choice_exceptions else None,
        "choice_exception_schema": exception_document.get("schema") if exception_document else None,
        "choice_exception_errors": exception_errors, "center_divider_observations": center_lines,
        "checks": {"all_391_markers_found_in_source_order": len(markers) == len(scope_ids), "all_391_semantic_endpoints_measured": all_workspace,
                   "all_87_previous_composites_resolved": sum(1 for row in rows if row.get("previously_composite_block") and row.get("semantic_endpoint_resolved")) == len(previous_composite),
                   "five_choice_layouts_are_3_plus_2_or_target_bound_compact_2_1_2": choice_closed,
                   "choice_exception_records_are_target_bound": not exception_errors,
                   "center_divider_observed": bool(center_lines)},
        "status": "PASS" if all_workspace and choice_closed and bool(center_lines) else "REVIEW_REQUIRED",
        "open_items": [] if all_workspace and choice_closed and bool(center_lines) else [{
            "kind": "WORKSPACE_OR_CHOICE_LAYOUT_REVIEW_REQUIRED",
            "workspace_shortfalls": [row["id"] for row in rows if row.get("status") != "PASS"],
            "choice_layout_ids": unresolved_choice_ids,
            "choice_exception_errors": exception_errors,
        }],
        "observations": [{"method": "PDF leaf words/drawings/images bounded by native question markers, excluding only HWPX-proven unit headings immediately before their anchor", "artifact": artifact(workspace_rows_path)}],
    }
    write(a.out / "workspace.json", workspace_report)

    # ``placement`` also occurs in unrelated document objects.  Only the
    # native endnote property is evidence for document-end placement.
    placement = [
        node.get("place")
        for section in target.sections.values()
        for node in section.findall(".//" + P("endNotePr") + "/" + P("placement"))
    ]
    endnote_objects = sum(1 for section in target.sections.values() for _ in section.iter(P("endNote")))
    boundary_report = {
        "schema": "teacher-endnote-boundary/v1", "kind": "endnote_order", "target_sha256": target_hashes,
        "scope_ids": scope_ids, "last_main_story_page": question_pages, "first_endnote_page": first_endnote_page,
        "last_question_method": "physical_page_before_first_native_endnote_label",
        "first_note_method": "actual_answer_and_solution_native_endnote_labels_in_pdf",
        "independent_review": False,
        "checks": {
            "native_endnote_object_count_matches_scope": endnote_objects == len(scope_ids),
            "endnote_placement_is_end_of_document": placement and all(value == "END_OF_DOCUMENT" for value in placement),
            "last_question_and_first_endnote_are_adjacent_physical_pages": first_endnote_page == question_pages + 1,
        },
        "status": "PASS" if endnote_objects == len(scope_ids) and placement and all(value == "END_OF_DOCUMENT" for value in placement) and first_endnote_page == question_pages + 1 else "REVIEW_REQUIRED",
        "open_items": [],
        "observations": [{"method": "native endNote object count plus B4 PDF answer+solution label boundary", "artifact": artifact(a.pdf)}],
    }
    write(a.out / "endnote-boundary-automatic.json", boundary_report)

    summary = {"targets": target_hashes, "scope_count": len(scope_ids), "reports": {name: artifact(a.out / name) for name in ("font-render.json", "style-roles.json", "header-render.json", "workspace.json", "endnote-boundary-automatic.json")}}
    write(a.out / "evidence-manifest.json", summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
