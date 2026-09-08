from unittest.mock import patch
from unittest.mock import Mock
from types import SimpleNamespace
import pytest

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


def test_preexisting_approval_prevents_new_com(tmp_path):
    with patch.object(probe, "_hwp_pids", return_value=set()), patch.object(
        probe, "_hwp_pid_snapshot", return_value={"status":"OK", "pids":set()}
    ), patch.object(probe, "_approval_window_snapshot", return_value={"status":"OK", "titles":["파일 접근 승인"]}), patch.object(probe, "create_secure_hwp") as create:
        with pytest.raises(RuntimeError, match="DETECTED_BEFORE_START"):
            probe._one_document(tmp_path,"blocked")
        create.assert_not_called()


def test_false_registration_prevents_file_access(tmp_path):
    hwp=Mock()
    hwp._hwp_security_registration=SimpleNamespace(returned=False)
    with patch.object(probe,"_hwp_pids",return_value=set()), patch.object(
        probe,"_hwp_pid_snapshot",return_value={"status":"OK","pids":set()}
    ), patch.object(probe,"_approval_window_snapshot",return_value={"status":"OK","titles":[]}), patch.object(probe,"create_secure_hwp",return_value=hwp):
        with pytest.raises(RuntimeError, match="HWP_SECURITY_MODULE_NOT_ACTIVE"):
            probe._one_document(tmp_path,"unregistered")
    hwp.insert_text.assert_not_called()
    hwp.save_as.assert_not_called()


def test_initial_pid_must_exit_before_reopen(tmp_path):
    hwp=Mock()
    hwp._hwp_security_registration=SimpleNamespace(returned=True)
    with patch.object(probe,"_hwp_pids",side_effect=[set(),{123}]), patch.object(
        probe,"_hwp_pid_snapshot",return_value={"status":"OK","pids":set()}
    ), patch.object(probe,"_approval_window_snapshot",return_value={"status":"OK","titles":[]}), patch.object(probe,"create_secure_hwp",return_value=hwp) as create, patch.object(probe,"_wait_for_new_pids_to_exit",return_value=({123},"OK")):
        with pytest.raises(RuntimeError, match="INITIAL_PROCESS_NOT_EXITED"):
            probe._one_document(tmp_path,"still-running")
        assert create.call_count == 1
