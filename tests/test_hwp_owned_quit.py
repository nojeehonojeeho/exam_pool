from types import SimpleNamespace as NS
import pytest
from app.hwp_owned_quit import quit_owned

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
