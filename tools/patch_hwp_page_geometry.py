"""Apply an explicit page-margin safety boundary to a fresh HWPX package.

This is a layout-only transformation.  It is used after the source-page
geometry has been measured and before the serial HWP save/readback gate.  The
input package is never modified and all XML content, equation scripts, table
cells, pictures, and native notes are copied byte-for-byte except for the
requested ``pagePr/margin`` attributes.
"""
from __future__ import annotations

import argparse
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile
import xml.etree.ElementTree as ET
import json
from typing import Any


def patch_page_margins(
    input_path: Path,
    output_path: Path,
    *,
    bottom: int | None = None,
    top: int | None = None,
    left: int | None = None,
    right: int | None = None,
) -> dict[str, Any]:
    input_path = input_path.resolve()
    output_path = output_path.resolve()
    if input_path == output_path:
        raise ValueError("output must be a fresh path")
    if output_path.exists():
        raise FileExistsError(output_path)
    requested = {"bottom": bottom, "top": top, "left": left, "right": right}
    if all(value is None for value in requested.values()):
        raise ValueError("at least one margin must be supplied")
    records: list[dict[str, Any]] = []
    with ZipFile(input_path) as source, ZipFile(output_path, "w", ZIP_DEFLATED) as target:
        for info in source.infolist():
            payload = source.read(info.filename)
            if info.filename.startswith("Contents/section") and info.filename.endswith(".xml"):
                root = ET.fromstring(payload)
                for page in root.findall(".//{*}pagePr"):
                    margin = page.find("./{*}margin")
                    if margin is None:
                        continue
                    before = dict(margin.attrib)
                    for key, value in requested.items():
                        if value is not None:
                            if value < 0:
                                raise ValueError(f"negative {key} margin")
                            margin.set(key, str(value))
                    records.append({"section": info.filename, "before": before, "after": dict(margin.attrib)})
                if records and records[-1]["section"] == info.filename:
                    ET.register_namespace("hp", "http://www.hancom.co.kr/hwpml/2011/paragraph")
                    ET.register_namespace("hs", "http://www.hancom.co.kr/hwpml/2011/section")
                    payload = ET.tostring(root, encoding="utf-8", xml_declaration=True)
            target.writestr(info, payload)
    return {"status": "PASS", "schema": "hwp-page-geometry-patch-v1", "input": str(input_path), "output": str(output_path), "requested": requested, "records": records}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--bottom", type=int)
    parser.add_argument("--top", type=int)
    parser.add_argument("--left", type=int)
    parser.add_argument("--right", type=int)
    args = parser.parse_args()
    print(json.dumps(patch_page_margins(args.input, args.output, bottom=args.bottom, top=args.top, left=args.left, right=args.right), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
