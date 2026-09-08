"""Keep pyhwpx finalizers outside a supervised multi-session COM operation.

This does not close documents, initialize COM, or stop any process. pyhwpx's
wrapper destructor calls CoUninitialize, so dropping a previous wrapper during
new-session assignment can affect apartment lifetime. Explicit release requires
the caller's independent PID-exit confirmation.
"""


class HwpSessionReferences:
    def __init__(self):
        self._references = []
        self._released = False

    def retain(self, wrapper):
        if self._released:
            raise RuntimeError("HWP_SESSION_REFERENCES_ALREADY_RELEASED")
        self._references.append(wrapper)
        return wrapper

    def release_after_exit(self, all_owned_exited):
        if all_owned_exited() is not True:
            raise RuntimeError("HWP_SESSION_REFERENCES_PRESERVE_LIVE")
        self._references.clear()
        self._released = True
