"""Install and verify Hancom's FilePathCheckerModule for HWP automation.

Registration belongs to ExamPool startup. Preview workers may be restricted and
must not depend on being able to edit the current user's registry themselves.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import hashlib
import importlib.util
import os
from pathlib import Path
import struct
import sys
from typing import Any


MODULE_TYPE = "FilePathCheckDLL"
VALUE_NAME = "FilePathCheckerModule"
PRIMARY_KEY_PATH = r"Software\HNC\HwpAutomation\Modules"
LEGACY_KEY_PATH = r"Software\Hnc\HwpUserAction\Modules"
KEY_PATHS = (PRIMARY_KEY_PATH, LEGACY_KEY_PATH)
HWP_DEFAULT_EXE = r"C:\Program Files (x86)\Hnc\Office 2024\HOffice130\Bin\Hwp.exe"


class HwpSecurityError(RuntimeError):
    """Bounded failure for an inactive/invalid Hanword automation module."""

    code = "HWP_SECURITY_MODULE_NOT_ACTIVE"

    def __init__(self, message: str, *, details: dict[str, Any] | None = None):
        self.details = details or {}
        super().__init__(f"{self.code}: {message}")


@dataclass(frozen=True)
class ModuleRegistration:
    module_id: str
    key_path: str
    dll_path: str
    registry_type: int | None
    sha256: str
    machine: str
    pe_format: str


@dataclass(frozen=True)
class RegisterModuleResult:
    module_id: str
    module_type: str
    registration: ModuleRegistration
    returned: Any


def _read_pe_metadata(path: Path) -> tuple[str, str]:
    """Return (machine, PE format) without loading an untrusted DLL."""
    data = path.read_bytes()
    if len(data) < 0x40 or data[:2] != b"MZ":
        raise ValueError(f"not a PE image: {path}")
    pe_offset = struct.unpack_from("<I", data, 0x3C)[0]
    if pe_offset + 26 > len(data) or data[pe_offset:pe_offset + 4] != b"PE\0\0":
        raise ValueError(f"invalid PE header: {path}")
    machine_code = struct.unpack_from("<H", data, pe_offset + 4)[0]
    optional_magic = struct.unpack_from("<H", data, pe_offset + 24)[0]
    machine = {0x014C: "x86", 0x8664: "x64", 0xAA64: "ARM64"}.get(
        machine_code, f"0x{machine_code:04X}"
    )
    pe_format = {0x010B: "PE32", 0x020B: "PE32+"}.get(
        optional_magic, f"0x{optional_magic:04X}"
    )
    return machine, pe_format


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def hwp_executable() -> Path:
    return Path(os.environ.get("PYHWPX_HWP_EXE", HWP_DEFAULT_EXE))


def checker_dll() -> Path | None:
    override = os.environ.get("HWP_FILEPATHCHECK_DLL")
    if override:
        path = Path(override).expanduser().resolve()
        return path if path.is_file() else None
    if getattr(sys, "frozen", False):
        bundled = Path(sys.executable).resolve().parent / "pyhwpx" / "FilePathCheckerModule.dll"
        if bundled.is_file():
            return bundled
    spec = importlib.util.find_spec("pyhwpx")
    if spec is None or spec.origin is None:
        return None
    path = Path(spec.origin).resolve().parent / "FilePathCheckerModule.dll"
    return path if path.is_file() else None


def _views(winreg) -> tuple[int, ...]:
    return tuple(dict.fromkeys((0, winreg.KEY_WOW64_32KEY, winreg.KEY_WOW64_64KEY)))


def _registry_value(module_id: str = VALUE_NAME, *, key_path: str = PRIMARY_KEY_PATH) -> tuple[str, int] | None:
    """Read one module value from the current user's registry, across WOW64 views."""
    if os.name != "nt":
        return None
    try:
        import winreg
        for view in _views(winreg):
            try:
                with winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER,
                    key_path,
                    0,
                    winreg.KEY_QUERY_VALUE | view,
                ) as key:
                    value, regtype = winreg.QueryValueEx(key, module_id)
                if value:
                    return str(value), int(regtype)
            except OSError:
                continue
    except (ImportError, OSError):
        return None
    return None


def registration_valid(module_id: str = VALUE_NAME) -> bool:
    if os.name != "nt":
        return True
    dll = checker_dll()
    if dll is None:
        return False
    try:
        registration = resolve_registration(module_id)
    except HwpSecurityError:
        return False
    # Multiple local pyhwpx bundles can legitimately contain the same official
    # module.  A path-only comparison would report a false negative when the
    # running interpreter resolves the package from a different bundle.
    try:
        return registration.sha256 == _sha256(dll)
    except OSError:
        return False


