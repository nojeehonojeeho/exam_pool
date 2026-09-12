from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.hwp_process_lifecycle import (
    HwpProcessIdentity,
    HwpProcessSnapshot,
    newly_started_hwp_processes,
    snapshot_hwp_processes,
    wait_for_hwp_processes_to_exit,
)


class _PsutilStub:
    def __init__(self, processes):
        self.processes = processes

    def process_iter(self, _attrs):
        return iter(self.processes)


def _process(pid: int, name: str, create_time: float = 1.0):
    return SimpleNamespace(info={"pid": pid, "name": name, "create_time": create_time})


def test_snapshot_keeps_hwp_identity_and_ignores_unrelated_processes():
    snapshot = snapshot_hwp_processes(
        psutil_module=_PsutilStub(
            [_process(10, "Hwp.exe", 100.0), _process(11, "WINWORD.EXE", 200.0)]
        )
    )
    assert snapshot.status == "OK"
    assert snapshot.processes == frozenset({HwpProcessIdentity(pid=10, create_time=100.0)})


def test_snapshot_is_fail_closed_when_psutil_cannot_enumerate():
    class Broken:
        def process_iter(self, _attrs):
            raise RuntimeError("permission denied")

    snapshot = snapshot_hwp_processes(psutil_module=Broken())
    assert snapshot.status == "UNAVAILABLE"
    assert not snapshot.processes


def test_snapshot_is_fail_closed_when_psutil_is_missing(monkeypatch):
    real_import = __import__("builtins").__import__

    def missing_psutil(name, *args, **kwargs):
        if name == "psutil":
            raise ModuleNotFoundError("psutil intentionally unavailable")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", missing_psutil)
    snapshot = snapshot_hwp_processes()
    assert snapshot.status == "UNAVAILABLE"
    assert not snapshot.processes


def test_new_pid_delta_rejects_unavailable_inputs():
    before = HwpProcessSnapshot(status="UNAVAILABLE", error="missing psutil")
    after = HwpProcessSnapshot(status="OK")
    delta = newly_started_hwp_processes(before, after)
    assert delta.status == "UNAVAILABLE"
    assert not delta.processes


def test_wait_times_out_and_never_calls_a_kill_method():
    identity = HwpProcessIdentity(pid=10, create_time=100.0)
    snapshots = iter(
        [
            HwpProcessSnapshot(status="OK", processes=frozenset({identity})),
            HwpProcessSnapshot(status="OK", processes=frozenset({identity})),
        ]
    )
    clock = iter([0.0, 0.0, 1.0])
    result = wait_for_hwp_processes_to_exit(
        [identity], snapshot=lambda: next(snapshots), timeout=1.0, poll_interval=0.1,
        monotonic=lambda: next(clock), sleep=lambda _delay: None,
    )
    assert result.status == "TIMEOUT"
    assert result.remaining == frozenset({identity})


def test_wait_is_unavailable_not_success_when_enumerator_fails():
    identity = HwpProcessIdentity(pid=10, create_time=100.0)
    result = wait_for_hwp_processes_to_exit(
        [identity],
        snapshot=lambda: HwpProcessSnapshot(status="UNAVAILABLE", error="test"),
        timeout=0,
        monotonic=lambda: 0.0,
        sleep=lambda _delay: None,
    )
    assert result.status == "UNAVAILABLE"
    assert not result.exited


def test_wait_is_fail_closed_when_no_session_identity_was_observed():
    result = wait_for_hwp_processes_to_exit([], timeout=0)
    assert result.status == "UNAVAILABLE"
    assert not result.exited


def test_pid_reuse_does_not_keep_old_identity_alive():
    old = HwpProcessIdentity(pid=10, create_time=100.0)
    reused = HwpProcessIdentity(pid=10, create_time=200.0)
    result = wait_for_hwp_processes_to_exit(
        [old],
        snapshot=lambda: HwpProcessSnapshot(status="OK", processes=frozenset({reused})),
        timeout=0,
        monotonic=lambda: 0.0,
        sleep=lambda _delay: None,
    )
    assert result.exited


@pytest.mark.parametrize(
    "timeout,poll_interval",
    [
        (float("nan"), 0.25),
        (float("inf"), 0.25),
        (1.0, float("nan")),
        (1.0, float("inf")),
        (-1.0, 0.25),
        (1.0, -0.1),
    ],
)
def test_wait_rejects_non_finite_or_negative_parameters(timeout, poll_interval):
    identity = HwpProcessIdentity(pid=10, create_time=100.0)
    with pytest.raises(ValueError):
        wait_for_hwp_processes_to_exit(
            [identity], timeout=timeout, poll_interval=poll_interval
        )


def test_wait_rejects_zero_poll_interval_for_positive_timeout():
    identity = HwpProcessIdentity(pid=10, create_time=100.0)
    with pytest.raises(ValueError, match="poll_interval"):
        wait_for_hwp_processes_to_exit([identity], timeout=1.0, poll_interval=0)


def test_wait_allows_zero_timeout_for_one_immediate_observation():
    identity = HwpProcessIdentity(pid=10, create_time=100.0)
    result = wait_for_hwp_processes_to_exit(
        [identity],
        snapshot=lambda: HwpProcessSnapshot(status="OK", processes=frozenset({identity})),
        timeout=0,
        poll_interval=0,
        monotonic=lambda: 0.0,
        sleep=lambda _delay: pytest.fail("zero-timeout wait must not sleep"),
    )
    assert result.status == "TIMEOUT"


def test_wait_fails_closed_when_monotonic_clock_is_non_finite():
    identity = HwpProcessIdentity(pid=10, create_time=100.0)
    result = wait_for_hwp_processes_to_exit(
        [identity],
        snapshot=lambda: HwpProcessSnapshot(status="OK", processes=frozenset({identity})),
        timeout=1.0,
        poll_interval=0.1,
        monotonic=lambda: float("nan"),
        sleep=lambda _delay: pytest.fail("invalid clock must not sleep"),
    )
    assert result.status == "UNAVAILABLE"
    assert not result.exited


def test_wait_rejects_deadline_overflow():
    identity = HwpProcessIdentity(pid=10, create_time=100.0)
    with pytest.raises(ValueError, match="finite deadline"):
        wait_for_hwp_processes_to_exit(
            [identity],
            timeout=1e308,
            poll_interval=1.0,
            monotonic=lambda: 1e308,
        )
