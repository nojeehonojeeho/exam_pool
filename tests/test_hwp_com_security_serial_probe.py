from unittest.mock import patch

from tools import hwp_com_security_serial_probe as probe


def test_pid_wait_does_not_treat_enumeration_failure_as_exit() -> None:
    with patch.object(
        probe,
        "_hwp_pid_snapshot",
        return_value={"status": "UNAVAILABLE", "pids": set(), "error": "test"},
    ):
        alive, status = probe._wait_for_new_pids_to_exit({1234}, timeout=0)
    assert alive == {1234}
    assert status == "UNAVAILABLE"


def test_approval_window_snapshot_has_explicit_unavailable_state() -> None:
    with patch.dict("sys.modules", {"win32gui": None}):
        snapshot = probe._approval_window_snapshot()
    assert snapshot["status"] == "UNAVAILABLE"
    assert snapshot["titles"] == []
