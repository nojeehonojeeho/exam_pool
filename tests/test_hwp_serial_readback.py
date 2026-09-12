from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from app.hwp_process_lifecycle import HwpProcessIdentity, HwpProcessSnapshot, HwpProcessWait
from tools import hwp_serial_readback as readback


def test_validate_paths_requires_editable_derived_output(tmp_path: Path) -> None:
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    source = source_dir / "paper.hwpx"
    source.write_bytes(b"source")
    with pytest.raises(readback.HwpReadbackError, match="EDITABLE_OUTPUT_REQUIRED"):
        readback.validate_paths(source, output_pdf=tmp_path / "work" / "paper.pdf")


def test_validate_paths_rejects_source_directory_and_existing_targets(tmp_path: Path) -> None:
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    source = source_dir / "paper.hwpx"
    source.write_bytes(b"source")
    with pytest.raises(readback.HwpReadbackError, match="SOURCE_DIRECTORY_OUTPUT_BLOCKED"):
        readback.validate_paths(source, output_hwpx=source_dir / "derived.hwpx")
    existing = tmp_path / "work" / "derived.hwpx"
    existing.parent.mkdir()
    existing.write_bytes(b"keep")
    with pytest.raises(readback.HwpReadbackError, match="OUTPUT_EXISTS"):
        readback.validate_paths(source, output_hwpx=existing)


class _FakeHwp:
    def __init__(self) -> None:
        self._hwp_security_registration = type("Registration", (), {"returned": True})()

    def open(self, _path: str, *, format: str, arg: str) -> bool:
        assert format in {"HWP", "HWPX"}
        assert "forceopen:true" in arg
        return True

    def save_as(self, path: str, *, format: str) -> bool:
        suffix = {"HWP": ".hwp", "HWPX": ".hwpx", "PDF": ".pdf"}[format]
        assert Path(path).suffix.casefold() == suffix
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_bytes(f"derived-{format}".encode("ascii"))
        return True

    def quit(self, *, save: bool = False) -> None:
        assert save is False


def test_run_readback_is_serial_and_uses_two_owned_sessions(tmp_path: Path) -> None:
    source_dir = tmp_path / "source"
    work_dir = tmp_path / "work"
    source_dir.mkdir()
    source = source_dir / "paper.hwpx"
    source.write_bytes(b"source")
    output_hwp = work_dir / "paper.hwp"
    output_hwpx = work_dir / "paper.hwpx"
    output_pdf = work_dir / "paper.pdf"
    readback_hwpx = work_dir / "paper.readback.hwpx"
    report = work_dir / "report.json"

    first = HwpProcessIdentity(100, 1.0)
    second = HwpProcessIdentity(200, 2.0)
    snapshots = iter(
        [
            HwpProcessSnapshot(status="OK"),
            HwpProcessSnapshot(status="OK", processes=frozenset({first})),
            HwpProcessSnapshot(status="OK", processes=frozenset({first})),
            HwpProcessSnapshot(status="OK"),
            HwpProcessSnapshot(status="OK", processes=frozenset({second})),
            HwpProcessSnapshot(status="OK", processes=frozenset({second})),
        ]
    )
    factories: list[_FakeHwp] = []

    def factory(**_kwargs: object) -> _FakeHwp:
        session = _FakeHwp()
        factories.append(session)
        return session

    def wait_fn(tracked, **_kwargs) -> HwpProcessWait:
        return HwpProcessWait(status="OK", tracked=frozenset(tracked))

    result = readback.run_readback(
        source,
        output_hwp=output_hwp,
        output_hwpx=output_hwpx,
        output_pdf=output_pdf,
        readback_hwpx=readback_hwpx,
        report=report,
        factory=factory,
        snapshot_fn=lambda: next(snapshots),
        wait_fn=wait_fn,
    )

    assert result["status"] == "PASS"
    assert len(factories) == 2
    assert [row["delta"]["pids"] for row in result["lifecycle"]] == [[100], [200]]
    assert all(path.is_file() for path in (output_hwp, output_hwpx, output_pdf, readback_hwpx, report))
    assert result["input_sha256_before"] == result["input_sha256_after"]


def test_run_readback_fails_closed_when_creation_does_not_produce_new_identity(tmp_path: Path) -> None:
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    source = source_dir / "paper.hwp"
    source.write_bytes(b"source")
    snapshots = iter(
        [
            HwpProcessSnapshot(status="OK"),
            HwpProcessSnapshot(status="OK"),
        ]
    )

    result = readback.run_readback(
        source,
        output_hwp=tmp_path / "work" / "paper.hwp",
        report=tmp_path / "work" / "report.json",
        factory=lambda **_kwargs: _FakeHwp(),
        snapshot_fn=lambda: next(snapshots),
        wait_fn=lambda *_args, **_kwargs: pytest.fail("no wait for unowned session"),
    )

    assert result["status"] == "FAIL"
    assert any(error["code"] == "HWP_COM_PROCESS_NOT_OBSERVED" for error in result["errors"])


def test_run_readback_does_not_infer_zero_approval_windows_when_enumeration_unavailable(tmp_path: Path) -> None:
    source_dir = tmp_path / "source"
    work_dir = tmp_path / "work"
    source_dir.mkdir()
    source = source_dir / "paper.hwpx"
    source.write_bytes(b"source")
    snapshots = iter(
        [
            HwpProcessSnapshot(status="OK"),
            HwpProcessSnapshot(status="OK", processes=frozenset({HwpProcessIdentity(100, 1.0)})),
            HwpProcessSnapshot(status="OK", processes=frozenset({HwpProcessIdentity(100, 1.0)})),
            HwpProcessSnapshot(status="OK"),
            HwpProcessSnapshot(status="OK", processes=frozenset({HwpProcessIdentity(200, 2.0)})),
            HwpProcessSnapshot(status="OK", processes=frozenset({HwpProcessIdentity(200, 2.0)})),
        ]
    )
    with patch.object(readback, "_approval_window_snapshot", return_value={"status": "UNAVAILABLE", "titles": []}):
        result = readback.run_readback(
            source,
            output_hwp=work_dir / "paper.hwp",
            report=work_dir / "report.json",
            factory=lambda **_kwargs: _FakeHwp(),
            snapshot_fn=lambda: next(snapshots),
            wait_fn=lambda tracked, **_kwargs: HwpProcessWait(status="OK", tracked=frozenset(tracked)),
        )
    assert result["status"] == "FAIL"
    assert result["approval_window_count"] == 0
    assert any(error["code"] == "HWP_APPROVAL_EVIDENCE_UNAVAILABLE" for error in result["errors"])
