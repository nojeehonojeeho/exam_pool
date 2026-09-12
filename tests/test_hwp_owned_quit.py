from types import SimpleNamespace as NS
import pytest
from app.hwp_owned_quit import (
    OwnedQuitError,
    quit_owned,
    quit_tracked_with_safe_fallback,
)
from app.hwp_process_lifecycle import HwpProcessIdentity

class Busy(Exception):
    hresult=-2147417846

def session(path="",pid=10):
    calls=[]
    def quit(**kw):raise Busy()
    raw=NS(XHwpWindows=NS(Item=lambda i:NS(WindowHandle=99)),
           XHwpDocuments=NS(Count=1,Item=lambda i:NS(FullName=path)),Quit=lambda:calls.append("Quit"))
    return NS(quit=quit,hwp=raw),calls

def test_recovery_is_one_normal_quit_for_cleared_owned_session():
    h,c=session()
    assert quit_owned(h,expected_pid=10,pid_for_window=lambda _:10,pause=lambda _:None)["recovered_busy"]
    assert c==["Quit"]

@pytest.mark.parametrize("path,pid",[("",11),("saved-or-user-document.hwp",10)])
def test_preserves_unowned_or_uncleared_session(path,pid):
    h,c=session(path)
    with pytest.raises(RuntimeError):quit_owned(h,expected_pid=10,pid_for_window=lambda _:pid,pause=lambda _:None)
    assert not c

def test_wrapped_rpc_busy_is_recovered_only_for_cleared_owned_session():
    h,c=session()
    class Wrapped(Exception):
        hresult=-2147352567
        excepinfo=(0,'server','busy',None,0,-2147417846)
    def quit(**kw):raise Wrapped()
    h.quit=quit
    assert quit_owned(h,expected_pid=10,pid_for_window=lambda _:10,pause=lambda _:None)['recovered_busy']
    assert c==['Quit']

def test_server_fault_is_not_misreported_as_busy():
    h,c=session()
    class Fault(Exception):hresult=-2147417851
    def quit(**kw):raise Fault()
    h.quit=quit
    result=quit_owned(h,expected_pid=10,pid_for_window=lambda _:10,pause=lambda _:None)
    assert result['recovered_server_fault'] and not result['recovered_busy']
    assert c==['Quit']


def test_tracked_fallback_uses_raw_quit_only_for_unmodified_owned_session():
    calls = []

    class WrapperError(Exception):
        pass

    class Raw:
        IsModified = False

        def Quit(self):
            calls.append("raw.Quit")

    class Wrapper:
        hwp = Raw()

        def quit(self, *, save=False):
            assert save is False
            raise WrapperError("Clear failed")

    identity = HwpProcessIdentity(pid=42, create_time=123.5)
    record = quit_tracked_with_safe_fallback(Wrapper(), tracked={identity})

    assert record["wrapper_quit_succeeded"] is False
    assert record["wrapper_error"] == "WrapperError('Clear failed')"
    assert record["is_modified"] is False
    assert record["raw_fallback_attempted"] is True
    assert record["raw_fallback_succeeded"] is True
    assert calls == ["raw.Quit"]


def test_tracked_fallback_refuses_modified_session_and_does_not_raw_quit():
    calls = []

    class Raw:
        IsModified = True

        def Quit(self):
            calls.append("raw.Quit")

    class Wrapper:
        hwp = Raw()

        def quit(self, *, save=False):
            raise RuntimeError("Clear failed")

    identity = HwpProcessIdentity(pid=43, create_time=123.6)
    with pytest.raises(OwnedQuitError, match="HWP_COM_RAW_QUIT_UNSAFE_MODIFIED"):
        quit_tracked_with_safe_fallback(Wrapper(), tracked={identity})

    assert calls == []


def test_tracked_fallback_never_touches_unknown_session():
    calls = []

    class Raw:
        IsModified = False

        def Quit(self):
            calls.append("raw.Quit")

    class Wrapper:
        hwp = Raw()

        def quit(self, *, save=False):
            calls.append("wrapper.quit")
            raise RuntimeError("Clear failed")

    with pytest.raises(OwnedQuitError, match="HWP_COM_PROCESS_NOT_OBSERVED"):
        quit_tracked_with_safe_fallback(Wrapper(), tracked=())

    assert calls == []
