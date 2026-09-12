"""Wrap oversized native equation scripts without changing math tokens.

HWP equations do not automatically line-wrap.  A paragraph that contains one
very long, semicolon-separated derivation can therefore paint outside its
own table cell or page even though the HWPX package is valid.  This tool adds
the HWP equation line-break operator (``#``) only after safe visible
separators and writes a new package.  It never changes text, operators,
numbers, or endnote relationships.

The transformation is deliberately conservative: equations with a cached
width at or below the configured content width are untouched, and a script is
changed only when it has a separator at which a line can be broken.  The
writer's cached width is capped after wrapping; Hanword recomputes the final
geometry during the required serial open/save round trip.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
from pathlib import Path
import re
import sys
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile
import xml.etree.ElementTree as ET


@dataclass(frozen=True)
class WrapRecord:
    section: str
    equation_id: str
    before_width: int
    after_width: int
    before_script_sha256: str
    after_script_sha256: str
    inserted_breaks: int


_SAFE_SEPARATORS = (";", " -> ", "→", ",", "=", "+")


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _wrap_at_separators(script: str, *, line_chars: int) -> tuple[str, int]:
    """Insert ``#`` after separators when the current visual line is long.

    The separator remains in the script, so the visible mathematical token
    stream is unchanged.  Existing ``#`` breaks are preserved and repeated
    application is idempotent.
    """
    if "#" in script:
        # Keep cases and previously wrapped formulas exactly as authored.
        return script, 0
    if len(script) <= line_chars:
        return script, 0
    # Assignment/arithmetic separators are included after the higher-level
    # statement separators.  They are retained verbatim and only receive a
    # line-break operator after the current visual line reaches the bound.
    # Do not split the ``=`` inside comparison operators (``<=``, ``>=`` or
    # ``!=``), and do not split unary/binary minus: those are mathematical
    # tokens rather than statement boundaries.  A standalone equality is a
    # safe visual break for a long chain of derived equalities.
    parts = re.split(r"(;| -> |→|,|(?<![<>!])=(?!=)|\+)", script)
    output: list[str] = []
    current = ""
    breaks = 0
    for part in parts:
        candidate = current + part
        if current and len(candidate) > line_chars and part in _SAFE_SEPARATORS:
            output.append(current.rstrip())
            output.append(part.strip())
            output.append(" # ")
            current = ""
            breaks += 1
        else:
            current = candidate
    output.append(current)
    wrapped = "".join(output).strip()
    return wrapped, breaks


def _patch_section_xml(payload: bytes, *, max_width: int, line_chars: int) -> tuple[bytes, list[WrapRecord]]:
    root = ET.fromstring(payload)
    records: list[WrapRecord] = []
    for equation in root.findall(".//{*}equation"):
        size = equation.find("./{*}sz")
        script_node = equation.find("./{*}script")
        if size is None or script_node is None or not (script_node.text or "").strip():
            continue
        try:
            width = int(size.attrib.get("width", "0"))
        except (TypeError, ValueError):
            continue
        if width <= max_width:
            continue
        before = script_node.text or ""
        after, inserted = _wrap_at_separators(before, line_chars=line_chars)
        if not inserted:
            continue
        script_node.text = after
        size.set("width", str(max_width))
        records.append(
            WrapRecord(
                section="",
                equation_id=equation.attrib.get("id", ""),
                before_width=width,
                after_width=max_width,
                before_script_sha256=_sha256_text(before),
                after_script_sha256=_sha256_text(after),
                inserted_breaks=inserted,
            )
        )
    if not records:
        return payload, records
    ET.register_namespace("hp", "http://www.hancom.co.kr/hwpml/2011/paragraph")
    ET.register_namespace("hs", "http://www.hancom.co.kr/hwpml/2011/section")
    return ET.tostring(root, encoding="utf-8", xml_declaration=True), records


def transform(input_path: Path, output_path: Path, *, max_width: int = 49918, line_chars: int = 96) -> dict[str, Any]:
    input_path = input_path.resolve()
    output_path = output_path.resolve()
    if input_path == output_path:
        raise ValueError("output must be a fresh path")
    if output_path.exists():
        raise FileExistsError(output_path)
    records: list[dict[str, Any]] = []
    with ZipFile(input_path) as source, ZipFile(output_path, "w", ZIP_DEFLATED) as target:
        for info in source.infolist():
            payload = source.read(info.filename)
            if info.filename.startswith("Contents/section") and info.filename.endswith(".xml"):
                payload, section_records = _patch_section_xml(
                    payload, max_width=max_width, line_chars=line_chars
                )
                for record in section_records:
                    records.append({"section": info.filename, **record.__dict__})
            target.writestr(info, payload)
    return {
        "status": "PASS",
        "schema": "hwp-equation-wrap-v1",
        "input": str(input_path),
        "output": str(output_path),
        "max_width": max_width,
        "line_chars": line_chars,
        "records": records,
        "wrapped_equation_count": len(records),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--max-width", type=int, default=49918)
    parser.add_argument("--line-chars", type=int, default=96)
    args = parser.parse_args()
    report = transform(args.input, args.output, max_width=args.max_width, line_chars=args.line_chars)
    print(__import__("json").dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
