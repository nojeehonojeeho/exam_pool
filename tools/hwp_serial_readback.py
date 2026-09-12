"""Fail-closed, serial HWP/HWPX save and COM readback command.

This command is an application-boundary helper for a *derived* document.  It
opens one input document in a securely registered Hanword COM session, saves
the requested HWP/HWPX/PDF outputs, closes that owned session, and then opens
one of the newly saved editable outputs in a second session.  A fresh HWPX
readback can optionally be saved from that second session.

The input is never written.  Existing output files are rejected rather than
overwritten, and all COM sessions are serial.  Process ownership is proved by
the PID + creation-time delta from :mod:`app.hwp_process_lifecycle`; an empty
or unavailable delta is a hard failure.  This tool never kills or terminates
an Hwp.exe process that it cannot prove is owned by the current session.

It is intentionally not a source-fidelity gate.  The source manifest, formula
provenance, endnote contract, and visual comparison gates remain required for
release.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.hwp_process_lifecycle import (  # noqa: E402
    HwpProcessSnapshot,
    HwpProcessWait,
    newly_started_hwp_processes,
    snapshot_hwp_processes,
    wait_for_hwp_processes_to_exit,
)
from app.hwp_owned_quit import quit_tracked_with_safe_fallback  # noqa: E402
from app.integrations.hwp_security import create_secure_hwp  # noqa: E402


class HwpReadbackError(RuntimeError):
    """A bounded, auditable failure; callers must not promote the output."""

    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(f"{code}: {message}")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _resolved(path: Path) -> Path:
    return Path(path).expanduser().resolve()


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def validate_paths(
    input_path: Path,
    *,
    output_hwp: Path | None = None,
    output_hwpx: Path | None = None,
    output_pdf: Path | None = None,
    readback_hwpx: Path | None = None,
    report: Path | None = None,
) -> dict[str, Path | None]:
    """Validate a non-overwriting, source-separated path plan.

    A derived output is not allowed in the source directory.  This conservative
    rule prevents accidental mutation of an input/delivery package when a
    caller passes a package file as the input and forgets to choose a work
    directory.
    """
    source = _resolved(input_path)
    if not source.is_file():
        raise HwpReadbackError("INPUT_NOT_FOUND", f"input is not a file: {source}")
    if source.suffix.casefold() not in {".hwp", ".hwpx"}:
        raise HwpReadbackError("INPUT_FORMAT_UNSUPPORTED", "input must end in .hwp or .hwpx")
    raw: dict[str, Path | None] = {
        "output_hwp": _resolved(output_hwp) if output_hwp else None,
        "output_hwpx": _resolved(output_hwpx) if output_hwpx else None,
        "output_pdf": _resolved(output_pdf) if output_pdf else None,
        "readback_hwpx": _resolved(readback_hwpx) if readback_hwpx else None,
        "report": _resolved(report) if report else None,
    }
    editable_outputs = [raw["output_hwp"], raw["output_hwpx"]]
    if not any(editable_outputs):
        raise HwpReadbackError(
            "EDITABLE_OUTPUT_REQUIRED",
            "at least one derived HWP or HWPX output is required for COM readback",
        )
    outputs = [value for value in raw.values() if value is not None]
    if len(set(outputs)) != len(outputs):
        raise HwpReadbackError("OUTPUT_PATH_COLLISION", "output paths must be unique")
    for value in outputs:
        assert value is not None
        if value == source:
            raise HwpReadbackError("INPUT_OVERWRITE_BLOCKED", f"output equals input: {source}")
        if _is_relative_to(value, source.parent):
            raise HwpReadbackError(
                "SOURCE_DIRECTORY_OUTPUT_BLOCKED",
                f"derived output must be outside the input directory: {value}",
            )
        if value.exists():
            raise HwpReadbackError("OUTPUT_EXISTS", f"refusing to overwrite existing file: {value}")
    if raw["output_hwp"] and raw["output_hwp"].suffix.casefold() != ".hwp":  # type: ignore[union-attr]
        raise HwpReadbackError("OUTPUT_FORMAT_MISMATCH", "--output-hwp must end in .hwp")
    if raw["output_hwpx"] and raw["output_hwpx"].suffix.casefold() != ".hwpx":  # type: ignore[union-attr]
        raise HwpReadbackError("OUTPUT_FORMAT_MISMATCH", "--output-hwpx must end in .hwpx")
    if raw["output_pdf"] and raw["output_pdf"].suffix.casefold() != ".pdf":  # type: ignore[union-attr]
        raise HwpReadbackError("OUTPUT_FORMAT_MISMATCH", "--output-pdf must end in .pdf")
    if raw["readback_hwpx"] and raw["readback_hwpx"].suffix.casefold() != ".hwpx":  # type: ignore[union-attr]
        raise HwpReadbackError("OUTPUT_FORMAT_MISMATCH", "--readback-hwpx must end in .hwpx")
    return {"input": source, **raw}


def _require_hwp_snapshot(snapshot_fn: Callable[[], HwpProcessSnapshot]) -> HwpProcessSnapshot:
    snapshot = snapshot_fn()
    if snapshot.status != "OK":
        raise HwpReadbackError(
            "HWP_PID_ENUMERATION_UNAVAILABLE",
            snapshot.error or "HWP process snapshot was unavailable",
        )
    return snapshot


def _open_tracked_session(
    *,
    factory: Callable[..., Any] = create_secure_hwp,
    snapshot_fn: Callable[[], HwpProcessSnapshot] = snapshot_hwp_processes,
) -> tuple[Any, dict[str, Any]]:
    """Create one secure HWP session and require an observed new process."""
    before = _require_hwp_snapshot(snapshot_fn)
    try:
        hwp = factory(new=True, visible=False, on_quit=False)
    except Exception as exc:
        # Ownership is unknown if construction raises.  Do not call quit on a
        # potentially unrelated HWP process; the error is deliberately loud.
        raise HwpReadbackError("HWP_SESSION_CREATE_FAILED", repr(exc)) from exc
    after = _require_hwp_snapshot(snapshot_fn)
    delta = newly_started_hwp_processes(before, after)
    if delta.status != "OK":
        raise HwpReadbackError("HWP_PID_ENUMERATION_UNAVAILABLE", delta.error or "delta unavailable")
    if not delta.processes:
        raise HwpReadbackError(
            "HWP_COM_PROCESS_NOT_OBSERVED",
            "HWP COM creation did not produce a new PID+creation-time identity",
        )
    registration = getattr(getattr(hwp, "_hwp_security_registration", None), "returned", None)
    if registration is not True:
        raise HwpReadbackError("HWP_SECURITY_MODULE_NOT_ACTIVE", "RegisterModule did not return True")
    return hwp, {
        "before_start": before.as_dict(),
        "after_start": after.as_dict(),
        "delta": delta.as_dict(),
        "wait": None,
        "register_module_return": registration,
    }


def _close_tracked_session(
    hwp: Any,
    lifecycle: dict[str, Any],
    *,
    snapshot_fn: Callable[[], HwpProcessSnapshot] = snapshot_hwp_processes,
    wait_fn: Callable[..., HwpProcessWait] = wait_for_hwp_processes_to_exit,
    exit_timeout: float = 20.0,
) -> HwpProcessWait:
    """Close only the owned session and require bounded process exit."""
    quit_error: BaseException | None = None
    quit_record: dict[str, Any] | None = None
    identities = frozenset(
        (item["pid"], item["create_time"])
        for item in lifecycle["delta"]["processes"]
    )
    # Convert the auditable dict back to the public identity type without
    # reaching into psutil or using PID-only ownership.
    from app.hwp_process_lifecycle import HwpProcessIdentity
    tracked = frozenset(
        HwpProcessIdentity(pid=int(pid), create_time=float(created))
        for pid, created in identities
    )
    try:
        # The session was proven by _open_tracked_session. If the wrapper's
        # Clear path fails, raw Quit is permitted only for a clean document.
        quit_record = quit_tracked_with_safe_fallback(hwp, tracked=tracked)
    except Exception as exc:  # record and still observe process state
        quit_error = exc
        quit_record = getattr(exc, "record", None)
    lifecycle["quit"] = quit_record
    after = _require_hwp_snapshot(snapshot_fn)
    lifecycle["after_quit"] = after.as_dict()
    result = wait_fn(tracked, snapshot=snapshot_fn, timeout=exit_timeout)
    lifecycle["wait"] = result.as_dict()
    if not result.exited:
        raise HwpReadbackError("HWP_COM_PROCESS_NOT_EXITED", result.status)
    if quit_error is not None:
        code = getattr(quit_error, "code", "HWP_COM_QUIT_FAILED")
        raise HwpReadbackError(str(code), repr(quit_error))
    return result


def _open_input(hwp: Any, path: Path) -> None:
    fmt = "HWPX" if path.suffix.casefold() == ".hwpx" else "HWP"
    try:
        opened = hwp.open(str(path), format=fmt, arg="forceopen:true;suspendpassword:true")
    except Exception as exc:
        raise HwpReadbackError("HWP_INPUT_OPEN_FAILED", repr(exc)) from exc
    if opened is False:
        raise HwpReadbackError("HWP_INPUT_OPEN_FAILED", str(path))


def _save_output(hwp: Any, path: Path, fmt: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        saved = hwp.save_as(str(path), format=fmt)
    except Exception as exc:
        raise HwpReadbackError(f"HWP_{fmt}_SAVE_FAILED", repr(exc)) from exc
    if saved is False or not path.is_file():
        raise HwpReadbackError(f"HWP_{fmt}_SAVE_FAILED", str(path))


def run_readback(
    input_path: Path,
    *,
    output_hwp: Path | None = None,
    output_hwpx: Path | None = None,
    output_pdf: Path | None = None,
    readback_hwpx: Path | None = None,
    report: Path | None = None,
    factory: Callable[..., Any] = create_secure_hwp,
    snapshot_fn: Callable[[], HwpProcessSnapshot] = snapshot_hwp_processes,
    wait_fn: Callable[..., HwpProcessWait] = wait_for_hwp_processes_to_exit,
    exit_timeout: float = 20.0,
    clock: Callable[[], float] = time.time,
) -> dict[str, Any]:
    """Execute one serial save/readback transaction and return its report."""
    paths = validate_paths(
        input_path,
        output_hwp=output_hwp,
        output_hwpx=output_hwpx,
        output_pdf=output_pdf,
        readback_hwpx=readback_hwpx,
        report=report,
    )
    if os.name != "nt":
        raise HwpReadbackError("WINDOWS_HWP_COM_REQUIRED", "HWP COM readback is Windows-only")
    source = paths["input"]
    assert isinstance(source, Path)
    source_hash = _sha256(source)
    result: dict[str, Any] = {
        "schema": "hwp-serial-readback-v1",
        "status": "FAIL",
        "created_at": _dt.datetime.now().isoformat(timespec="seconds"),
        "input": str(source),
        "input_sha256_before": source_hash,
        "outputs": {},
        "lifecycle": [],
        "errors": [],
    }
    first_hwp = None
    first_lifecycle: dict[str, Any] | None = None
    try:
        first_hwp, first_lifecycle = _open_tracked_session(factory=factory, snapshot_fn=snapshot_fn)
        _open_input(first_hwp, source)
        if paths["output_hwp"]:
            _save_output(first_hwp, paths["output_hwp"], "HWP")  # type: ignore[arg-type]
        if paths["output_hwpx"]:
            _save_output(first_hwp, paths["output_hwpx"], "HWPX")  # type: ignore[arg-type]
        if paths["output_pdf"]:
            _save_output(first_hwp, paths["output_pdf"], "PDF")  # type: ignore[arg-type]
    except HwpReadbackError as exc:
        result["errors"].append({"code": exc.code, "message": str(exc)})
    finally:
        if first_hwp is not None and first_lifecycle is not None:
            try:
                _close_tracked_session(
                    first_hwp,
                    first_lifecycle,
                    snapshot_fn=snapshot_fn,
                    wait_fn=wait_fn,
                    exit_timeout=exit_timeout,
                )
            except HwpReadbackError as exc:
                result["errors"].append({"code": exc.code, "message": str(exc)})
            result["lifecycle"].append(first_lifecycle)
    first_outputs_exist = all(
        not paths[key] or paths[key].is_file() for key in ("output_hwp", "output_hwpx", "output_pdf")
    )
    if not result["errors"] and first_outputs_exist:
        # Prefer HWP for readback because it tests the binary delivery format;
        # otherwise use HWPX.  This session is opened only after the first one
        # has passed its bounded exit check.
        editable = paths["output_hwp"] or paths["output_hwpx"]
        second_hwp = None
        second_lifecycle: dict[str, Any] | None = None
        try:
            second_hwp, second_lifecycle = _open_tracked_session(factory=factory, snapshot_fn=snapshot_fn)
            _open_input(second_hwp, editable)  # type: ignore[arg-type]
            if paths["readback_hwpx"]:
                _save_output(second_hwp, paths["readback_hwpx"], "HWPX")  # type: ignore[arg-type]
        except HwpReadbackError as exc:
            result["errors"].append({"code": exc.code, "message": str(exc)})
        finally:
            if second_hwp is not None and second_lifecycle is not None:
                try:
                    _close_tracked_session(
                        second_hwp,
                        second_lifecycle,
                        snapshot_fn=snapshot_fn,
                        wait_fn=wait_fn,
                        exit_timeout=exit_timeout,
                    )
                except HwpReadbackError as exc:
                    result["errors"].append({"code": exc.code, "message": str(exc)})
                result["lifecycle"].append(second_lifecycle)
    if source_hash != _sha256(source):
        result["errors"].append({"code": "INPUT_CHANGED", "message": "input SHA-256 changed during readback"})
    for key in ("output_hwp", "output_hwpx", "output_pdf", "readback_hwpx"):
        value = paths[key]
        if value and value.is_file():
            result["outputs"][key] = {"path": str(value), "sha256": _sha256(value)}
    result["status"] = "PASS" if not result["errors"] and len(result["lifecycle"]) == 2 else "FAIL"
    result["input_sha256_after"] = _sha256(source)
    if report:
        report_path = paths["report"]
        assert isinstance(report_path, Path)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        result["report"] = str(report_path)
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output-hwp", type=Path)
    parser.add_argument("--output-hwpx", type=Path)
    parser.add_argument("--output-pdf", type=Path)
    parser.add_argument("--readback-hwpx", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--exit-timeout", type=float, default=20.0)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = run_readback(
            args.input,
            output_hwp=args.output_hwp,
            output_hwpx=args.output_hwpx,
            output_pdf=args.output_pdf,
            readback_hwpx=args.readback_hwpx,
            report=args.report,
            exit_timeout=args.exit_timeout,
        )
    except HwpReadbackError as exc:
        result = {
            "schema": "hwp-serial-readback-v1",
            "status": "FAIL",
            "error": {"code": exc.code, "message": str(exc)},
        }
        try:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        except OSError:
            pass
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("status") == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
