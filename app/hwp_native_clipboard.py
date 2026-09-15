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
    # Keep a bounded diagnostic record even when delayed rendering never
    # produces a native payload.  A sequence change alone is deliberately not
    # considered success: another application can change the clipboard while
    # Hanword has not exposed the ``Hwp Native`` format.
    record = {
        'sequence_before': sequence_before,
        'native_format_name': 'Hwp Native',
        'ready': False,
        'poll_count': 0,
    }
    while clock() < deadline:
        pump()
        opened = False
        try:
            clipboard.OpenClipboard()
            opened = True
            native = clipboard.RegisterClipboardFormat('Hwp Native')
            sequence = clipboard.GetClipboardSequenceNumber()
            available = bool(clipboard.IsClipboardFormatAvailable(native))
            record.update(
                poll_count=record['poll_count'] + 1,
                sequence_after=sequence,
                native_format_id=native,
                native_format_available=available,
            )
            enum = getattr(clipboard, 'EnumClipboardFormats', None)
            if enum is not None:
                formats = []
                previous = 0
                try:
                    while True:
                        previous = enum(previous)
                        if not previous:
                            break
                        formats.append(int(previous))
                    record['available_format_ids'] = formats
                except Exception as exc:
                    record['format_enumeration_error'] = repr(exc)
            if sequence != sequence_before and available:
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
