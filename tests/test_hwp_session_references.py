import gc
import weakref
import pytest
from app.hwp_session_references import HwpSessionReferences


class Wrapper:
    pass


def test_previous_wrapper_survives_next_assignment_until_confirmed_exit():
    refs=HwpSessionReferences()
    wrapper=refs.retain(Wrapper());previous=weakref.ref(wrapper)
    wrapper=refs.retain(Wrapper())
    gc.collect()
    assert previous() is not None
    with pytest.raises(RuntimeError,match="PRESERVE_LIVE"):
        refs.release_after_exit(lambda:False)
    gc.collect()
    assert previous() is not None
    refs.release_after_exit(lambda:True)
    gc.collect()
    assert previous() is None
    with pytest.raises(RuntimeError,match="ALREADY_RELEASED"):
        refs.retain(Wrapper())


def test_unknown_exit_state_is_not_success():
    refs=HwpSessionReferences()
    with pytest.raises(RuntimeError,match="PRESERVE_LIVE"):
        refs.release_after_exit(lambda:None)
