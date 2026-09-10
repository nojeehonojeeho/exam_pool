"""Inspect the exact ordered blocks a writer will consume, not QA labels.

This boundary rejects known lossy authoring paths. Its PASS is a syntax and
input-integrity result only; source fidelity, HWP reopen, and page review are
separate release requirements. No source or copyrighted assets are bundled.
"""

from __future__ import annotations

import hashlib
from collections import Counter
from pathlib import Path
import re
from typing import Any, Iterator

from .hwp_equation_compiler import EquationCompileError, compile_equation
from .pdf_hwp_source_fidelity_v2 import normalize_content_blocks


EQUATION_KINDS = {"equation", "inline_equation", "display_equation"}
FORBIDDEN_FIGURE_SUBSTITUTES = {"figure_reference", "diagram", "figure_bundle", "figure_axis_labels", "figure_region_without_standalone_figure"}
PURE_FIGURE_ROLES = {"pure_graph", "pure_geometry", "pure_illustration", "pure_adjacency_illustration"}
_TEXT_MATH = re.compile(r"\\[A-Za-z]+|[\^_]|\b(?:sqrt|over|cases|matrix)\b|(?:[A-Za-z][0-9]?\s*[=<>≤≥]|[∑∫√])")
# OCR/tokenizers sometimes split a LaTeX operator into separate letters
# (``s q r t``/``p i``/``l i m``).  The equation compiler quite correctly
# treats those as ordinary atoms, so syntax compilation alone cannot catch the
# semantic loss.  Keep this list deliberately narrow: it only rejects a
# complete known operator made solely of whitespace-separated letters.
_SPLIT_LATEX_OPERATOR = re.compile(
    r"(?<![A-Za-z])(?:s\s+q\s+r\s+t|p\s+i|l\s+i\s+m|s\s+u\s+m|p\s+r\s+o\s+d|"
    r"i\s+n\s+t|s\s+i\s+n|c\s+o\s+s|t\s+a\s+n|c\s+o\s+t|f\s+r\s+a\s+c|"
    r"d\s+f\s+r\s+a\s+c)(?![A-Za-z])",
    re.IGNORECASE,
)


def _formula_control_characters(value: str) -> list[str]:
    """Return literal control characters that cannot be part of a formula source.

    Python string literals such as ``"\\alpha"`` turn ``\\a`` into BEL unless
    they are raw strings.  Hanword can silently drop that character during a
    round trip, producing an altered formula even though the remaining script
    appears syntactically valid.  Formula source is intentionally one-line,
    so every C0/C1 control character is a hard input error.
    """
    return [f"U+{ord(char):04X}" for char in value if ord(char) < 32 or 0x7F <= ord(char) <= 0x9F]


def walk(value: Any, path: str = "") -> Iterator[tuple[str, dict[str, Any]]]:
    if isinstance(value, dict):
        yield path, value
        for key, child in value.items():
            yield from walk(child, path + "/" + str(key))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from walk(child, path + "/" + str(index))


def piecewise_latex_source(block):
    """Construct exactly one native cases input shared by preflight and writer."""
    if block.get("script_language") != "latex" or not isinstance(block.get("cases"), list) or not block["cases"]:
        raise ValueError("piecewise function requires explicit latex cases")
    if block.get("script") or block.get("segments"):
        raise ValueError("ambiguous piecewise payload")
    name = block.get("name", "f(x)")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("piecewise function name must be a nonempty source string")
    rows = []
    for case in block["cases"]:
        if not isinstance(case, dict):
            raise ValueError("piecewise case must be an object")
        values = [case.get(key) for key in ("expression", "condition")]
        if any(not isinstance(value, str) or not value.strip() for value in values):
            raise ValueError("piecewise expression and condition must be source strings")
        rows.append(" & ".join(values))
    return name + "=" + r"\begin{cases}" + r"\\".join(rows) + r"\end{cases}"


