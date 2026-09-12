"""Fail-closed observation helpers for Hanword COM process lifecycles.

The helpers in this module are deliberately observational.  They never call
``terminate``/``kill`` and never infer ownership from a process name alone.
Callers take a baseline before creating a COM session, take another snapshot
after creation, and wait only for the newly observed ``Hwp.exe`` identities.

``psutil`` is an optional runtime dependency.  A missing or unusable process
enumerator is represented as ``UNAVAILABLE`` and can never be mistaken for a
clean exit.  Creation time is part of an identity so a PID reused by another
HWP process cannot be treated as the original session.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import time
from typing import Any, Callable, Iterable


@dataclass(frozen=True, order=True)
class HwpProcessIdentity:
    """Stable-enough identity for one observed HWP process instance.

    The identity deliberately uses PID plus creation time only.  Adding an
    executable path looks attractive, but querying ``exe`` can fail for a
    perfectly valid HWP process under Windows access restrictions and would
    make otherwise comparable before/after snapshots inconsistent.  Callers
    that need an executable-path audit should record it separately; ownership
    decisions here remain fail-closed when either PID or creation time is
    unavailable.
    """

    pid: int
    create_time: float

    def as_dict(self) -> dict[str, object]:
        return {"pid": self.pid, "create_time": self.create_time}


@dataclass(frozen=True)
class HwpProcessSnapshot:
    """One all-or-nothing HWP process enumeration result."""

    status: str
    processes: frozenset[HwpProcessIdentity] = frozenset()
    error: str | None = None

    @property
    def pids(self) -> frozenset[int]:
        return frozenset(identity.pid for identity in self.processes)

    def as_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "pids": sorted(self.pids),
            "processes": [identity.as_dict() for identity in sorted(self.processes)],
            "error": self.error,
        }


@dataclass(frozen=True)
class HwpProcessDelta:
    """The HWP identities present after session creation but not before it."""

    status: str
    processes: frozenset[HwpProcessIdentity] = frozenset()
    error: str | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "pids": sorted(identity.pid for identity in self.processes),
            "processes": [identity.as_dict() for identity in sorted(self.processes)],
            "error": self.error,
        }


@dataclass(frozen=True)
class HwpProcessWait:
    """Bounded wait result for identities observed as session-owned candidates."""

    status: str
    tracked: frozenset[HwpProcessIdentity]
    remaining: frozenset[HwpProcessIdentity] = frozenset()
    error: str | None = None

    @property
    def exited(self) -> bool:
        return self.status == "OK" and not self.remaining

    def as_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "tracked_pids": sorted(identity.pid for identity in self.tracked),
            "tracked_processes": [identity.as_dict() for identity in sorted(self.tracked)],
            "remaining_pids": sorted(identity.pid for identity in self.remaining),
            "remaining_processes": [identity.as_dict() for identity in sorted(self.remaining)],
            "error": self.error,
        }


def _unavailable(error: BaseException | str) -> HwpProcessSnapshot:
    return HwpProcessSnapshot(status="UNAVAILABLE", error=repr(error))


def snapshot_hwp_processes(*, psutil_module: Any = None) -> HwpProcessSnapshot:
    """Enumerate HWP process identities, failing closed on uncertainty.

    ``psutil_module`` exists for unit tests and embedders that provide a
    compatible process enumerator.  Every matching HWP record must expose a
    positive PID and finite creation time; otherwise the complete snapshot is
    ``UNAVAILABLE``.  A process that disappears between enumeration and field
    access is ignored, while access/other enumeration failures invalidate the
    whole snapshot.
    """
    try:
        if psutil_module is None:
            import psutil as psutil_module  # type: ignore[no-redef]

        no_such_process = getattr(psutil_module, "NoSuchProcess", ())
        identities: set[HwpProcessIdentity] = set()
        for process in psutil_module.process_iter(("pid", "name", "create_time")):
            try:
                info = process.info
            except Exception as exc:
                if no_such_process and isinstance(exc, no_such_process):
                    continue
                raise
            if not isinstance(info, dict):
                raise RuntimeError("psutil process info is not a mapping")
            name = info.get("name")
            if name is None:
                raise RuntimeError("HWP process enumeration returned an unknown process name")
            if str(name).casefold() != "hwp.exe":
                continue
            try:
                pid = int(info.get("pid"))
                create_time = float(info.get("create_time"))
            except (AttributeError, TypeError, ValueError) as exc:
                raise RuntimeError("HWP process identity is incomplete") from exc
            if pid <= 0 or not math.isfinite(create_time):
                raise RuntimeError("HWP process identity is invalid")
            identities.add(HwpProcessIdentity(pid=pid, create_time=create_time))
        return HwpProcessSnapshot(status="OK", processes=frozenset(identities))
    except Exception as exc:
        return _unavailable(exc)


def newly_started_hwp_processes(
    before: HwpProcessSnapshot,
    after: HwpProcessSnapshot,
) -> HwpProcessDelta:
    """Return identities newly observed after COM startup.

    A non-OK input is propagated as ``UNAVAILABLE``.  This prevents an empty
    set caused by a broken enumerator from being accepted as a clean session.
    """
    if before.status != "OK":
        return HwpProcessDelta(status="UNAVAILABLE", error=before.error or "baseline unavailable")
    if after.status != "OK":
        return HwpProcessDelta(status="UNAVAILABLE", error=after.error or "post-start unavailable")
    return HwpProcessDelta(status="OK", processes=frozenset(after.processes - before.processes))


def wait_for_hwp_processes_to_exit(
    tracked: Iterable[HwpProcessIdentity],
    *,
    snapshot: Callable[[], HwpProcessSnapshot] | None = None,
    timeout: float = 20.0,
    poll_interval: float = 0.25,
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> HwpProcessWait:
    """Wait at most ``timeout`` for exactly the tracked process instances.

    The returned ``UNAVAILABLE`` or ``TIMEOUT`` result is never clean.  The
    function only observes process state; it intentionally performs no kill or
    terminate operation, so unrelated HWP processes remain untouched.
    """
    identities = frozenset(tracked)
    if not identities:
        return HwpProcessWait(
            status="UNAVAILABLE",
            tracked=identities,
            error="no HWP process identity was observed for the COM session",
        )
    # Do not let NaN/Infinity turn the deadline into an unbounded wait.  A
    # zero poll interval is also unsafe for a live process: it can create a
    # tight loop that consumes a core when the injected/real clock does not
    # advance between observations.  ``timeout=0`` is still useful for a
    # single immediate snapshot and therefore permits ``poll_interval=0``.
    try:
        timeout = float(timeout)
        poll_interval = float(poll_interval)
    except (TypeError, ValueError) as exc:
        raise ValueError("timeout and poll_interval must be finite numbers") from exc
    if not math.isfinite(timeout) or not math.isfinite(poll_interval):
        raise ValueError("timeout and poll_interval must be finite numbers")
    if timeout < 0 or poll_interval < 0:
        raise ValueError("timeout and poll_interval must be non-negative")
    if timeout > 0 and poll_interval <= 0:
        raise ValueError("poll_interval must be greater than zero when timeout is positive")
    if snapshot is None:
        snapshot = snapshot_hwp_processes

    try:
        start = float(monotonic())
    except (TypeError, ValueError, OverflowError) as exc:
        return HwpProcessWait(
            status="UNAVAILABLE",
            tracked=identities,
            remaining=identities,
            error=f"invalid monotonic clock: {exc!r}",
        )
    if not math.isfinite(start):
        return HwpProcessWait(
            status="UNAVAILABLE",
            tracked=identities,
            remaining=identities,
            error="invalid monotonic clock: non-finite value",
        )
    deadline = start + timeout
    if not math.isfinite(deadline):
        raise ValueError("timeout is too large to produce a finite deadline")
    while True:
        current = snapshot()
        if current.status != "OK":
            return HwpProcessWait(
                status="UNAVAILABLE",
                tracked=identities,
                remaining=identities,
                error=current.error or "HWP process enumeration unavailable",
            )
        remaining = frozenset(identity for identity in identities if identity in current.processes)
        if not remaining:
            return HwpProcessWait(status="OK", tracked=identities)
        try:
            now = float(monotonic())
        except (TypeError, ValueError, OverflowError) as exc:
            return HwpProcessWait(
                status="UNAVAILABLE",
                tracked=identities,
                remaining=remaining,
                error=f"invalid monotonic clock: {exc!r}",
            )
        if not math.isfinite(now):
            return HwpProcessWait(
                status="UNAVAILABLE",
                tracked=identities,
                remaining=remaining,
                error="invalid monotonic clock: non-finite value",
            )
        if now >= deadline:
            return HwpProcessWait(status="TIMEOUT", tracked=identities, remaining=remaining)
        sleep(min(poll_interval, max(0.0, deadline - now)))
