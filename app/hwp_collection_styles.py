"""Read-only resolved style comparison for continuous native HWPX bodies.

Does not import pyhwpx/COM or alter a global COM type-library cache. Numeric
definition IDs are document-local; compare the resolved definitions instead.
"""
from __future__ import annotations
import hashlib
import json
import re
import zipfile
from xml.etree import ElementTree as ET

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"


def resolved_body_style_signatures(path, resolved: bool = False) -> list[dict]:
    local = lambda element: element.tag.rsplit("}", 1)[-1]
    with zipfile.ZipFile(path) as archive:
        header = ET.fromstring(archive.read("Contents/header.xml"))
        names = sorted([name for name in archive.namelist()
                        if re.fullmatch(r"Contents/section\d+\.xml", name)],
                       key=lambda name: int(re.search(r"(\d+)\.xml", name).group(1)))
        sections = [ET.fromstring(archive.read(name)) for name in names]
    kinds = ["charPr", "paraPr", "borderFill", "tabPr"]
    definitions = {kind: {e.get("id"): e for e in header.iter() if local(e) == kind}
                   for kind in kinds}
    faces = {e.get("lang"): {x.get("id"): x.get("face") for x in e if local(x) == "font"}
             for e in header.iter() if local(e) == "fontface"}

    def normalized(element):
        attrs = {key: value for key, value in element.attrib.items() if key != "id"}
        if local(element) == "fontRef":
            attrs = {key: faces[key.upper()][value] for key, value in attrs.items()}
        for attr, kind in [("borderFillIDRef", "borderFill"), ("tabPrIDRef", "tabPr")]:
            if attr in attrs:
                attrs[attr] = normalized(definitions[kind][attrs[attr]])
        return [local(element), sorted(attrs.items()),
                element.text.strip() if element.text and element.text.strip() else "",
                [normalized(child) for child in element]]

    def digest(value):
        return value if resolved else hashlib.sha256(json.dumps(
            value, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()

    chars = {key: digest(normalized(e)) for key, e in definitions["charPr"].items()}
    paras = {key: digest(normalized(e)) for key, e in definitions["paraPr"].items()}
    result = []
    for section in sections:
        for paragraph in section.findall(HP + "p"):
            runs = []
            for run in paragraph.findall(HP + "run"):
                if any(local(child) in ["t", "equation", "pic"] and
                       (local(child) != "t" or (child.text or "")) for child in run):
                    signature = chars[run.get("charPrIDRef")]
                    if not runs or runs[-1] != signature:
                        runs.append(signature)
            if runs:
                result.append({"paragraph": paras[paragraph.get("paraPrIDRef")], "runs": runs})
    return result
