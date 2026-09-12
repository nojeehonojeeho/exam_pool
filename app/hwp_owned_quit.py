"""One bounded normal-Quit recovery for an already-cleared owned COM session.

Never kills a process or saves an unnamed document. The caller must supervise
COM deadlines externally and confirm PID exit separately.
"""
import time
import math


class OwnedQuitError(RuntimeError):
    """A bounded, auditable failure while closing an owned HWP session."""

    def __init__(self, code, message, *, record=None):
        self.code = code
        self.record = record or {}
        super().__init__(f"{code}: {message}")


def quit_tracked_with_safe_fallback(hwp, *, tracked):
    """Close a *proven* HWP session without touching unknown HWP processes.

    ``pyhwpx.Hwp.quit(save=False)`` normally closes the wrapper and its raw
    ``HwpObject``.  Some COM error paths raise from the wrapper's ``Clear``
    even though the raw object is still a clean, unnamed session.  Only in
    that narrowly safe case do we call raw ``hwp.hwp.Quit()``: the caller must
    provide at least one PID+creation-time identity observed after this
    session was created, and the raw object must report ``IsModified=False``.
    The caller remains responsible for waiting for those exact identities to
    exit; this helper never kills or terminates a process.
    """
    identities = tuple(tracked or ())
    record = {
        "tracked_processes": [],
        "wrapper_quit_attempted": False,
        "wrapper_quit_succeeded": False,
        "wrapper_error": None,
        "raw_fallback_attempted": False,
        "raw_fallback_succeeded": False,
        "is_modified": None,
    }
    # Empty or malformed ownership evidence is checked before touching the
    # wrapper.  This is the important guard against closing a user's HWP.
    if not identities:
        raise OwnedQuitError(
            "HWP_COM_PROCESS_NOT_OBSERVED",
            "raw Quit fallback is forbidden without owned PID+creation-time evidence",
            record=record,
        )
    for identity in identities:
        try:
            pid = int(getattr(identity, "pid"))
            create_time = float(getattr(identity, "create_time"))
        except (AttributeError, TypeError, ValueError) as exc:
            raise OwnedQuitError(
                "HWP_COM_OWNERSHIP_EVIDENCE_INVALID",
                repr(exc),
                record=record,
            ) from exc
        record["tracked_processes"].append({"pid": pid, "create_time": create_time})
        if pid <= 0 or not math.isfinite(create_time):
            raise OwnedQuitError(
                "HWP_COM_OWNERSHIP_EVIDENCE_INVALID",
                "tracked identity must contain a positive PID and finite creation time",
                record=record,
            )

    record["wrapper_quit_attempted"] = True
    try:
        hwp.quit(save=False)
    except Exception as wrapper_error:
        record["wrapper_error"] = repr(wrapper_error)
        try:
            raw = getattr(hwp, "hwp")
        except Exception as exc:
            raise OwnedQuitError(
                "HWP_COM_RAW_QUIT_UNAVAILABLE",
                repr(exc),
                record=record,
            ) from wrapper_error
        if raw is None:
            raise OwnedQuitError(
                "HWP_COM_RAW_QUIT_UNAVAILABLE",
                "wrapper did not expose its raw HwpObject",
                record=record,
            ) from wrapper_error
        try:
            modified = getattr(raw, "IsModified")
            if callable(modified):
                modified = modified()
        except Exception as exc:
            raise OwnedQuitError(
                "HWP_COM_RAW_QUIT_MODIFIED_UNKNOWN",
                repr(exc),
                record=record,
            ) from wrapper_error
        # VARIANT_BOOL normally arrives as bool, but test doubles and some
        # COM bridges expose 0/1.  No other truthy value is accepted.
        if isinstance(modified, bool):
            is_modified = modified
        elif isinstance(modified, int) and modified in (0, 1):
            is_modified = bool(modified)
        else:
            raise OwnedQuitError(
                "HWP_COM_RAW_QUIT_MODIFIED_UNKNOWN",
                f"unexpected IsModified value: {modified!r}",
                record=record,
            ) from wrapper_error
        record["is_modified"] = is_modified
        if is_modified:
            raise OwnedQuitError(
                "HWP_COM_RAW_QUIT_UNSAFE_MODIFIED",
                "raw Quit is forbidden while the owned document is modified",
                record=record,
            ) from wrapper_error
        record["raw_fallback_attempted"] = True
        try:
            raw.Quit()
        except Exception as raw_error:
            record["raw_error"] = repr(raw_error)
            raise OwnedQuitError(
                "HWP_COM_RAW_QUIT_FAILED",
                repr(raw_error),
                record=record,
            ) from raw_error
        record["raw_fallback_succeeded"] = True
        return record
    record["wrapper_quit_succeeded"] = True
    return record


def quit_owned(hwp, *, expected_pid, pid_for_window, pause=time.sleep):
    try:
        hwp.quit(save=False)
        return {"normal_quit": True, "recovered_busy": False}
    except Exception as exc:
        initial_hresult=getattr(exc,"hresult",None)
        codes={getattr(exc,"hresult",None)}
        info=getattr(exc,"excepinfo",None)
        if isinstance(info,tuple) and len(info)>5:codes.add(info[5])
        if not codes.intersection((-2147417846, -2147418111, -2147417851)):
            raise
    pause(0.5)
    raw=hwp.hwp
    actual=pid_for_window(int(raw.XHwpWindows.Item(0).WindowHandle))
    if actual != expected_pid:
        raise RuntimeError("OWNED_QUIT_PID_MISMATCH")
    documents=raw.XHwpDocuments
    paths=[documents.Item(i).FullName for i in range(documents.Count)]
    if not paths or any(paths):
        raise RuntimeError("OWNED_QUIT_NOT_CLEARED_PRESERVE")
    raw.Quit()
    return {"normal_quit": True, "recovered_busy": bool(codes.intersection((-2147417846,-2147418111))),
            "recovered_server_fault": -2147417851 in codes,"initial_hresult":initial_hresult,"paths": paths}
