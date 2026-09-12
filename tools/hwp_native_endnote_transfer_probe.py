"""Perform one bounded, serial HWP native-endnote copy/move test.

This tool never edits its source HWP/HWPX.  It writes fresh HWP/HWPX probe
files under ``--out`` and proves that the copied/moved question kept its actual
native endnote body after HWP save and reopen.  It is intentionally a bounded
editor-behaviour test, not a substitute for full-book source-fidelity QA.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import time
import xml.etree.ElementTree as ET
from zipfile import ZipFile

import pythoncom
import win32clipboard

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.hwp_endnote_transfer_contract import (
    _equation_count,
    validate_endnote_placement_values,
    validate_endnote_transfer,
)
from app.hwp_process_lifecycle import (
    HwpProcessSnapshot,
    HwpProcessWait,
    newly_started_hwp_processes,
    snapshot_hwp_processes,
    wait_for_hwp_processes_to_exit,
)
from app.hwp_native_clipboard import wait_native_payload
from app.hwp_native_equation_writer import read_equation_snapshot
from app.hwpx_content_snapshot import read_hwpx_snapshot
from app.integrations.hwp_security import create_secure_hwp


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _endnote_placement_is_document_end(hwpx: Path) -> bool:
    with ZipFile(hwpx) as package:
        sections = [
            name for name in package.namelist()
            if name.startswith("Contents/section") and name.endswith(".xml")
        ]
        declarations: list[list[str | None]] = []
        for name in sections:
            root = ET.fromstring(package.read(name))
            for node in root.findall(".//{*}endNotePr"):
                declarations.append([
                    child.get("place") for child in node.findall("./{*}placement")
                ])
        native_endnotes_present = any(
            ET.fromstring(package.read(name)).findall(".//{*}endNote")
            for name in sections
        )
        return validate_endnote_placement_values(
            declarations, native_endnotes_present=native_endnotes_present
        )


def _selection_visible_evidence(xml: str, fallback_text: str) -> tuple[str, int, int]:
    """Return visible main-story text, equations, and native-note count.

    Hanword's ``UNICODE`` saveblock includes the nested endnote body. That is
    useful for clipboard transfer but it is not evidence that selection began
    in the main question. HWPML2X is parsed to exclude text and equations
    below ``hp:endNote`` while retaining the native control count.
    """

    if not xml:
        return fallback_text, 0, 0
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return (
            fallback_text,
            len(re.findall(r"<(?:[A-Za-z_][\w.-]*:)?equation\b", xml, flags=re.I)),
            len(re.findall(r"<(?:[A-Za-z_][\w.-]*:)?endNote(?:\s|>)", xml, flags=re.I)),
        )
    parent = {child: parent for parent in root.iter() for child in parent}

    def under_endnote(element: ET.Element) -> bool:
        current = parent.get(element)
        while current is not None:
            if current.tag.rsplit("}", 1)[-1].split(":", 1)[-1].lower() == "endnote":
                return True
            current = parent.get(current)
        return False

    visible: list[str] = []
    equations = 0
    note_count = 0
    for element in root.iter():
        local = element.tag.rsplit("}", 1)[-1].split(":", 1)[-1].lower()
        if local == "endnote":
            note_count += 1
        elif local == "t" and not under_endnote(element):
            visible.append(element.text or "")
        elif local == "equation" and not under_endnote(element):
            equations += 1
    return " ".join(visible).strip() or fallback_text, equations, note_count


def _selected_main_evidence(hwp: object) -> tuple[str | None, int | None, int]:
    """Read the currently selected main-question block without mutating it."""
    get_text_file = getattr(hwp, "get_text_file", None)
    if not callable(get_text_file):
        return None, None, 0
    text = str(get_text_file("UNICODE", "saveblock:true") or "")
    xml = str(get_text_file("HWPML2X", "saveblock:true") or "")
    visible_text, equations, note_count = _selection_visible_evidence(xml, text)
    return (visible_text or None), equations, note_count


def _select_main_paragraph_for_endnote(
    hwp: object,
    note_index: int,
    *,
    max_paragraphs: int = 20000,
) -> tuple[str | None, int | None, int]:
    """Select the main-story paragraph that owns one native endnote.

    ``Ctrl.GetAnchorPos(0)`` points into the endnote sub-list on some Hanword
    builds. Walking only top-level paragraphs and counting the endnote control
    in each HWPML2X selection avoids selecting the body as if it were the
    question. The matching selection is left active for native Copy/Cut.
    """

    move_doc_begin = getattr(hwp, "MoveDocBegin", None)
    if not callable(move_doc_begin):
        raise RuntimeError("HWP_MAIN_STORY_ENUMERATION_UNAVAILABLE")
    move_doc_begin()
    seen: set[tuple[int, int, int]] = set()
    found = 0
    for _ in range(max_paragraphs):
        try:
            start = tuple(int(value) for value in hwp.GetPos())
        except Exception as exc:
            raise RuntimeError("HWP_MAIN_STORY_POSITION_UNAVAILABLE") from exc
        if start in seen:
            break
        seen.add(start)
        try:
            hwp.MoveSelParaEnd()
            end = tuple(int(value) for value in hwp.GetPos())
            if start[0] == 0 and end != start and hwp.select_text_by_get_pos(start, end):
                text = str(hwp.get_text_file("UNICODE", "saveblock:true") or "")
                xml = str(hwp.get_text_file("HWPML2X", "saveblock:true") or "")
                _, _, native_count = _selection_visible_evidence(xml, text)
                if native_count:
                    if found <= note_index < found + native_count:
                        visible, equations, selected_count = _selected_main_evidence(hwp)
                        return visible, equations, selected_count
                    found += native_count
            try:
                hwp.Cancel()
            except Exception:
                pass
            hwp.SetPos(*start)
        except Exception:
            try:
                hwp.Cancel()
            except Exception:
                pass
            try:
                hwp.SetPos(*start)
            except Exception:
                pass
        move_next = getattr(hwp, "MoveNextParaBegin", None)
        if not callable(move_next) or not move_next():
            break
    raise RuntimeError(
        f"HWP_MAIN_ENDNOTE_ANCHOR_NOT_FOUND: index={note_index}, found={found}"
    )


def _snapshot_text(value: object) -> str:
    """Flatten visible text from a saved HWPX main-body snapshot."""
    if isinstance(value, dict):
        if value.get("type") == "text":
            return str(value.get("text") or "")
        return "".join(_snapshot_text(child) for child in value.values())
    if isinstance(value, list):
        return "".join(_snapshot_text(child) for child in value)
    return ""


def _main_text_diagnostic(
    baseline_text: str,
    actual_text: str,
    selected_text: str | None,
) -> dict[str, object]:
    """Record representation-safe main-story evidence for the transfer report."""
    def normalise(value: str | None) -> str:
        return re.sub(r"\s+", " ", str(value or "")).strip()

    def tokens(value: str | None) -> list[str]:
        return re.findall(r"[0-9A-Za-z가-힣]+", normalise(value))

    baseline = normalise(baseline_text)
    actual = normalise(actual_text)
    selected = normalise(selected_text)
    appended = actual[len(baseline) :].strip() if actual.startswith(baseline) else ""
    selected_tokens = tokens(selected)
    appended_counts: dict[str, int] = {}
    for token in tokens(appended):
        appended_counts[token] = appended_counts.get(token, 0) + 1
    covered = sum(
        min(count, appended_counts.get(token, 0))
        for token, count in __import__("collections").Counter(selected_tokens).items()
    )
    return {
        "baseline_length": len(baseline),
        "actual_length": len(actual),
        "selected_length": len(selected),
        "actual_starts_with_baseline": actual.startswith(baseline),
        "appended_length": len(appended),
        "selected_token_count": len(selected_tokens),
        "selected_token_coverage": round(covered / len(selected_tokens), 6) if selected_tokens else 0.0,
    }


def _require_hwp_process_snapshot() -> HwpProcessSnapshot:
    """Take a fail-closed HWP process snapshot for one COM lifecycle edge."""
    snapshot = snapshot_hwp_processes()
    if snapshot.status != "OK":
        raise RuntimeError("HWP_PID_ENUMERATION_UNAVAILABLE")
    return snapshot


def _open_tracked_hwp() -> tuple[object, dict[str, object]]:
    """Create one HWP COM session and require a newly observed process.

    The process delta uses PID plus creation time, so a pre-existing or PID
    reused HWP process is never treated as this session's process.  This
    function only observes; it does not terminate any process.
    """
    before = _require_hwp_process_snapshot()
    hwp = create_secure_hwp(new=True, visible=False, on_quit=False)
    after = _require_hwp_process_snapshot()
    delta = newly_started_hwp_processes(before, after)
    if delta.status != "OK":
        raise RuntimeError("HWP_PID_ENUMERATION_UNAVAILABLE")
    if not delta.processes:
        raise RuntimeError("HWP_COM_PROCESS_NOT_OBSERVED")
    lifecycle: dict[str, object] = {
        "before_start": before.as_dict(),
        "after_start": after.as_dict(),
        "delta": delta.as_dict(),
        "wait": None,
    }
    return hwp, {"tracked": delta.processes, "lifecycle": lifecycle}


def _raw_quit_if_unmodified(hwp: object) -> dict[str, object]:
    """Attempt raw ``HwpObject.Quit`` only after an explicit clean-state check.

    ``pyhwpx.Hwp.quit(save=False)`` calls its own ``Clear`` first.  Some
    Hanword builds can raise from that wrapper even though the underlying
    ``HwpObject`` can still close normally.  The raw fallback is deliberately
    narrow: the caller has already proven this wrapper owns a newly observed
    HWP PID, and this function refuses to call ``Quit`` unless the raw object
    reports ``IsModified == False``.  Missing/ambiguous state is never treated
    as clean.
    """
    record: dict[str, object] = {
        "attempted": False,
        "succeeded": False,
        "is_modified": None,
        "error": None,
    }
    raw = getattr(hwp, "hwp", None)
    if raw is None:
        record["error"] = "raw HwpObject is unavailable"
        return record
    try:
        modified = getattr(raw, "IsModified")
        if callable(modified):
            modified = modified()
    except Exception as exc:
        record["error"] = f"IsModified read failed: {exc!r}"
        return record
    record["is_modified"] = modified
    # Do not coerce None, strings, or arbitrary truthy values into a clean
    # state.  pywin32 normally returns bool/int for this COM property.
    if modified is None or bool(modified):
        record["error"] = "raw HwpObject is modified or modification state is ambiguous"
        return record
    record["attempted"] = True
    try:
        raw.Quit()
    except Exception as exc:
        record["error"] = repr(exc)
        return record
    record["succeeded"] = True
    return record


def _quit_tracked_hwp(hwp: object, tracked: dict[str, object]) -> HwpProcessWait:
    """Quit one owned COM wrapper and require its observed process to exit.

    A wrapper failure may use the raw COM fallback, but only for the tracked
    process identities supplied by :func:`_open_tracked_hwp`.  Unknown or
    empty ownership is rejected before either quit path is called.
    """
    identities = tracked.get("tracked")
    if not identities or isinstance(identities, dict):
        raise RuntimeError("HWP_COM_QUIT_UNOWNED")
    lifecycle = tracked["lifecycle"]
    assert isinstance(lifecycle, dict)
    quit_record: dict[str, object] = {
        "wrapper_attempted": True,
        "wrapper_succeeded": False,
        "wrapper_error": None,
        "raw_attempted": False,
        "raw_succeeded": False,
        "raw_is_modified": None,
        "raw_error": None,
        "path": None,
    }
    quit_error: BaseException | None = None
    try:
        hwp.quit(save=False)
        quit_record["wrapper_succeeded"] = True
        quit_record["path"] = "pyhwpx_wrapper_quit"
    except Exception as exc:
        quit_error = exc
        quit_record["wrapper_error"] = repr(exc)
        raw_record = _raw_quit_if_unmodified(hwp)
        quit_record["raw_attempted"] = bool(raw_record["attempted"])
        quit_record["raw_succeeded"] = bool(raw_record["succeeded"])
        quit_record["raw_is_modified"] = raw_record["is_modified"]
        quit_record["raw_error"] = raw_record["error"]
        if raw_record["succeeded"]:
            quit_record["path"] = "raw_com_quit_after_wrapper_error"
    lifecycle["quit"] = quit_record

    after_quit = _require_hwp_process_snapshot()
    lifecycle["after_quit"] = after_quit.as_dict()
    result = wait_for_hwp_processes_to_exit(identities)  # type: ignore[arg-type]
    lifecycle["wait"] = result.as_dict()
    if not result.exited:
        raise RuntimeError(f"HWP_COM_PROCESS_NOT_EXITED:{result.status}")
    if quit_error is not None and not quit_record["raw_succeeded"]:
        raise RuntimeError("HWP_COM_QUIT_FAILED") from quit_error
    return result


def probe(source_hwp: Path, output_dir: Path, *, mode: str, note_index: int) -> dict:
    source_hwp = source_hwp.resolve()
    source_hwpx = source_hwp.with_suffix(".hwpx")
    if not source_hwp.is_file() or not source_hwpx.is_file():
        raise FileNotFoundError("source must be an HWP/HWPX sibling pair")
    if mode not in {"copy", "move"}:
        raise ValueError("mode must be copy or move")
    baseline = read_hwpx_snapshot(source_hwpx)
    baseline_notes = list(baseline.get("endnotes", []))
    if not 0 <= note_index < len(baseline_notes):
        raise ValueError(f"note index {note_index} is outside 0..{len(baseline_notes) - 1}")

    output_dir.mkdir(parents=True, exist_ok=True)
    output_hwpx = output_dir / f"{mode}-note-{note_index + 1:03d}.hwpx"
    output_hwp = output_dir / f"{mode}-note-{note_index + 1:03d}.hwp"
    if output_hwpx.exists() or output_hwp.exists():
        raise FileExistsError(f"probe output already exists: {output_hwpx}")
    source_hwp_sha = _sha256(source_hwp)
    source_hwpx_sha = _sha256(source_hwpx)
    hwp, first_tracking = _open_tracked_hwp()
    clipboard_record: dict = {}
    selected_main_text: str | None = None
    selected_main_equation_count: int | None = None
    selected_native_endnote_count: int | None = None
    try:
        if not hwp.open(str(source_hwp), format="HWP"):
            raise RuntimeError("source HWP open failed")
        before = read_equation_snapshot(hwp)
        notes = [ctrl for ctrl in hwp.ctrl_list if str(ctrl.CtrlID).strip() == "en"]
        if len(notes) != len(baseline_notes):
            raise RuntimeError(
                f"COM native note count differs from saved HWPX: {len(notes)} != {len(baseline_notes)}"
            )
        selected_main_text, selected_main_equation_count, selected_native_endnote_count = (
            _select_main_paragraph_for_endnote(hwp, note_index)
        )
        if selected_main_equation_count is None:
            raise RuntimeError("selected main-question HWPML2X evidence unavailable")
        if selected_native_endnote_count != 1:
            raise RuntimeError(
                f"native question selection did not contain exactly one endnote reference: {selected_native_endnote_count}"
            )
        sequence_before = win32clipboard.GetClipboardSequenceNumber()
        if not (hwp.Copy() if mode == "copy" else hwp.Cut()):
            raise RuntimeError(f"HWP {mode} action failed")
        clipboard_record = wait_native_payload(
            win32clipboard,
            sequence_before,
            pump=pythoncom.PumpWaitingMessages,
        )
        if not clipboard_record.get("ready"):
            raise RuntimeError("native HWP clipboard payload was not ready within the bounded wait")
        hwp.Cancel()
        # MoveDocEnd can remain inside an endnote/table list.  The top-level
        # main story is required so the copied native reference has a valid owner.
        hwp.MoveTopLevelEnd()
        destination = tuple(hwp.get_pos())
        if destination[0] != 0:
            raise RuntimeError(f"native paste destination is not the main story: {destination}")
        hwp.BreakPara()
        if not hwp.Paste():
            raise RuntimeError("native HWP paste failed")
        if not hwp.save_as(str(output_hwpx.resolve()), format="HWPX"):
            raise RuntimeError("probe HWPX save failed")
        if not hwp.save_as(str(output_hwp.resolve()), format="HWP"):
            raise RuntimeError("probe HWP save failed")
    finally:
        notes = []
        _quit_tracked_hwp(hwp, first_tracking)

    reopened, second_tracking = _open_tracked_hwp()
    after_main_text = ""
    try:
        if not reopened.open(str(output_hwp), format="HWP"):
            raise RuntimeError("probe HWP reopen failed")
        after = read_equation_snapshot(reopened)
        # The pre-save HWPX is not authoritative: HWP may rewrite native
        # controls during reopen.  Save a fresh HWPX from this reopened COM
        # session and use that package for all structural assertions.
        reopened_hwpx = output_dir / f"{mode}-note-{note_index + 1:03d}-reopen.hwpx"
        if not reopened.save_as(str(reopened_hwpx.resolve()), format="HWPX"):
            raise RuntimeError("reopened HWPX readback save failed")
        after_main_text = _snapshot_text(read_hwpx_snapshot(reopened_hwpx).get("body", []))
    finally:
        _quit_tracked_hwp(reopened, second_tracking)

    reopened_hwpx = output_dir / f"{mode}-note-{note_index + 1:03d}-reopen.hwpx"
    actual = read_hwpx_snapshot(reopened_hwpx)
    baseline_main_text = _snapshot_text(baseline.get("body", []))
    actual_hwpx_equations = _equation_count(actual)
    checks = validate_endnote_transfer(
        baseline,
        actual,
        mode=mode,
        note_index=note_index,
        before_equation_count=int(before.get("equation_count", 0)),
        after_equation_count=int(after.get("equation_count", 0)),
        source_hwp_unchanged=source_hwp_sha == _sha256(source_hwp),
        source_hwpx_unchanged=source_hwpx_sha == _sha256(source_hwpx),
        placement_is_end_of_document=_endnote_placement_is_document_end(reopened_hwpx),
        selected_question_equation_count=selected_main_equation_count,
        baseline_main_text=baseline_main_text,
        actual_main_text=after_main_text,
        selected_main_text=selected_main_text,
        selected_native_endnote_count=selected_native_endnote_count,
    )
    checks["reopened_hwpx_matches_com_equation_count"] = (
        actual_hwpx_equations == int(after.get("equation_count", 0))
    )
    checks["hwp_processes_exited"] = bool(
        first_tracking["lifecycle"]["wait"]["status"] == "OK"  # type: ignore[index]
        and second_tracking["lifecycle"]["wait"]["status"] == "OK"  # type: ignore[index]
    )
    return {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "scope": "bounded_native_endnote_transfer_editor_test",
        "mode": mode,
        "note_index": note_index,
        "source_hwp": str(source_hwp),
        "source_hwpx": str(source_hwpx),
        "output_hwp": str(output_hwp),
        "output_hwpx": str(output_hwpx),
        "reopened_hwpx": str(reopened_hwpx),
        "source_hwp_sha256": source_hwp_sha,
        "source_hwpx_sha256": source_hwpx_sha,
        "clipboard": clipboard_record,
        "before_com": before,
        "after_com": after,
        "selected_main_text_sha256": hashlib.sha256((selected_main_text or "").encode("utf-8")).hexdigest(),
        "selected_main_equation_count": selected_main_equation_count,
        "reopened_main_text_sha256": hashlib.sha256(after_main_text.encode("utf-8")).hexdigest(),
        "main_text_diagnostic": _main_text_diagnostic(
            baseline_main_text, after_main_text, selected_main_text
        ),
        "hwp_process_lifecycle": {
            "initial": first_tracking["lifecycle"],
            "reopen": second_tracking["lifecycle"],
        },
        "checks": checks,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source_hwp", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--note-index", type=int, required=True, help="zero-based native endnote index")
    parser.add_argument("--mode", choices=("copy", "move"), required=True)
    args = parser.parse_args()
    started = time.time()
    result = probe(args.source_hwp, args.out, mode=args.mode, note_index=args.note_index)
    result["elapsed_seconds"] = round(time.time() - started, 3)
    report = args.out / f"{args.mode}-note-{args.note_index + 1:03d}-report.json"
    report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "checks": result["checks"], "report": str(report)}, ensure_ascii=False))
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
