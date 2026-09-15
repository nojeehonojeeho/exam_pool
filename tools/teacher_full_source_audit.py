"""Audit every source-owned item against a rebuilt HWP/HWPX release.

This is deliberately separate from layout/COM evidence.  It confirms that the
source-stage problem/answer/solution payload for every selected ID survived
the native reflow, including sanctioned, hash-bound next-section metadata
exclusions.  It does not infer visual, font, clipboard, or FINAL success.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.teacher_workflow import NS, P, Package, digest, file_hash, payload, write_json


def text_series(events: list[list[object]]) -> str:
    return "".join(str(value or "") for kind, value in events if kind == "text")


def series(events: list[list[object]], kind: str) -> list[object]:
    return [value for event_kind, value in events if event_kind == kind]


def blocks(package: Package) -> list[dict[str, object]]:
    section = next(iter(package.sections.values()))
    top = list(section)
    starts = [i for i, node in enumerate(top) if node.find(".//" + P("endNote")) is not None]
    result: list[dict[str, object]] = []
    for ordinal, start in enumerate(starts):
        end = starts[ordinal + 1] if ordinal + 1 < len(starts) else len(top)
        while end > start + 1:
            candidate = top[end - 1]
            text = "".join(candidate.xpath("./p:run/p:t/text()", namespaces=NS))
            if payload(package, [candidate]) == [["paragraph_end", None]] or " · 유형편 · " in text or " · 실전편 · " in text:
                end -= 1
            else:
                break
        anchor = top[start].find(".//" + P("endNote"))
        assert anchor is not None
        result.append({"body": payload(package, top[start:end]), "note": payload(package, list(anchor), omit_notes=False)})
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--build-report", type=Path, required=True)
    parser.add_argument("--source-stage", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--target-hwp", type=Path, required=True)
    parser.add_argument("--target-hwpx", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        raise FileExistsError(args.out)
    config = json.loads(args.config.read_text(encoding="utf-8-sig"))
    build = json.loads(args.build_report.read_text(encoding="utf-8-sig"))
    inventory = json.loads(args.inventory.read_text(encoding="utf-8-sig"))
    selected = list(map(str, config["selected_item_ids"]))
    expected = build["expected"]
    target = Package(args.target_hwpx)
    actual = blocks(target)
    source = Package(args.source_stage)
    source_top = list(next(iter(source.sections.values())))
    by_id = {str(row["item_id"]): row for row in inventory["items"]}
    exclusions = {str(row["item_id"]): row for row in config.get("note_exclusions", [])}
    roundtrip_rows: list[dict] = []
    source_rows: list[dict] = []
    mismatches: list[str] = []
    missing: list[str] = []
    for ordinal, item_id in enumerate(selected, 1):
        got = actual[ordinal - 1] if ordinal <= len(actual) else {"body": [], "note": []}
        want = expected[ordinal - 1] if ordinal <= len(expected) else {"body": [], "note": []}
        roundtrip = {"id": item_id, "ordinal": ordinal}
        for role in ("body", "note"):
            roundtrip[role + "_payload_equal"] = want[role] == got[role]
            roundtrip[role + "_text_equal"] = text_series(want[role]) == text_series(got[role])
            roundtrip[role + "_equation_equal"] = series(want[role], "equation") == series(got[role], "equation")
            roundtrip[role + "_image_equal"] = series(want[role], "image") == series(got[role], "image")
        if not all(value for key, value in roundtrip.items() if key not in {"id", "ordinal"}):
            mismatches.append(item_id)
        roundtrip_rows.append(roundtrip)
        inv = by_id.get(item_id)
        row: dict[str, object] = {"id": item_id, "ordinal": inv.get("ordinal") if inv else None}
        if inv is None:
            row["status"] = "MISSING_IN_INVENTORY"
            missing.append(item_id)
            source_rows.append(row)
            continue
        for role, source_roles in (("body", ["problem"]), ("note", ["answer", "solution"])):
            indices: list[int] = []
            for source_role in source_roles:
                indices.extend(inv["roles"][source_role]["top_indices"])
            exclusion = exclusions.get(item_id)
            if role == "note" and exclusion:
                # Exclude only a source-proven table cell, never a guessed
                # paragraph or a whole solution region.
                bad = int(exclusion.get("paragraph_index", -1))
                approved = set(inv.get("excluded_next_section_metadata", []))
                if bad in approved:
                    indices = [index for index in indices if index != bad]
            src_events = payload(source, [source_top[index] for index in indices])
            dst_events = want[role]
            src_text = text_series(src_events)
            dst_text = text_series(dst_events)
            if role == "note":
                dst_text = re.sub(r"^\s*정답\s*:\s*", "", dst_text)
                dst_text = re.sub(r"해설\s*:\s*", "", dst_text, count=1)
            row[role + "_text_nonspace_equal"] = re.sub(r"\s", "", src_text) == re.sub(r"\s", "", dst_text)
            row[role + "_equation_equal"] = series(src_events, "equation") == series(dst_events, "equation")
            row[role + "_image_equal"] = series(src_events, "image") == series(dst_events, "image")
            row[role + "_source_sha256"] = digest(src_text.encode())
            row[role + "_output_sha256"] = digest(dst_text.encode())
            row[role + "_excluded_metadata"] = bool(exclusion and role == "note")
        row["status"] = "PASS" if all(value for key, value in row.items() if key.endswith("_equal")) else "REVIEW_REQUIRED"
        source_rows.append(row)
    all_roundtrip = not mismatches and len(actual) == len(expected) == len(selected)
    all_source = not missing and all(str(row.get("status", "")).startswith("PASS") for row in source_rows)
    result = {
        "schema": "teacher-full-audit/v3",
        "scope_ids": selected,
        "source_stage_sha256": file_hash(args.source_stage),
        "target_sha256": {"hwp": file_hash(args.target_hwp), "hwpx": file_hash(args.target_hwpx)},
        "checks": {
            "full_scope_count": len(selected),
            "target_anchor_count": len(actual),
            "source_ids_resolve": not missing,
            "target_payload_equal_to_build_expected": all_roundtrip,
            "source_payload_equal_after_boundary_normalization": all_source,
        },
        "mismatch_ids": mismatches,
        "missing_ids": missing,
        "boundary_exclusion_ids": sorted(exclusions),
        "roundtrip_rows": roundtrip_rows,
        "source_rows": source_rows,
        "scope_claim": "full selected source inventory content closure only; not visual/font/COM/clipboard FINAL",
    }
    write_json(args.out, result)
    print(json.dumps({"status": "PASS" if all_roundtrip and all_source else "REVIEW_REQUIRED", "scope": len(selected), "mismatches": len(mismatches), "missing": len(missing)}))
    return 0 if all_roundtrip and all_source else 2


if __name__ == "__main__":
    raise SystemExit(main())
