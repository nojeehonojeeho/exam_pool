"""Bounded serial probe for Hanword FilePathChecker automation security.

The probe writes only to a fresh ``work/hwp_security_probe_*`` directory.  It
never clicks approval dialogs and never terminates an unrelated Hwp.exe.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import time
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.integrations.hwp_security import create_secure_hwp, security_snapshot


def _hwp_pid_snapshot() -> dict[str, object]:
    try:
        import psutil

        return {
            "status": "OK",
            "pids": {
                int(proc.pid)
                for proc in psutil.process_iter(("name",))
                if str(proc.info.get("name") or "").casefold() == "hwp.exe"
            },
        }
    except Exception as exc:
        return {"status": "UNAVAILABLE", "pids": set(), "error": repr(exc)}


def _hwp_pids() -> set[int]:
    snapshot = _hwp_pid_snapshot()
    return set(snapshot.get("pids") or ())


def _approval_window_snapshot() -> dict[str, object]:
    try:
        import win32gui

        titles: list[str] = []

        def callback(hwnd: int, _extra: object) -> None:
            if not win32gui.IsWindowVisible(hwnd):
                return
            title = str(win32gui.GetWindowText(hwnd) or "").strip()
            if any(mark in title.casefold() for mark in ("접근 승인", "파일 접근", "file access", "approval")):
                titles.append(title)

        win32gui.EnumWindows(callback, None)
        return {"status": "OK", "titles": titles}
    except Exception as exc:
        # A failed window enumeration is not equivalent to zero approval
        # dialogs.  The caller must keep the run non-PASS in this state.
        return {"status": "UNAVAILABLE", "titles": [], "error": repr(exc)}


def _approval_windows() -> list[str]:
    snapshot = _approval_window_snapshot()
    return list(snapshot.get("titles") or ())


def _quit(hwp: object) -> None:
    try:
        hwp.quit(save=False)
    except Exception:
        pass


def _wait_for_new_pids_to_exit(pids: set[int], timeout: float = 20.0) -> tuple[set[int], str]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        snapshot = _hwp_pid_snapshot()
        if snapshot.get("status") != "OK":
            return set(pids), str(snapshot.get("status"))
        alive = set(snapshot.get("pids") or ()) & pids
        if not alive:
            return set(), "OK"
        time.sleep(0.25)
    snapshot = _hwp_pid_snapshot()
    if snapshot.get("status") != "OK":
        return set(pids), str(snapshot.get("status"))
    return set(snapshot.get("pids") or ()) & pids, "OK"


def _one_document(root: Path, label: str) -> dict[str, object]:
    before_pids = _hwp_pids()
    pid_statuses = [_hwp_pid_snapshot()]
    approval_before_snapshot = _approval_window_snapshot()
    hwp = create_secure_hwp(new=True, visible=False, on_quit=False)
    activation_returns = [getattr(getattr(hwp, "_hwp_security_registration", None), "returned", None)]
    created_pids = _hwp_pids() - before_pids
    pid_statuses.append(_hwp_pid_snapshot())
    stem = root / label
    files = {
        "hwp": stem.with_suffix(".hwp"),
        "hwpx": stem.with_suffix(".hwpx"),
        "pdf": stem.with_suffix(".pdf"),
    }
    try:
        if not hwp.insert_text(f"HWP security serial probe: {label}"):
            raise RuntimeError("insert_text returned False")
        for fmt, path in files.items():
            if not hwp.save_as(str(path), format=fmt.upper()):
                raise RuntimeError(f"save_as returned False: {fmt}")
        _quit(hwp)
        hwp = None
        reopened = create_secure_hwp(new=True, visible=False, on_quit=False)
        created_pids |= _hwp_pids() - before_pids
        pid_statuses.append(_hwp_pid_snapshot())
        activation_returns.append(
            getattr(getattr(reopened, "_hwp_security_registration", None), "returned", None)
        )
        try:
            if not reopened.open(str(files["hwp"]), format="HWP", arg="forceopen:true;suspendpassword:true"):
                raise RuntimeError("HWP reopen returned False")
            if not reopened.open(str(files["hwpx"]), format="HWPX", arg="forceopen:true;suspendpassword:true"):
                raise RuntimeError("HWPX reopen returned False")
        finally:
            _quit(reopened)
        approval_after_snapshot = _approval_window_snapshot()
        pid_statuses.append(_hwp_pid_snapshot())
        alive_after_quit, pid_wait_status = _wait_for_new_pids_to_exit(created_pids)
        return {
            "label": label,
            "files": {key: str(value) for key, value in files.items()},
            "exists": {key: value.is_file() for key, value in files.items()},
            "approval_windows_before": list(approval_before_snapshot.get("titles") or ()),
            "approval_windows_after": list(approval_after_snapshot.get("titles") or ()),
            "approval_window_status_before": approval_before_snapshot.get("status"),
            "approval_window_status_after": approval_after_snapshot.get("status"),
            "approval_window_error_before": approval_before_snapshot.get("error"),
            "approval_window_error_after": approval_after_snapshot.get("error"),
            "new_hwp_pids": sorted(created_pids),
            "new_hwp_pids_alive_after_quit": sorted(alive_after_quit),
            "pid_wait_status": pid_wait_status,
            "pid_enumeration_statuses": [snapshot.get("status") for snapshot in pid_statuses],
            "pid_enumeration_ok": (
                pid_wait_status == "OK"
                and all(snapshot.get("status") == "OK" for snapshot in pid_statuses)
            ),
            "register_module_return_values": activation_returns,
        }
    finally:
        if hwp is not None:
            _quit(hwp)


def main() -> int:
    if os.name != "nt":
        print(json.dumps({"status": "SKIP_NON_WINDOWS"}, ensure_ascii=False, indent=2))
        return 0
    workspace = Path(__file__).resolve().parents[3]
    out = workspace / f"work/hwp_security_probe_{uuid.uuid4().hex}"
    out.mkdir(parents=True, exist_ok=False)
    report: dict[str, object] = {
        "status": "FAIL",
        "output_dir": str(out),
        "security": security_snapshot(),
        "documents": [],
        "approval_window_count": 0,
    }
    try:
        if not report["security"].get("registration_valid", False):  # type: ignore[union-attr]
            report["failure_code"] = "HWP_SECURITY_MODULE_NOT_ACTIVE"
            raise RuntimeError(str(report["security"].get("register_module_error")))  # type: ignore[union-attr]
        documents = [_one_document(out, "serial-a"), _one_document(out, "serial-b")]
        report["documents"] = documents
        if any(row.get("approval_window_status_before") != "OK" or row.get("approval_window_status_after") != "OK" for row in documents):
            report["failure_code"] = "WINDOW_ENUMERATION_UNAVAILABLE"
            raise RuntimeError("approval window enumeration unavailable")
        if any(not row.get("pid_enumeration_ok", False) for row in documents):
            report["failure_code"] = "HWP_PID_ENUMERATION_UNAVAILABLE"
            raise RuntimeError("HWP PID enumeration unavailable")
        all_windows = [
            title
            for row in documents
            for title in row.get("approval_windows_after", [])  # type: ignore[union-attr]
        ]
        report["approval_window_count"] = len(all_windows)
        if len(documents) != 2 or report["approval_window_count"] != 0:
            report["failure_code"] = "HWP_APPROVAL_WINDOW_DETECTED"
            raise RuntimeError("approval window observed")
        if any(not all(row["exists"].values()) for row in documents):  # type: ignore[union-attr]
            report["failure_code"] = "HWP_SERIAL_OUTPUT_MISSING"
            raise RuntimeError("one or more output files missing")
        if any(row["new_hwp_pids_alive_after_quit"] for row in documents):  # type: ignore[union-attr]
            report["failure_code"] = "HWP_COM_PROCESS_NOT_EXITED"
            raise RuntimeError("new COM process did not exit within bounded wait")
        report["status"] = "PASS"
    except Exception as exc:
        report["error"] = repr(exc)
    (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
