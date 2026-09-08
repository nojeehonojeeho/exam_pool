"""Compare editable content across saved HWPX checkpoints.

Not a PDF/source-fidelity check. Equations, paragraphs and table cell order are
preserved; only blank paragraphs, automatic note numbering and layout metadata
are excluded. Picture hashes are resolved from the actual package resource.
"""
from __future__ import annotations

import hashlib
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from zipfile import ZipFile


def _tag(node):
    return node.tag.rsplit("}", 1)[-1]


def snapshot_node(node, *, binary_hashes=None):
    binary_hashes = binary_hashes or {}

    def content(element):
        tag = _tag(element)
        if tag in {"line", "rect", "ellipse", "arc", "polygon", "curve", "connectLine", "container", "textart", "ole", "video", "chart"}:
            raise ValueError(f"unsupported visible object in checkpoint: {tag}")
        if tag == "endNote":
            return []
        if tag == "equation":
            return [{"type": "equation", "script": (element.findtext(".//{*}script") or "").strip()}]
        if tag == "pic":
            images = element.findall(".//{*}img")
            refs = [image.get("binaryItemIDRef") for image in images]
            if not refs or any(ref not in binary_hashes for ref in refs):
                raise ValueError("picture resource could not be resolved")
            return [{"type": "picture", "sha256": [binary_hashes[ref] for ref in refs]}]
        if tag == "tbl":
            rows = []
            for row in element.findall("./{*}tr"):
                cells = []
                for cell in row.findall("./{*}tc"):
                    span = cell.find("./{*}cellSpan")
                    cells.append({"content": content(cell), "span": dict(span.attrib) if span is not None else {}})
                rows.append(cells)
            return [{"type": "table", "rows": rows}]
        if tag == "t":
            # Child tab/line-break controls are not silently discarded.
            text = element.text or ""
            for child in element:
                text += {"tab": "\t", "lineBreak": "\n", "nbSpace": "\u00a0"}.get(_tag(child), "<CONTROL:" + _tag(child) + ">")
                text += child.tail or ""
            return [{"type": "text", "text": text}] if text else []
        if tag in {"run", "p", "sec", "subList", "tc", "ctrl"}:
            values = []
            for child in element:
                for value in content(child):
                    if values and value["type"] == "text" and values[-1]["type"] == "text":
                        values[-1]["text"] += value["text"]
                    else:
                        values.append(value)
            if tag == "p":
                # Note auto-number leaves a leading space in the first run.
                if values and values[0]["type"] == "text":
                    values[0]["text"] = values[0]["text"].lstrip()
                if values and values[-1]["type"] == "text":
                    values[-1]["text"] = values[-1]["text"].rstrip()
                values = [value for value in values if value != {"type": "text", "text": ""}]
                return [{"type": "paragraph", "content": values}] if values else []
            return values
        return []

    if _tag(node) == "endNote":
        node = node.find("./{*}subList")
        if node is None:
            raise ValueError("endnote has no native body")
    return content(node)


def read_hwpx_snapshot(path):
    path = Path(path)
    with ZipFile(path) as package:
        bad = package.testzip()
        if bad:
            raise ValueError(f"corrupt ZIP member: {bad}")
        hashes = {}
        if "Contents/content.hpf" in package.namelist():
            index = ET.fromstring(package.read("Contents/content.hpf"))
            for entry in index.findall(".//{*}item"):
                href = entry.get("href", "").replace("\\", "/")
                candidates = (href, "Contents/" + href, href.removeprefix("../"))
                member = next((candidate for candidate in candidates if candidate in package.namelist()), None)
                if member and "BinData/" in member:
                    hashes[entry.get("id")] = hashlib.sha256(package.read(member)).hexdigest()
        sections = sorted((name for name in package.namelist() if re.fullmatch(r"Contents/section\d+\.xml", name)),
                          key=lambda name: int(re.search(r"\d+", name).group()))
        if not sections:
            raise ValueError("HWPX has no section XML")
        body, notes = [], []
        for name in sections:
            root = ET.fromstring(package.read(name))
            body.extend(snapshot_node(root, binary_hashes=hashes))
            for note in root.findall(".//{*}endNote"):
                notes.append({"number": note.get("number"), "content": snapshot_node(note, binary_hashes=hashes)})
        return {"file_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "check_scope": "native_checkpoint_content_not_pdf_fidelity",
                "body": body, "endnotes": notes}
