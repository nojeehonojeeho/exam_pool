"""Prove that one selected question transfers with its native endnote.

Unlike the in-place editor probe, this uses a fresh destination document.  It
models the teacher workflow directly: select a question in the integrated
book, copy it, and paste it into another HWP document.  Source files are read
only and every test artefact is written below ``--out``.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

import pythoncom
import win32clipboard

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.hwpx_content_snapshot import read_hwpx_snapshot
from app.hwp_native_clipboard import wait_native_payload
from hwp_native_endnote_transfer_probe import (  # type: ignore[import-not-found]
    _open_tracked_hwp,
    _quit_tracked_hwp,
    _select_main_paragraph_for_endnote,
)


def sha256(path: Path) -> str:
    return hashlib.file_digest(path.open("rb"), "sha256").hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source_hwp", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--note-index", type=int, required=True, help="zero-based endnote index")
    args = parser.parse_args()
    started = time.time()
    source_hwp = args.source_hwp.resolve()
    source_hwpx = source_hwp.with_suffix(".hwpx")
    out = args.out.resolve()
    report_path = out / f"cross-document-copy-note-{args.note_index + 1:03d}-report.json"
    out.mkdir(parents=True, exist_ok=True)
    result: dict[str, object]
    source = None
    destination = None
    source_tracking: dict | None = None
    destination_tracking: dict | None = None
    try:
        if not source_hwp.is_file() or not source_hwpx.is_file():
            raise FileNotFoundError("source must be a sibling HWP/HWPX pair")
        baseline = read_hwpx_snapshot(source_hwpx, include_body=False)
        notes = list(baseline.get("endnotes", []))
        if not 0 <= args.note_index < len(notes):
            raise ValueError(f"note index must be 0..{len(notes) - 1}")
        source_hwp_hash = sha256(source_hwp)
        source_hwpx_hash = sha256(source_hwpx)

        source, source_tracking = _open_tracked_hwp()
        if not source.open(str(source_hwp), format="HWP"):
            raise RuntimeError("SOURCE_HWP_OPEN_FAILED")
        selected_text, selected_equations, selected_notes = _select_main_paragraph_for_endnote(source, args.note_index)
        if selected_notes != 1:
            raise RuntimeError(f"SOURCE_SELECTION_NATIVE_NOTE_COUNT:{selected_notes}")
        sequence_before = win32clipboard.GetClipboardSequenceNumber()
        if not source.Copy():
            raise RuntimeError("SOURCE_HWP_COPY_FAILED")
        clipboard = wait_native_payload(win32clipboard, sequence_before, pump=pythoncom.PumpWaitingMessages)
        if not clipboard.get("ready"):
            raise RuntimeError("NATIVE_HWP_CLIPBOARD_NOT_READY")
        _quit_tracked_hwp(source, source_tracking)
        source = None

        destination, destination_tracking = _open_tracked_hwp()
        # A new document starts in the main story.  Its native paste is the
        # behaviour users need when assembling a separate handout.
        paste_return = destination.Paste()
        if not paste_return:
            raise RuntimeError("DESTINATION_HWP_NATIVE_PASTE_FAILED")
        output_hwp = out / f"cross-document-copy-note-{args.note_index + 1:03d}.hwp"
        output_hwpx = out / f"cross-document-copy-note-{args.note_index + 1:03d}.hwpx"
        if not destination.save_as(str(output_hwp), format="HWP"):
            raise RuntimeError("DESTINATION_HWP_SAVE_FAILED")
        if not destination.save_as(str(output_hwpx), format="HWPX"):
            raise RuntimeError("DESTINATION_HWPX_SAVE_FAILED")
        _quit_tracked_hwp(destination, destination_tracking)
        destination = None

        reopened, reopen_tracking = _open_tracked_hwp()
        try:
            if not reopened.open(str(output_hwp), format="HWP"):
                raise RuntimeError("DESTINATION_HWP_REOPEN_FAILED")
            readback_hwpx = out / f"cross-document-copy-note-{args.note_index + 1:03d}-readback.hwpx"
            if not reopened.save_as(str(readback_hwpx), format="HWPX"):
                raise RuntimeError("DESTINATION_HWPX_READBACK_SAVE_FAILED")
        finally:
            _quit_tracked_hwp(reopened, reopen_tracking)
        copied = read_hwpx_snapshot(readback_hwpx, include_body=False)
        copied_notes = list(copied.get("endnotes", []))
        expected = dict(notes[args.note_index])
        expected.pop("number", None)
        actual = dict(copied_notes[0]) if copied_notes else {}
        actual.pop("number", None)
        checks = {
            "source_hwp_unchanged": source_hwp_hash == sha256(source_hwp),
            "source_hwpx_unchanged": source_hwpx_hash == sha256(source_hwpx),
            "native_clipboard_ready": bool(clipboard.get("ready")),
            "selected_one_native_reference": selected_notes == 1,
            "copied_exactly_one_native_endnote": len(copied_notes) == 1,
            "copied_endnote_body_matches_source": actual == expected,
            "source_process_exited": bool(source_tracking["lifecycle"]["wait"]["status"] == "OK"),
            "destination_process_exited": bool(destination_tracking["lifecycle"]["wait"]["status"] == "OK"),
            "reopen_process_exited": bool(reopen_tracking["lifecycle"]["wait"]["status"] == "OK"),
        }
        result = {
            "schema": "hwp-native-endnote-cross-document-probe-v1",
            "status": "PASS" if all(checks.values()) else "FAIL",
            "source_hwp": str(source_hwp), "source_hwpx": str(source_hwpx),
            "output_hwp": str(output_hwp), "output_hwpx": str(output_hwpx), "readback_hwpx": str(readback_hwpx),
            "note_index": args.note_index, "clipboard": clipboard,
            "selected_text_sha256": hashlib.sha256((selected_text or "").encode("utf-8")).hexdigest(),
            "selected_equation_count": selected_equations, "checks": checks,
        }
    except Exception as exc:
        result = {"schema": "hwp-native-endnote-cross-document-probe-v1", "status": "FAIL", "note_index": args.note_index, "error": {"type": type(exc).__name__, "message": str(exc)}}
    finally:
        if destination is not None and destination_tracking is not None:
            try:
                _quit_tracked_hwp(destination, destination_tracking)
            except Exception:
                pass
        if source is not None and source_tracking is not None:
            try:
                _quit_tracked_hwp(source, source_tracking)
            except Exception:
                pass
    result["elapsed_seconds"] = round(time.time() - started, 3)
    report_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": result["status"], "report": str(report_path)}, ensure_ascii=False))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
