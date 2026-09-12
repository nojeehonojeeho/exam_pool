from __future__ import annotations

from types import SimpleNamespace

import pytest

import tools.hwp_native_endnote_transfer_probe as probe
from app.hwp_process_lifecycle import HwpProcessIdentity, HwpProcessSnapshot, HwpProcessWait


IDENTITY = HwpProcessIdentity(pid=4321, create_time=123.0)


def _tracking() -> dict[str, object]:
    return {
        "tracked": frozenset({IDENTITY}),
        "lifecycle": {"before_start": {}, "after_start": {}, "delta": {}},
    }


def _stub_clean_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    snapshot = HwpProcessSnapshot(status="OK", processes=frozenset())
    monkeypatch.setattr(probe, "_require_hwp_process_snapshot", lambda: snapshot)
    monkeypatch.setattr(
        probe,
        "wait_for_hwp_processes_to_exit",
        lambda tracked: HwpProcessWait(status="OK", tracked=frozenset(tracked)),
    )


def test_wrapper_quit_error_uses_raw_quit_for_known_unmodified_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_clean_exit(monkeypatch)

    class Raw:
        IsModified = False

        def __init__(self) -> None:
            self.quit_calls = 0

        def Quit(self) -> None:
            self.quit_calls += 1

    raw = Raw()

    class Wrapper:
        hwp = raw

        def quit(self, *, save: bool) -> None:
            assert save is False
            raise RuntimeError("pyhwpx Clear failed")

    tracking = _tracking()
    result = probe._quit_tracked_hwp(Wrapper(), tracking)

    assert result.exited
    assert raw.quit_calls == 1
    assert tracking["lifecycle"]["quit"] == {
        "wrapper_attempted": True,
        "wrapper_succeeded": False,
        "wrapper_error": "RuntimeError('pyhwpx Clear failed')",
        "raw_attempted": True,
        "raw_succeeded": True,
        "raw_is_modified": False,
        "raw_error": None,
        "path": "raw_com_quit_after_wrapper_error",
    }


def test_wrapper_quit_error_does_not_raw_quit_modified_document(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_clean_exit(monkeypatch)

    class Raw:
        IsModified = True

        def __init__(self) -> None:
            self.quit_calls = 0

        def Quit(self) -> None:
            self.quit_calls += 1

    raw = Raw()

    class Wrapper:
        hwp = raw

        def quit(self, *, save: bool) -> None:
            raise RuntimeError("wrapper failed")

    tracking = _tracking()
    with pytest.raises(RuntimeError, match="HWP_COM_QUIT_FAILED"):
        probe._quit_tracked_hwp(Wrapper(), tracking)

    assert raw.quit_calls == 0
    quit_record = tracking["lifecycle"]["quit"]
    assert quit_record["raw_attempted"] is False
    assert quit_record["raw_succeeded"] is False
    assert quit_record["raw_is_modified"] is True
    assert quit_record["path"] is None


def test_wrapper_quit_error_records_raw_quit_error_and_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_clean_exit(monkeypatch)

    class Raw:
        IsModified = False

        def Quit(self) -> None:
            raise RuntimeError("raw Quit failed")

    class Wrapper:
        hwp = Raw()

        def quit(self, *, save: bool) -> None:
            raise RuntimeError("wrapper failed")

    tracking = _tracking()
    with pytest.raises(RuntimeError, match="HWP_COM_QUIT_FAILED"):
        probe._quit_tracked_hwp(Wrapper(), tracking)

    quit_record = tracking["lifecycle"]["quit"]
    assert quit_record["raw_attempted"] is True
    assert quit_record["raw_succeeded"] is False
    assert quit_record["raw_error"] == "RuntimeError('raw Quit failed')"


def test_unknown_session_is_rejected_before_any_quit_path() -> None:
    class Wrapper:
        def quit(self, *, save: bool) -> None:
            raise AssertionError("unknown wrapper must not be touched")

    with pytest.raises(RuntimeError, match="HWP_COM_QUIT_UNOWNED"):
        probe._quit_tracked_hwp(Wrapper(), {"tracked": frozenset(), "lifecycle": {}})


def test_selection_evidence_excludes_nested_endnote_body() -> None:
    xml = (
        '<hp:p xmlns:hp="urn:synthetic">'
        '<hp:run><hp:t>문제 본문</hp:t>'
        '<hp:ctrl><hp:endNote number="1"><hp:subList><hp:p>'
        '<hp:run><hp:t>정답 해설</hp:t><hp:equation/></hp:run>'
        '</hp:p></hp:subList></hp:endNote></hp:ctrl>'
        '<hp:t>선택지</hp:t><hp:equation/></hp:run>'
        '</hp:p>'
    )
    visible, equations, native_notes = probe._selection_visible_evidence(xml, "fallback")
    assert "문제 본문" in visible
    assert "선택지" in visible
    assert "정답 해설" not in visible
    assert equations == 1
    assert native_notes == 1
