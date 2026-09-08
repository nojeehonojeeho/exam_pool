import unittest
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch

from app.integrations import hwp_security


class TestHwpSecurity(unittest.TestCase):
    def _registration(self):
        return hwp_security.ModuleRegistration(
            module_id="FilePathCheckerModule",
            key_path=hwp_security.PRIMARY_KEY_PATH,
            dll_path="C:/approved/FilePathCheckerModule.dll",
            registry_type=1,
            sha256="A" * 64,
            machine="x86",
            pe_format="PE32",
        )

    def test_register_module_return_value_is_required(self):
        class Stub:
            def __init__(self, result):
                self.result = result
                self.calls = []

            def RegisterModule(self, **kwargs):
                self.calls.append(kwargs)
                return self.result

        stub = Stub(True)
        result = hwp_security.activate_registered_module(
            stub,
            registration=self._registration(),
        )
        self.assertTrue(result.returned)
        self.assertEqual(stub.calls, [{"ModuleType": "FilePathCheckDLL", "ModuleData": "FilePathCheckerModule"}])

    def test_register_module_false_fails_closed(self):
        class Stub:
            def RegisterModule(self, **kwargs):
                return False

        with self.assertRaises(hwp_security.HwpSecurityError) as context:
            hwp_security.activate_registered_module(
                Stub(),
                registration=self._registration(),
            )
        self.assertEqual(context.exception.code, "HWP_SECURITY_MODULE_NOT_ACTIVE")

    def test_frozen_app_uses_bundled_path_checker(self):
        with TemporaryDirectory() as temporary:
            install = Path(temporary)
            executable = install / "ExamPoolHwpConverter.exe"
            checker = install / "pyhwpx" / "FilePathCheckerModule.dll"
            checker.parent.mkdir()
            checker.write_bytes(b"bundled-checker")

            with patch.object(sys, "frozen", True, create=True), \
                 patch.object(sys, "executable", str(executable)):
                resolved = hwp_security.checker_dll()

        self.assertEqual(resolved, checker)

    def test_non_windows_needs_no_registration(self):
        with patch.object(hwp_security.os, "name", "posix"):
            self.assertTrue(hwp_security.registration_valid())
            ok, _ = hwp_security.ensure_registration()
        self.assertTrue(ok)

    def test_missing_dll_is_reported(self):
        with patch.object(hwp_security.os, "name", "nt"), \
             patch.object(hwp_security, "checker_dll", return_value=None):
            ok, message = hwp_security.ensure_registration()
        self.assertFalse(ok)
        self.assertIn("FilePathCheckerModule.dll", message)

    def test_launcher_runs_security_preflight(self):
        launcher = Path(__file__).resolve().parents[1] / "run.bat"
        text = launcher.read_text(encoding="utf-8", errors="replace")
        self.assertIn("python -m app.integrations.hwp_security", text)
        self.assertIn("if errorlevel 1", text)


if __name__ == "__main__":
    unittest.main()