def audit_authoring_items(items: list[dict[str, Any]], *, asset_root: str | Path) -> dict[str, Any]:
    findings, equations = [], []
    root = Path(asset_root)
    if not items:
        findings.append({"code": "ITEM_SET_EMPTY"})
    ids = [item.get("item_id") for item in items]
    if any(not isinstance(item_id, str) or not item_id.strip() for item_id in ids):
        findings.append({"code": "ITEM_ID_MISSING"})
    if any(count > 1 for count in Counter(str(item_id) for item_id in ids).values()):
        findings.append({"code": "ITEM_ID_DUPLICATE"})
    for item in items:
        item_id = item.get("item_id")
        for role in ("problem_blocks", "solution_blocks"):
            if not isinstance(item.get(role), list) or not item[role]:
                findings.append({"item_id": item_id, "code": "AUTHORING_BODY_MISSING", "path": role})
            else:
                # The writer consumes semantic blocks, not the legacy wrapper
                # itself.  Expand the four historical nested text fields at
                # the same boundary and reject unknown keys before any HWP
                # operation can silently ignore them.
                _, ledger, contract_findings = normalize_content_blocks(
                    item[role], path=f"/{role}",
                )
                for contract in contract_findings:
                    findings.append({
                        "item_id": item_id,
                        "code": contract.get("code", "AUTHORING_CONTENT_SCHEMA_INVALID"),
                        "path": contract.get("path", f"/{role}"),
                        **{key: value for key, value in contract.items() if key not in {"code", "path"}},
                    })
                if not ledger.entries:
                    findings.append({
                        "item_id": item_id,
                        "code": "AUTHORING_CONTENT_SCHEMA_INVALID",
                        "path": f"/{role}",
                        "detail": "writer input must contain at least one typed block",
                    })
            for path, block in walk(item.get(role, []), role):
                kind = block.get("type", "")
                context = {"item_id": item_id, "path": path}
                if 'align' in block and block['align'] not in ('Left', 'Center', 'Right', 'Justify', 'Distribute', 'DistributeSpace'):
                    findings.append({**context, 'code': 'AUTHORING_ALIGN_INVALID', 'detail': 'Use a canonical, case-sensitive native HAlign value.'})
                if kind in EQUATION_KINDS and block.get("segments") is not None and (block.get("script") or block.get("source")):
                    findings.append({**context, "code": "AUTHORING_AMBIGUOUS_CONTENT"})
                if kind in EQUATION_KINDS and "segments" not in block:
                    try:
                        # Strict checkpoint manifests may retain the original
                        # formula source under source_script.  Prefer the
                        # writer-facing script/source fields, but do not
                        # mistake source-aware metadata for an empty formula.
                        source = block.get("script") or block.get("source") or block.get("source_script") or ""
                        if not isinstance(source, str):
                            raise ValueError("formula source must be a string")
                        controls = _formula_control_characters(source)
                        if controls:
                            findings.append({**context, "code": "FORMULA_CONTROL_CHARACTER", "detail": controls})
                            continue
                        split_operator = _SPLIT_LATEX_OPERATOR.search(source)
                        if split_operator:
                            findings.append({
                                **context,
                                "code": "FORMULA_OPERATOR_TOKENIZATION",
                                "detail": split_operator.group(0),
                            })
                            continue
                        result = compile_equation(source, dialect=block.get("script_language", ""), operator_policies=block.get("operator_policies"))
                        # Preserve source-review provenance carried by the
                        # manifest block; compiler defaults must not overwrite
                        # source_pdf_verified/MathIR/evidence fields.
                        equations.append({**result.to_dict(), **context, **{
                            key: block[key]
                            for key in ("formula_occurrence_id", "source_pdf_verified", "mathir", "source_evidence", "source_text_sha256")
                            if key in block
                        }})
                    except (EquationCompileError, ValueError, TypeError) as exc:
                        findings.append({**context, "code": getattr(exc, "code", "FORMULA_INPUT_INVALID"), "detail": str(exc)})
                if kind in {"text", "answer", "solution_heading", "step_heading"}:
                    # Do not split or "repair" prose here. Review exact spans.
                    text = str(block.get("text", ""))
                    if text and (block.get("segments") is not None or block.get("components") is not None):
                        findings.append({**context, "code": "AUTHORING_AMBIGUOUS_CONTENT"})
                    if _TEXT_MATH.search(text):
                        findings.append({**context, "code": "FORMULA_MARKUP_IN_TEXT", "detail": text})
                    if "\n" in text or "\r" in text:
                        findings.append({**context, "code": "NATIVE_PARAGRAPH_REQUIRED", "detail": "Use ordered semantic paragraphs, not embedded OCR line breaks."})
                    ignored = sorted(set(block) & {
                        "condition_box", "question", "table", "choices", "rows", "cells",
                        "cases", "elements", "script",
                    })
                    if ignored:
                        findings.append({**context, "code": "AUTHORING_UNCONSUMED_CONTENT", "fields": ignored})
                    if "figure" in str(block.get("role", "")) or text.startswith(("그림:", "〔도식", "〔도형")):
                        findings.append({**context, "code": "FIGURE_DESCRIPTION_REPLACEMENT", "detail": "Figure data hidden in a text block is not a drawn figure."})
                if kind == "condition_box":
                    # The native writer consumes semantic rows, or a component
                    # wrapper. A table-style cells field is never consumed.
                    if "cells" in block:
                        findings.append({**context, "code": "AUTHORING_UNCONSUMED_CONTENT", "fields": ["cells"]})
                    rows, components = block.get("rows"), block.get("components")
                    if rows and components:
                        findings.append({**context, "code": "AUTHORING_AMBIGUOUS_CONTENT"})
                    if not ((isinstance(rows, list) and rows) or (isinstance(components, list) and components)):
                        findings.append({**context, "code": "CONDITION_BOX_CONTENT_REQUIRED"})
                    if rows is not None and not isinstance(rows, list):
                        findings.append({**context, "code": "CONDITION_BOX_ROWS_INVALID"})
                    if components is not None and not isinstance(components, list):
                        findings.append({**context, "code": "CONDITION_BOX_COMPONENTS_INVALID"})
                if kind in {"choices", "table", "condition_box"}:
                    def check_scalar(value, at):
                        if isinstance(value, list):
                            for index, child in enumerate(value):
                                check_scalar(child, f"{at}/{index}")
                        elif isinstance(value, str) and (_TEXT_MATH.search(value) or re.fullmatch(r"\s*[①②③④⑤]?\s*[+-]?\d+(?:[./]\d+)?\s*", value)):
                            findings.append({**context, "path": at, "code": "FORMULA_UNTYPED_CELL", "detail": value})
                    for field in ("cells", "rows"):
                        check_scalar(block.get(field, []), path + "/" + field)
                if kind in FORBIDDEN_FIGURE_SUBSTITUTES or (kind == "figure" and block.get("representation") in {"native_semantic", "semantic_description"}):
                    findings.append({**context, "code": "FIGURE_DESCRIPTION_REPLACEMENT", "detail": "Original diagrams cannot be substituted by prose or a semantic description table."})
                elif kind == "figure":
                    placement = block.get("placement", "block")
                    in_segments = "/segments/" in path
                    if placement not in {"block", "inline"} or (placement == "inline") != in_segments:
                        findings.append({**context, "code": "FIGURE_PLACEMENT_CONTEXT_MISMATCH"})
                    asset = root / str(block.get("path", ""))
                    if block.get("allowed") is not True or block.get("reason") not in PURE_FIGURE_ROLES:
                        findings.append({**context, "code": "FIGURE_NOT_APPROVED"})
                    if not asset.is_file():
                        findings.append({**context, "code": "FIGURE_ASSET_MISSING"})
                    elif not block.get("sha256") or hashlib.sha256(asset.read_bytes()).hexdigest().lower() != str(block["sha256"]).lower():
                        findings.append({**context, "code": "FIGURE_ASSET_HASH_MISMATCH"})
                if kind == "piecewise_function":
                    try:
                        script = piecewise_latex_source(block)
                        result = compile_equation(script, dialect="latex", operator_policies=block.get("operator_policies"))
                        equations.append({**result.to_dict(), **context, **{
                            key: block[key]
                            for key in ("formula_occurrence_id", "source_pdf_verified", "mathir", "source_evidence", "source_text_sha256")
                            if key in block
                        }})
                    except (EquationCompileError, ValueError, TypeError) as exc:
                        findings.append({**context, "code": "PIECEWISE_NATIVE_REQUIRED", "detail": str(exc)})
        completeness = item.get("solution_completeness", {})
        blocks = item.get("solution_blocks", [])
        for count_key in ("source_block_count", "included_block_count", "reconstructed_block_count"):
            if count_key in completeness and completeness[count_key] != len(blocks):
                findings.append({"item_id": item_id, "code": "SOLUTION_DECLARED_COUNT_MISMATCH", "field": count_key, "declared": completeness[count_key], "actual": len(blocks)})
    return {"status": "FAIL" if findings else "PASS", "check_scope": "authoring_syntax_and_asset_integrity_only", "source_fidelity_proven": False,
            "counts": {"items": len(items), "equations": len(equations), "findings": len(findings)}, "findings": findings, "equations": equations}
