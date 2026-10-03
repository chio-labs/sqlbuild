"""CPU capacity available to this process, including container CPU quotas."""

from __future__ import annotations

import math
import os
from collections.abc import Callable, Iterator
from pathlib import Path

_CGROUP_ROOT: Path = Path("/sys/fs/cgroup")
_PROC_CGROUP: Path = Path("/proc/self/cgroup")
_CGROUP_V1_CPU_CONTROLLER: str = "cpu"
_CGROUP_V1_CPU_DIRECTORIES: tuple[str, ...] = ("cpu", "cpu,cpuacct", "cpuacct,cpu")
_CPU_MAX_FIELD_COUNT: int = 2


def available_cores(*, cgroup_root: Path = _CGROUP_ROOT, proc_cgroup: Path = _PROC_CGROUP) -> int:
    """Return usable CPUs: the process CPU count capped by any cgroup v1 or v2 CPU quota."""

    counter: Callable[[], int | None] | None = getattr(os, "process_cpu_count", None)
    count: int = (counter() if counter is not None else _affinity_count()) or 1
    quotas: list[int] = list(_cgroup_quotas(cgroup_root=cgroup_root, proc_cgroup=proc_cgroup))
    return max(1, min((count, *quotas)))


def _affinity_count() -> int | None:
    affinity: Callable[[int], set[int]] | None = getattr(os, "sched_getaffinity", None)
    return len(affinity(0)) if affinity is not None else os.cpu_count()


def _cgroup_quotas(*, cgroup_root: Path, proc_cgroup: Path) -> Iterator[int]:
    try:
        entries: list[str] = proc_cgroup.read_text(encoding="utf-8").splitlines()
    except (OSError, ValueError):
        entries = []
    for entry in entries or ["0::/"]:
        _hierarchy, _separator, remainder = entry.partition(":")
        controllers, _separator, path = remainder.partition(":")
        if not controllers:
            yield from _quotas_in(
                paths=tuple(
                    directory / "cpu.max"
                    for directory in _directories(base=cgroup_root, relative=path)
                ),
                parse=_cpu_max_quota,
            )
        elif _CGROUP_V1_CPU_CONTROLLER in controllers.split(","):
            for name in (controllers, *_CGROUP_V1_CPU_DIRECTORIES):
                yield from _quotas_in(
                    paths=tuple(_directories(base=cgroup_root / name, relative=path)),
                    parse=_cfs_quota,
                )


def _directories(*, base: Path, relative: str) -> Iterator[Path]:
    """Yield the cgroup directory and each ancestor down from the hierarchy root."""

    directory: Path = base
    yield directory
    for part in Path(relative.strip("/")).parts:
        directory = directory / part
        yield directory


def _quotas_in(*, paths: tuple[Path, ...], parse: Callable[[Path], int | None]) -> Iterator[int]:
    for path in paths:
        quota: int | None = parse(path)
        if quota is not None:
            yield quota


def _cpu_max_quota(path: Path) -> int | None:
    """Parse cgroup v2 `cpu.max`: `max <period>` means unlimited, else `<quota> <period>`."""

    try:
        fields: list[str] = path.read_text(encoding="utf-8").split()
    except (OSError, ValueError):
        return None
    return (
        _quota(quota=fields[0], period=fields[1]) if len(fields) == _CPU_MAX_FIELD_COUNT else None
    )


def _cfs_quota(directory: Path) -> int | None:
    """Parse cgroup v1 `cpu.cfs_quota_us` / `cpu.cfs_period_us`; a negative quota is unlimited."""

    try:
        quota: str = (directory / "cpu.cfs_quota_us").read_text(encoding="utf-8").strip()
        period: str = (directory / "cpu.cfs_period_us").read_text(encoding="utf-8").strip()
    except (OSError, ValueError):
        return None
    return _quota(quota=quota, period=period)


def _quota(*, quota: str, period: str) -> int | None:
    try:
        quota_us: int = int(quota)
        period_us: int = int(period)
    except ValueError:
        return None
    if quota_us <= 0 or period_us <= 0:
        return None
    return max(1, math.ceil(quota_us / period_us))
