"""One bounded normal-Quit recovery for an already-cleared owned COM session.

Never kills a process or saves an unnamed document. The caller must supervise
COM deadlines externally and confirm PID exit separately.
"""
import time


def quit_owned(hwp, *, expected_pid, pid_for_window, pause=time.sleep):
    try:
        hwp.quit(save=False)
        return {"normal_quit": True, "recovered_busy": False}
    except Exception as exc:
        if getattr(exc, "hresult", None) not in (-2147417846, -2147418111):
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
    return {"normal_quit": True, "recovered_busy": True, "paths": paths}
