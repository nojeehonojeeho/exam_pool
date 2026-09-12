"""Apply a page/column break to a matching HWPX paragraph.

The source package is never overwritten.  A break is applied only to a
paragraph whose visible text contains the supplied anchor, allowing an
overflowing question/options block to start together on the next page.  This
is a layout-only operation: equation scripts, table cells, pictures, and
native endnote relationships are copied unchanged.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile
import xml.etree.ElementTree as ET


def _paragraph_text(paragraph: ET.Element) -> str:
    return "".join(node.text or "" for node in paragraph.findall(".//{*}t"))


def patch_paragraph_break(
    input_path: Path,
    output_path: Path,
    *,
    anchor: str,
    page_break: bool = True,
    column_break: bool = False,
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
    if occurrence < 1:
        raise ValueError("occurrence must be >= 1")

    records: list[dict[str, Any]] = []
    matched = 0
    with ZipFile(input_path) as source, ZipFile(output_path, "w", ZIP_DEFLATED) as target:
        for info in source.infolist():
            payload = source.read(info.filename)
            if info.filename.startswith("Contents/section") and info.filename.endswith(".xml"):
                root = ET.fromstring(payload)
                for paragraph in root.findall(".//{*}p"):
                    text = _paragraph_text(paragraph)
                    if anchor not in text:
                        continue
                    matched += 1
                    if matched != occurrence:
                        continue
                    before = {
                        "pageBreak": paragraph.attrib.get("pageBreak", "0"),
                        "columnBreak": paragraph.attrib.get("columnBreak", "0"),
                    }
                    if page_break:
                        paragraph.set("pageBreak", "1")
                    if column_break:
                        paragraph.set("columnBreak", "1")
                    after = {
                        "pageBreak": paragraph.attrib.get("pageBreak", "0"),
                        "columnBreak": paragraph.attrib.get("columnBreak", "0"),
                    }
                    records.append(
                        {
                            "section": info.filename,
                            "occurrence": occurrence,
                            "anchor": anchor,
                            "text": text,
                            "before": before,
                            "after": after,
                        }
                    )
                if any(record["section"] == info.filename for record in records):
                    ET.register_namespace("hp", "http://www.hancom.co.kr/hwpml/2011/paragraph")
                    ET.register_namespace("hs", "http://www.hancom.co.kr/hwpml/2011/section")
                    payload = ET.tostring(root, encoding="utf-8", xml_declaration=True)
            target.writestr(info, payload)
    if not records:
        # Do not leave a misleading partial package when the requested anchor
        # was not found; the source remains untouched and the derived target
        # fails closed.
        if output_path.exists():
            output_path.unlink()
        raise ValueError(f"anchor occurrence not found: {anchor!r} (matches={matched})")
    return {
        "status": "PASS",
        "schema": "hwp-paragraph-break-patch-v1",
        "input": str(input_path),
        "output": str(output_path),
        "anchor": anchor,
        "occurrence": occurrence,
        "match_count": matched,
        "records": records,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--anchor", required=True)
    parser.add_argument("--occurrence", type=int, default=1)
    parser.add_argument("--no-page-break", action="store_true")
    parser.add_argument("--column-break", action="store_true")
    args = parser.parse_args()
    report = patch_paragraph_break(
        args.input,
        args.output,
        anchor=args.anchor,
        page_break=not args.no_page_break,
        column_break=args.column_break,
        occurrence=args.occurrence,
    )
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