def resolve_registration(
    module_id: str = VALUE_NAME,
    *,
    key_path: str = PRIMARY_KEY_PATH,
    hwp_exe: Path | None = None,
    require_matching_bitness: bool = True,
) -> ModuleRegistration:
    """Validate the registered DLL before any HWP file operation."""
    if os.name != "nt":
        raise HwpSecurityError("HWP COM security is Windows-only")
    value = _registry_value(module_id, key_path=key_path)
    if value is None:
        raise HwpSecurityError(
            f"registry value missing: HKCU\\{key_path}\\{module_id}",
            details={"registry_key_path": key_path, "module_id": module_id},
        )
    dll_path, regtype = value
    path = Path(dll_path).expanduser().resolve()
    if not path.is_file():
        raise HwpSecurityError("registered DLL does not exist", details={"dll_path": str(path)})
    if regtype is not None:
        try:
            import winreg
            if regtype != winreg.REG_SZ:
                raise HwpSecurityError("registry value is not REG_SZ", details={"registry_type": regtype})
        except ImportError:
            pass
    try:
        dll_machine, dll_format = _read_pe_metadata(path)
    except (OSError, ValueError) as exc:
        raise HwpSecurityError(str(exc), details={"dll_path": str(path)}) from exc
    target = (hwp_exe or hwp_executable()).expanduser().resolve()
    hwp_machine = "unknown"
    hwp_format = "unknown"
    if target.is_file():
        try:
            hwp_machine, hwp_format = _read_pe_metadata(target)
        except (OSError, ValueError):
            pass
    if require_matching_bitness and target.is_file() and hwp_machine != dll_machine:
        raise HwpSecurityError(
            f"DLL/Hwp.exe bitness mismatch: {dll_machine} vs {hwp_machine}",
            details={"dll_machine": dll_machine, "hwp_machine": hwp_machine},
        )
    return ModuleRegistration(
        module_id=module_id,
        key_path=key_path,
        dll_path=str(path),
        registry_type=regtype,
        sha256=_sha256(path),
        machine=dll_machine,
        pe_format=dll_format,
    )


def activate_registered_module(
    hwp: Any,
    *,
    module_id: str = VALUE_NAME,
    module_type: str = MODULE_TYPE,
    registration: ModuleRegistration | None = None,
) -> RegisterModuleResult:
    """Call the real HwpObject.RegisterModule and fail closed on False."""
    registration = registration or resolve_registration(module_id)
    method = getattr(hwp, "RegisterModule", None)
    if method is None:
        raise HwpSecurityError("HwpObject.RegisterModule is unavailable")
    try:
        returned = method(ModuleType=module_type, ModuleData=module_id)
    except TypeError:
        returned = method(module_type, module_id)
    if not bool(returned):
        raise HwpSecurityError(
            "RegisterModule returned False",
            details={"module_id": module_id, "returned": returned},
        )
    return RegisterModuleResult(module_id, module_type, registration, returned)


def create_secure_hwp(*, new: bool = True, visible: bool = False, on_quit: bool = False, **kwargs: Any) -> Any:
    """Construct pyhwpx.Hwp with explicit registration before Open/SaveAs/Print."""
    from pyhwpx import Hwp

    kwargs.pop("register_module", None)
    hwp = Hwp(new=new, visible=visible, register_module=False, on_quit=on_quit, **kwargs)
    try:
        result = activate_registered_module(hwp)
        # Keep the auditable return value on the wrapper without changing the
        # pyhwpx public API used by existing writers.
        setattr(hwp, "_hwp_security_registration", result)
    except Exception:
        try:
            hwp.quit(save=False)
        except Exception:
            pass
        raise
    return hwp


def security_snapshot(module_id: str = VALUE_NAME) -> dict[str, Any]:
    """Return an auditable, non-sensitive configuration snapshot."""
    registration = None
    error = None
    try:
        registration = resolve_registration(module_id)
    except Exception as exc:
        error = str(exc)
    snapshot: dict[str, Any] = {
        "registry_key_path": PRIMARY_KEY_PATH,
        "module_id": module_id,
        "hwp_executable": str(hwp_executable()),
        "registration_valid": registration is not None,
        "register_module_error": error,
    }
    if registration is not None:
        snapshot.update(asdict(registration))
    return snapshot


def ensure_registration() -> tuple[bool, str]:
    if os.name != "nt":
        return True, "Windows가 아니므로 HWP 보안 모듈 등록을 건너뜁니다."
    dll = checker_dll()
    if dll is None:
        return False, "pyhwpx의 FilePathCheckerModule.dll을 찾지 못했습니다."
    if registration_valid():
        return True, f"HWP 보안 모듈 등록 확인: {dll}"
    try:
        import winreg

        for key_path in KEY_PATHS:
            for view in _views(winreg):
                with winreg.CreateKeyEx(
                    winreg.HKEY_CURRENT_USER, key_path, 0,
                    winreg.KEY_SET_VALUE | view,
                ) as key:
                    winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, str(dll))
    except (ImportError, OSError) as exc:
        return False, (
            "HWP 파일 경로 승인 모듈을 현재 사용자 레지스트리에 등록하지 "
            f"못했습니다: {exc}"
        )
    if not registration_valid():
        return False, "HWP 보안 모듈을 기록했지만 등록 값을 다시 확인하지 못했습니다."
    return True, f"HWP 보안 모듈 등록 완료: {dll}"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="등록 여부만 확인")
    parser.add_argument("--snapshot", action="store_true", help="검증된 보안 설정을 JSON으로 출력")
    args = parser.parse_args(argv)
    if args.snapshot:
        import json
        snapshot = security_snapshot()
        print(json.dumps(snapshot, ensure_ascii=False, indent=2))
        ok = bool(snapshot.get("registration_valid"))
        message = "HWP 보안 모듈 스냅샷 정상" if ok else "HWP 보안 모듈 스냅샷 실패"
    elif args.check:
        ok = registration_valid()
        message = "HWP 보안 모듈 등록 정상" if ok else "HWP 보안 모듈 등록 필요"
    else:
        ok, message = ensure_registration()
    print(message, file=sys.stdout if ok else sys.stderr)
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
