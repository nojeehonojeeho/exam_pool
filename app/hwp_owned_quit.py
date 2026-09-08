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
