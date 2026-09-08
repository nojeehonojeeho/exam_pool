"""Bounded readiness evidence for an owned HWP copy/move test.

This does not modify the clipboard, paste, or prove content fidelity. The
caller must supervise the worker process: Windows delayed rendering itself
can block inside GetClipboardData despite the polling deadline.
"""
import hashlib
import time


def wait_native_payload(clipboard, sequence_before, *, pump=lambda: None,
                        timeout=5.0, clock=time.monotonic, sleep=time.sleep):
    if not 0 < timeout <= 10:
        raise ValueError('native clipboard timeout must be in (0, 10]')
    deadline = clock() + timeout
    record = {'sequence_before': sequence_before, 'ready': False}
    while clock() < deadline:
        pump()
        opened = False
        try:
            clipboard.OpenClipboard()
            opened = True
            native = clipboard.RegisterClipboardFormat('Hwp Native')
            sequence = clipboard.GetClipboardSequenceNumber()
            if sequence != sequence_before and clipboard.IsClipboardFormatAvailable(native):
                payload = clipboard.GetClipboardData(native)
                if isinstance(payload, bytes) and payload:
                    record.update(ready=True, sequence_after=sequence,
                                  native_bytes=len(payload),
                                  native_sha256=hashlib.sha256(payload).hexdigest())
                    return record
        except Exception as exc:
            record['last_error'] = repr(exc)
        finally:
            if opened:
                clipboard.CloseClipboard()
        sleep(.1)
    return record
