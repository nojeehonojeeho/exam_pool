import hashlib
import pytest
from app.hwp_native_clipboard import wait_native_payload


class Clipboard:
    def __init__(self, seq=2, payload=b'synthetic native data', error=False):
        self.seq=seq;self.payload=payload;self.error=error;self.closed=0
    def OpenClipboard(self):pass
    def CloseClipboard(self):self.closed+=1
    def RegisterClipboardFormat(self, name):
        assert name=='Hwp Native'
        return 50000
    def GetClipboardSequenceNumber(self):return self.seq
    def IsClipboardFormatAvailable(self, fmt):return True
    def GetClipboardData(self, fmt):
        if self.error:raise RuntimeError('delayed render unavailable')
        return self.payload


def run(c):
    ticks=iter([0,.1,.2,.3,.4,6])
    return wait_native_payload(c,1,clock=lambda:next(ticks),sleep=lambda _:None)


def test_new_native_payload_hash_only():
    c=Clipboard();r=run(c)
    assert r['ready'] and c.closed==1
    assert r['native_sha256']==hashlib.sha256(c.payload).hexdigest()
    assert 'payload' not in r


@pytest.mark.parametrize('kwargs',[{'seq':1},{'payload':b''},{'payload':'plain text'},{'error':True}])
def test_stale_empty_non_native_or_unavailable_data_cannot_pass(kwargs):
    c=Clipboard(**kwargs);r=run(c)
    assert not r['ready'] and c.closed==4


def test_invalid_timeout_fails_before_clipboard_access():
    with pytest.raises(ValueError):wait_native_payload(None,0,timeout=0)
